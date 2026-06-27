"""SessionStore — multi-session persistence for agent sessions.

Stores session state in SQLite so sessions survive CLI restarts.
Users can list, switch, and restore sessions.
"""

import sqlite3
from datetime import datetime

from src.config import settings
from src.core.models import SessionRecord
from src.exceptions import SessionNotFoundError
from src.logging import get_logger

logger = get_logger("session_store")


class SessionStore:
    """SQLite-based session persistence."""

    def __init__(self, db_path: str | None = None):
        from pathlib import Path

        self._db_path = db_path or settings.sqlite_db_path
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                name TEXT DEFAULT '',
                current_strategy_id TEXT,
                current_backtest_id TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_sessions_is_active ON sessions(is_active);
            CREATE INDEX IF NOT EXISTS idx_sessions_updated_at ON sessions(updated_at);
        """)
        self._conn.commit()

    def create(self, name: str = "") -> dict:
        """Create a new session."""
        import uuid

        session_id = uuid.uuid4().hex[:12]
        now = datetime.now().isoformat()
        self._conn.execute(
            "INSERT INTO sessions (session_id, name, is_active, created_at, updated_at) VALUES (?, ?, 1, ?, ?)",
            (session_id, name, now, now),
        )
        self._conn.commit()
        logger.info("session_created", session_id=session_id, name=name)
        return {"session_id": session_id, "name": name, "status": "created"}

    def load(self, session_id: str) -> dict:
        """Load a session by ID."""
        row = self._conn.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if not row:
            raise SessionNotFoundError(
                f"Session '{session_id}' not found",
                details={"session_id": session_id},
            )
        return {
            "session_id": row["session_id"],
            "name": row["name"],
            "current_strategy_id": row["current_strategy_id"],
            "current_backtest_id": row["current_backtest_id"],
            "is_active": bool(row["is_active"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "status": "loaded",
        }

    def list_active(self) -> list[dict]:
        """List all active sessions."""
        rows = self._conn.execute(
            "SELECT * FROM sessions WHERE is_active = 1 ORDER BY updated_at DESC"
        ).fetchall()
        return [
            {
                "session_id": row["session_id"],
                "name": row["name"],
                "current_strategy_id": row["current_strategy_id"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def update_current_strategy(self, session_id: str, strategy_id: str | None) -> None:
        """Update the current strategy for a session."""
        now = datetime.now().isoformat()
        self._conn.execute(
            "UPDATE sessions SET current_strategy_id = ?, updated_at = ? WHERE session_id = ?",
            (strategy_id, now, session_id),
        )
        self._conn.commit()
        logger.info("session_strategy_updated", session_id=session_id, strategy_id=strategy_id)

    def update_current_backtest(self, session_id: str, backtest_id: str | None) -> None:
        """Update the current backtest result for a session."""
        now = datetime.now().isoformat()
        self._conn.execute(
            "UPDATE sessions SET current_backtest_id = ?, updated_at = ? WHERE session_id = ?",
            (backtest_id, now, session_id),
        )
        self._conn.commit()
        logger.info("session_backtest_updated", session_id=session_id, backtest_id=backtest_id)

    def delete(self, session_id: str) -> None:
        """Soft-delete a session (mark inactive)."""
        now = datetime.now().isoformat()
        self._conn.execute(
            "UPDATE sessions SET is_active = 0, updated_at = ? WHERE session_id = ?",
            (now, session_id),
        )
        self._conn.commit()
        logger.info("session_deleted", session_id=session_id)

    def close(self) -> None:
        self._conn.close()
