"""Attorney human-in-the-loop review queue (SQLite). Nothing is released to a client unless approved."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS review_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL CHECK (kind IN ('answer', 'intake')),
    payload TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'edited', 'rejected')),
    reviewer TEXT,
    note TEXT,
    final_payload TEXT,
    rubric TEXT,
    created_at TEXT NOT NULL,
    reviewed_at TEXT
);
"""
RUBRIC_KEYS = ("accuracy", "grounding", "citation", "completeness", "risk")  # each 0-2, see RUBRIC.md


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ReviewQueue:
    def __init__(self, path: str = ":memory:"):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def submit(self, kind: str, payload: dict[str, Any]) -> int:
        cur = self.conn.execute("INSERT INTO review_items (kind, payload, created_at) VALUES (?,?,?)",
                                (kind, json.dumps(payload, ensure_ascii=False), _now()))
        self.conn.commit()
        return int(cur.lastrowid)

    def pending(self, kind: str | None = None) -> list[dict]:
        sql, args = "SELECT * FROM review_items WHERE status='pending'", []
        if kind:
            sql += " AND kind=?"
            args.append(kind)
        return [self._row(r) for r in self.conn.execute(sql + " ORDER BY id", args)]

    def get(self, item_id: int) -> dict:
        row = self.conn.execute("SELECT * FROM review_items WHERE id=?", (item_id,)).fetchone()
        if row is None:
            raise KeyError(item_id)
        return self._row(row)

    def _decide(self, item_id: int, status: str, reviewer: str, note: str | None,
                final: dict | None, rubric: dict | None) -> dict:
        item = self.get(item_id)
        if item["status"] != "pending":
            raise ValueError(f"item {item_id} already {item['status']}")
        if not reviewer:
            raise ValueError("reviewer is required")
        if rubric is not None:
            bad = [k for k in rubric if k not in RUBRIC_KEYS or rubric[k] not in (0, 1, 2)]
            if bad:
                raise ValueError(f"invalid rubric fields: {bad}")
        self.conn.execute(
            "UPDATE review_items SET status=?, reviewer=?, note=?, final_payload=?, rubric=?, reviewed_at=? WHERE id=?",
            (status, reviewer, note, json.dumps(final, ensure_ascii=False) if final is not None else None,
             json.dumps(rubric) if rubric is not None else None, _now(), item_id))
        self.conn.commit()
        return self.get(item_id)

    def approve(self, item_id: int, reviewer: str, rubric: dict | None = None, note: str | None = None) -> dict:
        return self._decide(item_id, "approved", reviewer, note, self.get(item_id)["payload"], rubric)

    def edit(self, item_id: int, reviewer: str, changes: dict, rubric: dict | None = None, note: str | None = None) -> dict:
        final = self.get(item_id)["payload"] | changes
        return self._decide(item_id, "edited", reviewer, note, final, rubric)

    def reject(self, item_id: int, reviewer: str, note: str, rubric: dict | None = None) -> dict:
        if not note:
            raise ValueError("a rejection needs a note explaining why")
        return self._decide(item_id, "rejected", reviewer, note, None, rubric)

    def released(self) -> list[dict]:
        """What may be sent to clients: approved or attorney-edited items only."""
        return [self._row(r) for r in self.conn.execute(
            "SELECT * FROM review_items WHERE status IN ('approved','edited') ORDER BY id")]

    @staticmethod
    def _row(r: sqlite3.Row) -> dict:
        d = dict(r)
        for k in ("payload", "final_payload", "rubric"):
            d[k] = json.loads(d[k]) if d[k] else None
        return d
