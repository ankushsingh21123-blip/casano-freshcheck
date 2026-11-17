"""SQLite storage with stdlib sqlite3 only. No ORM."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .config import get_db_path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    answer_date TEXT,
    topic TEXT NOT NULL,
    mode TEXT NOT NULL,
    verdict TEXT NOT NULL,
    query TEXT NOT NULL,
    reasons TEXT NOT NULL,
    signals TEXT NOT NULL,
    evidence TEXT NOT NULL,
    error TEXT,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL
)
"""


def _connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute(_SCHEMA)
    conn.commit()
    return conn


def init_db(db_path: Path | None = None) -> None:
    conn = _connect(db_path)
    conn.close()


def _row_to_check(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "question": row["question"],
        "answer": row["answer"],
        "answer_date": row["answer_date"],
        "topic": row["topic"],
        "mode": row["mode"],
        "verdict": row["verdict"],
        "query": row["query"],
        "reasons": json.loads(row["reasons"]),
        "signals": json.loads(row["signals"]),
        "evidence": json.loads(row["evidence"]),
        "error": json.loads(row["error"]) if row["error"] else None,
        "message": row["message"],
        "created_at": row["created_at"],
    }


def insert_check(record: dict, db_path: Path | None = None) -> dict:
    created_at = datetime.now(timezone.utc).isoformat()
    conn = _connect(db_path)
    try:
        cursor = conn.execute(
            """
            INSERT INTO checks
                (question, answer, answer_date, topic, mode, verdict, query,
                 reasons, signals, evidence, error, message, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["question"],
                record["answer"],
                record.get("answer_date"),
                record["topic"],
                record["mode"],
                record["verdict"],
                record["query"],
                json.dumps(record["reasons"]),
                json.dumps(record["signals"]),
                json.dumps(record["evidence"]),
                json.dumps(record["error"]) if record.get("error") else None,
                record["message"],
                created_at,
            ),
        )
        conn.commit()
        check_id = cursor.lastrowid
    finally:
        conn.close()
    stored = get_check(check_id, db_path=db_path)
    assert stored is not None  # just inserted
    return stored


def list_checks(limit: int = 50, db_path: Path | None = None) -> list[dict]:
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM checks ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    finally:
        conn.close()
    return [_row_to_check(row) for row in rows]


def get_check(check_id: int, db_path: Path | None = None) -> dict | None:
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM checks WHERE id = ?", (check_id,)
        ).fetchone()
    finally:
        conn.close()
    return _row_to_check(row) if row is not None else None
