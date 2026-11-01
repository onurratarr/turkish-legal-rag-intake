"""Client-intake agent: free-text message from a prospective client -> validated, structured intake JSON.

The mock backend is rule-based (regex + keyword lexicon). An OpenAI-compatible backend can be plugged in with
``LLM_BACKEND=openai``; its output is validated against the same schema and falls back to the rule-based result
if it is invalid. Every intake goes to the attorney review queue (conflict check + acceptance are human decisions).
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Callable

from .text import normalize

MATTER_TYPES = ["tenancy", "employment", "consumer", "family", "inheritance", "other"]
# Turkish keywords (normalised, diacritics folded) per matter type.
MATTER_TERMS = {
    "tenancy": ["kira", "kiraci", "ev sahibi", "depozito", "tahliye", "kontrat"],
    "employment": ["isten", "isveren", "kidem", "tazminat", "maas", "mesai", "calistigim", "isyeri"],
    "consumer": ["ayipli", "satici", "garanti", "urun", "internetten", "siparis", "cayma"],
    "family": ["bosanma", "velayet", "nafaka", "esim", "evlilik"],
    "inheritance": ["miras", "vefat", "tereke", "veraset", "oldu"],
}
URGENT_TERMS = ["acil", "tebligat", "yarin", "son gun", "icra", "sure doluyor", "dava acildi"]

SCHEMA_REQUIRED = {
    "client_name": (str, type(None)), "phone": (str, type(None)), "email": (str, type(None)),
    "matter_type": str, "matter_confidence": (int, float), "urgency": str, "key_dates": list, "amounts_try": list,
    "summary": str, "missing_fields": list, "conflict_check_required": bool, "proposed_consultation": (str, type(None)),
}

SLOTS_FILE = Path(__file__).resolve().parent.parent / "data" / "consultation_slots.json"


def validate_intake(d: dict[str, Any]) -> list[str]:
    errors = [f"missing:{k}" for k in SCHEMA_REQUIRED if k not in d]
    errors += [f"type:{k}" for k, t in SCHEMA_REQUIRED.items() if k in d and not isinstance(d[k], t)]
    if d.get("matter_type") not in MATTER_TYPES:
        errors.append("enum:matter_type")
    if d.get("urgency") not in ("normal", "high"):
        errors.append("enum:urgency")
    return errors


def _classify(text: str) -> tuple[str, float]:
    t = normalize(text)
    counts = {m: sum(t.count(term) for term in terms) for m, terms in MATTER_TERMS.items()}
    best = max(counts, key=lambda m: counts[m])
    total = sum(counts.values())
    if total == 0:
        return "other", 0.0
    return best, round(counts[best] / total, 2)


def _name(text: str) -> str | None:
    m = re.search(r"(?:[Aa]d[ıi]m|[İi]smim|[Bb]en)\s+([A-ZÇĞİÖŞÜ][a-zçğıöşü]+(?:\s+[A-ZÇĞİÖŞÜ][a-zçğıöşü]+)+)", text)
    return m.group(1) if m else None


def rule_based_intake(text: str, slots: list[str] | None = None) -> dict[str, Any]:
    phone = re.search(r"(?:\+90\s?)?0?5\d{2}[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}", text)
    email = re.search(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", text)
    matter, conf = _classify(text)
    urgency = "high" if any(term in normalize(text) for term in URGENT_TERMS) else "normal"
    d: dict[str, Any] = {
        "client_name": _name(text),
        "phone": re.sub(r"[\s-]", "", phone.group(0)) if phone else None,
        "email": email.group(0) if email else None,
        "matter_type": matter,
        "matter_confidence": conf,
        "urgency": urgency,
        "key_dates": re.findall(r"\b\d{1,2}[./]\d{1,2}[./]\d{4}\b", text),
        "amounts_try": [int(a.replace(".", "")) for a in re.findall(r"(\d{1,3}(?:\.\d{3})+|\d+)\s?(?:TL|lira)", text)],
        "summary": " ".join(text.split())[:280],
    }
    d["missing_fields"] = [k for k in ("client_name", "phone") if not d[k]] + \
                          (["contact"] if not d["phone"] and not d["email"] else [])
    d["conflict_check_required"] = True  # always: only an attorney can clear conflicts of interest
    if slots is None:
        slots = json.loads(SLOTS_FILE.read_text(encoding="utf-8"))["slots"]
    d["proposed_consultation"] = (slots[0] if urgency == "high" else slots[min(2, len(slots) - 1)]) if slots else None
    return d


INTAKE_PROMPT = """Extract a JSON object from this Turkish client message for a law firm intake form. Keys:
client_name, phone, email (string or null), matter_type (one of {types}), matter_confidence (0-1),
urgency ("normal" or "high"), key_dates (list of strings), amounts_try (list of integers), summary (<=280 chars),
missing_fields (list), conflict_check_required (always true), proposed_consultation (null).
Return only JSON. Message:
{text}"""


class IntakeAgent:
    def __init__(self, backend: str | None = None, post: Callable[[dict], dict] | None = None,
                 slots: list[str] | None = None):
        self.backend = (backend or os.environ.get("LLM_BACKEND", "mock")).lower()
        self._post = post
        self.slots = slots

    def _llm(self, text: str) -> dict[str, Any]:
        payload = {"model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"), "temperature": 0,
                   "response_format": {"type": "json_object"},
                   "messages": [{"role": "user", "content": INTAKE_PROMPT.format(types=MATTER_TYPES, text=text)}]}
        if self._post:
            data = self._post(payload)
        else:
            import httpx

            base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
            r = httpx.post(f"{base}/chat/completions", json=payload, timeout=60,
                           headers={"Authorization": f"Bearer {os.environ.get('OPENAI_API_KEY', '')}"})
            r.raise_for_status()
            data = r.json()
        return json.loads(data["choices"][0]["message"]["content"])

    def run(self, text: str) -> dict[str, Any]:
        base = rule_based_intake(text, self.slots)
        if self.backend == "mock":
            return base | {"source": "rule_based", "validation_errors": validate_intake(base)}
        try:
            d = self._llm(text)
            d["conflict_check_required"] = True
            d["proposed_consultation"] = base["proposed_consultation"]
            errors = validate_intake(d)
        except Exception as exc:  # network / JSON errors -> safe fallback
            d, errors = {}, [f"llm_error:{type(exc).__name__}"]
        if errors:
            return base | {"source": "rule_based_fallback", "validation_errors": errors}
        return d | {"source": "llm", "validation_errors": []}
