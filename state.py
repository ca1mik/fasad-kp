from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
import sqlite3
from typing import Iterator


class StateStore:
    """Durable local at-most-once ledger. Never reserve in dry-run mode."""

    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA busy_timeout=30000")
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _init(self) -> None:
        with self._db() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS deliveries (
                    lead_key TEXT PRIMARY KEY,
                    company TEXT NOT NULL,
                    email TEXT NOT NULL,
                    reserved_at TEXT NOT NULL,
                    sent_at TEXT,
                    message_id TEXT,
                    status TEXT NOT NULL,
                    error TEXT
                );
                CREATE TABLE IF NOT EXISTS processed_replies (
                    reply_id TEXT PRIMARY KEY,
                    processed_at TEXT NOT NULL,
                    lead_key TEXT NOT NULL
                );
                """
            )

    def reserve(self, lead_key: str, company: str, email: str, when: datetime) -> bool:
        try:
            with self._db() as db:
                db.execute(
                    "INSERT INTO deliveries(lead_key,company,email,reserved_at,status) VALUES(?,?,?,?,?)",
                    (lead_key, company, email, when.isoformat(), "reserved"),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def mark_sent(self, lead_key: str, message_id: str, when: datetime) -> None:
        with self._db() as db:
            db.execute(
                "UPDATE deliveries SET sent_at=?,message_id=?,status='commit_pending',error=NULL WHERE lead_key=?",
                (when.isoformat(), message_id, lead_key),
            )

    def mark_committed(self, lead_key: str) -> None:
        with self._db() as db:
            db.execute("UPDATE deliveries SET status='committed',error=NULL WHERE lead_key=?", (lead_key,))

    def mark_uncertain(self, lead_key: str, error: str) -> None:
        with self._db() as db:
            db.execute(
                "UPDATE deliveries SET status='uncertain',error=? WHERE lead_key=?",
                (error[:1000], lead_key),
            )

    def contains(self, lead_key: str) -> bool:
        with self._db() as db:
            return db.execute("SELECT 1 FROM deliveries WHERE lead_key=?", (lead_key,)).fetchone() is not None

    def pending(self) -> list[dict[str, str]]:
        with self._db() as db:
            rows = db.execute(
                "SELECT * FROM deliveries WHERE status='commit_pending' ORDER BY reserved_at"
            ).fetchall()
        return [dict(row) for row in rows]

    def sent_keys_on(self, day: date) -> set[str]:
        prefix = day.isoformat() + "%"
        with self._db() as db:
            rows = db.execute(
                "SELECT lead_key FROM deliveries WHERE sent_at LIKE ? AND status IN ('commit_pending','committed')",
                (prefix,),
            ).fetchall()
        return {row[0] for row in rows}

    def reply_processed(self, reply_id: str) -> bool:
        with self._db() as db:
            return db.execute("SELECT 1 FROM processed_replies WHERE reply_id=?", (reply_id,)).fetchone() is not None

    def mark_reply_processed(self, reply_id: str, lead_key: str, when: datetime) -> None:
        with self._db() as db:
            db.execute(
                "INSERT OR IGNORE INTO processed_replies(reply_id,processed_at,lead_key) VALUES(?,?,?)",
                (reply_id, when.isoformat(), lead_key),
            )

    def report(self) -> dict[str, int]:
        with self._db() as db:
            rows = db.execute("SELECT status,COUNT(*) AS n FROM deliveries GROUP BY status").fetchall()
            reply_count = db.execute("SELECT COUNT(*) FROM processed_replies").fetchone()[0]
        result = {row[0]: row[1] for row in rows}
        result["processed_replies"] = reply_count
        return result
