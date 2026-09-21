"""ChatStore — persists chat history in SQLite.

Each chat has a unique ID and a list of messages stored as JSON.
This is the source of truth; the frontend localStorage is just a cache.
"""

import json
import sqlite3
from pathlib import Path

from src.config import settings
from src.logging import get_logger

logger = get_logger("chat_store")


class ChatStore:
    """SQLite-backed chat history store."""

    def __init__(self, db_path: str | None = None):
        self._db_path = db_path or settings.sqlite_db_path
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS chats (
                id TEXT PRIMARY KEY,
                title TEXT DEFAULT '',
                messages_json TEXT DEFAULT '[]',
                created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
                updated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
            );
        """)
        self._migrate_timestamps()
        self._conn.commit()

    def _migrate_timestamps(self) -> None:
        """Rewrite pre-existing ``datetime('now')`` values as ISO-8601 UTC.

        ``datetime('now')`` produces ``YYYY-MM-DD HH:MM:SS`` with no zone marker,
        which JavaScript parses as *local* time: every stored timestamp rendered
        eight hours early, and mixing those strings with the frontend's ISO
        values sorted the history list incorrectly. Appending the marker makes
        the values unambiguous, and the WHERE guard keeps this idempotent.
        """
        self._conn.execute(
            """
            UPDATE chats SET
              created_at = CASE WHEN created_at NOT LIKE '%T%'
                                THEN replace(created_at, ' ', 'T') || 'Z'
                                ELSE created_at END,
              updated_at = CASE WHEN updated_at NOT LIKE '%T%'
                                THEN replace(updated_at, ' ', 'T') || 'Z'
                                ELSE updated_at END
            WHERE created_at NOT LIKE '%T%' OR updated_at NOT LIKE '%T%'
            """
        )

    def list_chats(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, title, messages_json, created_at, updated_at "
            "FROM chats ORDER BY updated_at DESC"
        ).fetchall()
        return [
            {
                "id": r["id"],
                "title": r["title"],
                "createdAt": r["created_at"],
                "updatedAt": r["updated_at"],
                # A real count: the previous size/100 estimate was meaningless.
                "messageCount": len(json.loads(r["messages_json"])),
            }
            for r in rows
        ]

    def get_chat(self, chat_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT id, title, messages_json, created_at, updated_at FROM chats WHERE id = ?",
            (chat_id,),
        ).fetchone()
        if not row:
            return None
        messages = json.loads(row["messages_json"])
        return {
            "id": row["id"],
            "title": row["title"],
            "messages": messages,
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    def save_chat(self, chat_id: str, messages: list[dict], title: str | None = None) -> None:
        if title is None:
            title = next(
                (m.get("content", "")[:40] for m in messages if m.get("role") == "user"),
                "新对话",
            )
        messages_json = json.dumps(messages, ensure_ascii=False)
        self._conn.execute(
            """INSERT INTO chats (id, title, messages_json, updated_at)
               VALUES (?, ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ','now'))
               ON CONFLICT(id) DO UPDATE SET
                 title=excluded.title,
                 messages_json=excluded.messages_json,
                 updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now')""",
            (chat_id, title, messages_json),
        )
        self._conn.commit()

    def delete_chat(self, chat_id: str) -> None:
        self._conn.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
