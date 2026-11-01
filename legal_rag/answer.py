"""Citation-grounded answering.

* ``MockAnswerer`` (default): extractive and deterministic — quotes the retrieved articles with citations, or abstains.
* ``OpenAICompatibleAnswerer``: generates from the retrieved context with an OpenAI-compatible endpoint
  (``LLM_BACKEND=openai`` + ``OPENAI_API_KEY``; optional ``OPENAI_BASE_URL``, ``OPENAI_MODEL``).

Whatever the backend, citations are validated against what was actually retrieved, and every answer goes to the
attorney review queue before anything reaches a client.
"""
from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from .retrieval import BM25Retriever, Hit

CITATION_RE = re.compile(r"\[(SYN-[A-Z]+-\d+ [mb]\.\d+)\]")
ABSTAIN_TEXT = ("Sağlanan kaynaklarda bu soruya dayanak oluşturacak bilgi bulunamadı. "
                "Soru avukat değerlendirmesine yönlendirildi.")
DISCLAIMER = "Not: Bu taslak yanıt avukat onayı olmadan müvekkile iletilmez."


@dataclass
class Answer:
    question: str
    text: str
    citations: list[str]
    retrieved: list[dict]
    abstained: bool
    invalid_citations: list[str] = field(default_factory=list)
    backend: str = "mock"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def extract_citations(text: str) -> list[str]:
    return list(dict.fromkeys(CITATION_RE.findall(text)))


def _select(hits: list[Hit], min_coverage: float) -> list[Hit]:
    if not hits or hits[0].coverage < min_coverage:
        return []
    top = hits[0].score
    floor = max(min_coverage, hits[0].coverage - 0.2)
    return [h for h in hits if h.score >= 0.6 * top and h.coverage >= floor][:2]


class MockAnswerer:
    name = "mock"

    def generate(self, question: str, hits: list[Hit]) -> str:
        lines = [f"{h.chunk.text} [{h.chunk.cite_id}]" for h in hits]
        return "Kaynaklara göre:\n" + "\n".join(f"- {line}" for line in lines)


PROMPT = """Aşağıdaki kaynaklara dayanarak soruyu Türkçe yanıtla. Her cümlenin sonunda köşeli parantez içinde
kaynak kimliğini ver, örn. [SYN-KIRA-01 m.2]. Kaynaklarda olmayan bilgi ekleme. Yanıt kaynaklarda yoksa sadece
"YETERSIZ_KAYNAK" yaz.

KAYNAKLAR:
{context}

SORU: {question}"""


class OpenAICompatibleAnswerer:
    name = "openai"

    def __init__(self, post: Callable[[dict], dict] | None = None):
        self.api_key = os.environ.get("OPENAI_API_KEY", "")
        self.base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        self._post = post

    def generate(self, question: str, hits: list[Hit]) -> str:
        context = "\n".join(f"[{h.chunk.cite_id}] {h.chunk.text}" for h in hits)
        payload = {"model": self.model, "temperature": 0,
                   "messages": [{"role": "user", "content": PROMPT.format(context=context, question=question)}]}
        if self._post:
            data = self._post(payload)
        else:
            import httpx

            r = httpx.post(f"{self.base_url}/chat/completions", json=payload, timeout=60,
                           headers={"Authorization": f"Bearer {self.api_key}"})
            r.raise_for_status()
            data = r.json()
        return data["choices"][0]["message"]["content"] or ""


def get_answerer(name: str | None = None):
    name = (name or os.environ.get("LLM_BACKEND", "mock")).lower()
    return {"mock": MockAnswerer, "openai": OpenAICompatibleAnswerer}[name]()


class LegalAssistant:
    def __init__(self, retriever: BM25Retriever, answerer=None, k: int = 3, min_coverage: float = 0.5):
        self.retriever = retriever
        self.answerer = answerer or get_answerer()
        self.k = k
        self.min_coverage = min_coverage

    def ask(self, question: str) -> Answer:
        hits = self.retriever.search(question, self.k)
        retrieved = [{"cite_id": h.chunk.cite_id, "score": h.score, "coverage": h.coverage} for h in hits]
        selected = _select(hits, self.min_coverage)
        name = getattr(self.answerer, "name", "custom")
        if not selected:
            return Answer(question, ABSTAIN_TEXT, [], retrieved, True, backend=name)
        text = self.answerer.generate(question, selected)
        if "YETERSIZ_KAYNAK" in text:
            return Answer(question, ABSTAIN_TEXT, [], retrieved, True, backend=name)
        cites = extract_citations(text)
        allowed = {h.chunk.cite_id for h in selected}
        invalid = [c for c in cites if c not in allowed]
        return Answer(question, f"{text}\n\n{DISCLAIMER}", cites, retrieved, False, invalid, name)
