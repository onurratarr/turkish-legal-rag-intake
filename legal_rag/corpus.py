"""Load the markdown corpus and split it into citable chunks (one per article / section)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DOCS = Path(__file__).resolve().parent.parent / "data" / "docs"


@dataclass(frozen=True)
class Chunk:
    cite_id: str      # e.g. "SYN-KIRA-01 m.2"
    doc_id: str
    doc_title: str
    heading: str
    text: str
    source_type: str  # "synthetic" for every document shipped here


def _frontmatter(raw: str) -> tuple[dict, str]:
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", raw, re.S)
    if not m:
        return {}, raw
    meta = dict(line.split(":", 1) for line in m.group(1).splitlines() if ":" in line)
    return {k.strip(): v.strip() for k, v in meta.items()}, m.group(2)


def load_corpus(docs_dir: str | Path = DEFAULT_DOCS) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in sorted(Path(docs_dir).glob("SYN-*.md")):
        meta, body = _frontmatter(path.read_text(encoding="utf-8"))
        doc_id = meta.get("id", path.stem)
        for sec in re.split(r"^## ", body, flags=re.M)[1:]:
            heading, _, text = sec.partition("\n")
            m = re.match(r"(Madde|Bölüm)\s+(\d+)", heading)
            if not m:
                continue
            prefix = "m" if m.group(1) == "Madde" else "b"
            chunks.append(Chunk(f"{doc_id} {prefix}.{m.group(2)}", doc_id, meta.get("title", doc_id),
                                heading.strip(), " ".join(text.split()), meta.get("source_type", "unknown")))
    return chunks
