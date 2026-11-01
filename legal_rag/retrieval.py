"""BM25 retrieval over chunks, implemented from scratch (no external dependencies)."""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass

from .corpus import Chunk
from .text import content_stems, expand_query


@dataclass
class Hit:
    chunk: Chunk
    score: float
    coverage: float  # share of the query's content stems that appear in the chunk


class BM25Retriever:
    def __init__(self, chunks: list[Chunk], k1: float = 1.5, b: float = 0.75):
        self.chunks = chunks
        self.k1, self.b = k1, b
        self.docs = [content_stems(f"{c.doc_title} {c.heading} {c.text}") for c in chunks]
        self.tf = [Counter(d) for d in self.docs]
        self.avgdl = sum(len(d) for d in self.docs) / max(len(self.docs), 1)
        df = Counter(t for d in self.docs for t in set(d))
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def search(self, query: str, k: int = 3) -> list[Hit]:
        q = list(dict.fromkeys(content_stems(expand_query(query))))
        hits: list[Hit] = []
        for chunk, tf, doc in zip(self.chunks, self.tf, self.docs):
            score = 0.0
            for t in q:
                if t in tf:
                    f = tf[t]
                    score += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * len(doc) / self.avgdl))
            if score > 0:
                cov = sum(1 for t in q if t in tf) / len(q) if q else 0.0
                hits.append(Hit(chunk, round(score, 4), round(cov, 3)))
        hits.sort(key=lambda h: (-h.score, h.chunk.cite_id))
        return hits[:k]
