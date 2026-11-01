"""Command-line interface.

    python -m legal_rag.cli ask "Kıdem tazminatı nasıl hesaplanır?"
    python -m legal_rag.cli intake "Merhaba, adım Ayşe Yılmaz ..."
    python -m legal_rag.cli review list
    python -m legal_rag.cli review approve 1 --reviewer "Av. Demo" --rubric accuracy=2,grounding=2,citation=2
    python -m legal_rag.cli review edit 2 --reviewer "Av. Demo" --set text="..."
    python -m legal_rag.cli review reject 3 --reviewer "Av. Demo" --note "needs case-file context"
    python -m legal_rag.cli demo

Questions and answers are in Turkish because the sample corpus is Turkish. The review queue is stored in
SQLite (default: review.db, git-ignored).
"""
from __future__ import annotations

import argparse
import json

from .answer import LegalAssistant
from .corpus import load_corpus
from .intake import IntakeAgent
from .retrieval import BM25Retriever
from .review import ReviewQueue

DEMO_QUESTION = "Ev sahibi depozitoyu ne zaman iade etmek zorunda?"  # "When must the landlord return the deposit?"
DEMO_INTAKE = ("Merhaba, adım Ayşe Yılmaz. 3 yıldır çalıştığım işyerinden 12.10.2026 tarihinde çıkarıldım, "
               "kıdem tazminatımı ödemediler. Telefonum 0532 000 00 00. Yarın işverenle görüşmem var, acil.")


def _pp(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _rubric(s: str | None) -> dict | None:
    return {k: int(v) for k, v in (p.split("=") for p in s.split(","))} if s else None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="review.db")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ask").add_argument("question")
    sub.add_parser("intake").add_argument("message")
    sub.add_parser("demo")
    rv = sub.add_parser("review")
    rv.add_argument("action", choices=["list", "show", "approve", "edit", "reject"])
    rv.add_argument("id", nargs="?", type=int)
    rv.add_argument("--reviewer", default="")
    rv.add_argument("--note", default=None)
    rv.add_argument("--rubric", default=None, help="e.g. accuracy=2,grounding=2,citation=1,completeness=2,risk=2")
    rv.add_argument("--set", action="append", default=[], help="field=value changes for 'edit'")
    args = ap.parse_args()

    queue = ReviewQueue(":memory:" if args.cmd == "demo" else args.db)
    if args.cmd in ("ask", "demo"):
        ans = LegalAssistant(BM25Retriever(load_corpus())).ask(args.question if args.cmd == "ask" else DEMO_QUESTION)
        item = queue.submit("answer", ans.to_dict())
        print(ans.text)
        print(f"\n[queued for attorney review as item #{item}; citations={ans.citations}; abstained={ans.abstained}]")
    if args.cmd in ("intake", "demo"):
        rec = IntakeAgent().run(args.message if args.cmd == "intake" else DEMO_INTAKE)
        item = queue.submit("intake", rec)
        _pp(rec)
        print(f"[queued for attorney review as item #{item}]")
    if args.cmd == "demo":
        queue.approve(1, "Av. Demo", rubric={"accuracy": 2, "grounding": 2, "citation": 1, "completeness": 2, "risk": 2},
                      note="Second citation is context only.")
        queue.edit(2, "Av. Demo", {"proposed_consultation": "2026-11-04T11:00"}, note="Moved to a slot with the employment-law attorney.")
        print("\nReleased after review:")
        _pp([{k: r[k] for k in ("id", "kind", "status", "reviewer", "rubric")} for r in queue.released()])
    if args.cmd == "review":
        if args.action == "list":
            _pp([{"id": r["id"], "kind": r["kind"], "created_at": r["created_at"],
                  "preview": (r["payload"].get("question") or r["payload"].get("summary", ""))[:80]}
                 for r in queue.pending()])
        elif args.action == "show":
            _pp(queue.get(args.id))
        elif args.action == "approve":
            _pp(queue.approve(args.id, args.reviewer, _rubric(args.rubric), args.note))
        elif args.action == "edit":
            changes = dict(s.split("=", 1) for s in args.set)
            _pp(queue.edit(args.id, args.reviewer, changes, _rubric(args.rubric), args.note))
        elif args.action == "reject":
            _pp(queue.reject(args.id, args.reviewer, args.note or "", _rubric(args.rubric)))


if __name__ == "__main__":
    main()
