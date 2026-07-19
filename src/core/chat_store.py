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
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );
        """)
        self._conn.commit()

    def list_chats(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, title, created_at, updated_at, length(messages_json) as msg_size FROM chats ORDER BY updated_at DESC"
        ).fetchall()
        return [
            {
                "id": r["id"],
                "title": r["title"],
                "createdAt": r["created_at"],
                "updatedAt": r["updated_at"],
                "messageCount": max(1, r["msg_size"] // 100),  # rough estimate
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
               VALUES (?, ?, ?, datetime('now'))
               ON CONFLICT(id) DO UPDATE SET
                 title=excluded.title,
                 messages_json=excluded.messages_json,
                 updated_at=datetime('now')""",
            (chat_id, title, messages_json),
        )
        self._conn.commit()

    def delete_chat(self, chat_id: str) -> None:
        self._conn.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
