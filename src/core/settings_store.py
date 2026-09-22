"""SettingsStore — persists LLM config presets in SQLite.

Users can save multiple presets and activate them with one click.
The active preset is read by create_llm() every time the agent runs,
so switching takes effect immediately without restart.
"""

import json
import sqlite3
from pathlib import Path

from src.config import settings
from src.logging import get_logger

logger = get_logger("settings_store")


def _headers_to_json(headers: dict[str, str] | None) -> str:
    """Serialize custom headers for storage. Absent headers stay ``'{}'``."""
    return json.dumps(headers or {}, ensure_ascii=False, sort_keys=True)


def _headers_from_json(raw: str | None) -> dict[str, str]:
    """Parse stored headers, tolerating both NULL and a corrupt value.

    A preset whose header blob cannot be parsed is still usable without them,
    which beats failing the whole settings page on one bad row.
    """
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        logger.warning("preset_headers_unreadable")
        return {}
    return parsed if isinstance(parsed, dict) else {}


class SettingsStore:
    """SQLite-backed LLM preset store."""

    def __init__(self, db_path: str | None = None):
        self._db_path = db_path or settings.sqlite_db_path
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS llm_presets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                label TEXT NOT NULL DEFAULT '',
                api_key TEXT DEFAULT '',
                base_url TEXT DEFAULT '',
                model TEXT DEFAULT '',
                protocol TEXT DEFAULT 'auto',
                headers TEXT DEFAULT '{}',
                is_active INTEGER DEFAULT 0
            );
        """)
        self._migrate_protocol()
        self._migrate_headers()
        self._conn.commit()

    def _migrate_protocol(self) -> None:
        """Add the ``protocol`` column to databases created before it existed.

        The protocol used to be inferred from the base URL alone, which routed
        self-hosted gateways onto the wrong SDK. Rows predating the column keep
        that behaviour via the ``'auto'`` default; the PRAGMA guard keeps this
        idempotent.
        """
        columns = {row["name"] for row in self._conn.execute("PRAGMA table_info(llm_presets)")}
        if "protocol" not in columns:
            self._conn.execute(
                "ALTER TABLE llm_presets ADD COLUMN protocol TEXT DEFAULT 'auto'"
            )
            logger.info("presets_protocol_column_added")

    def _migrate_headers(self) -> None:
        """Add the ``headers`` column to databases created before it existed.

        Some gateways reject requests that omit a custom header — OpenCode Go
        demands ``x-opencode-session`` and answers 400 without it — and the
        preset had no way to express one. Existing rows default to ``'{}'``,
        i.e. send no extra headers, exactly as before.
        """
        columns = {row["name"] for row in self._conn.execute("PRAGMA table_info(llm_presets)")}
        if "headers" not in columns:
            self._conn.execute(
                "ALTER TABLE llm_presets ADD COLUMN headers TEXT DEFAULT '{}'"
            )
            logger.info("presets_headers_column_added")

    # ── Presets CRUD ────────────────────────────────────────────

    def list_presets(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, label, base_url, model, protocol, headers, is_active"
            " FROM llm_presets ORDER BY id"
        ).fetchall()
        return [
            {
                "id": r["id"],
                "label": r["label"],
                "base_url": r["base_url"],
                "model": r["model"],
                "protocol": r["protocol"] or "auto",
                "headers": _headers_from_json(r["headers"]),
                "is_active": bool(r["is_active"]),
            }
            for r in rows
        ]

    def add_preset(
        self,
        label: str,
        base_url: str,
        api_key: str,
        model: str,
        protocol: str = "auto",
        headers: dict[str, str] | None = None,
    ) -> int:
        cur = self._conn.execute(
            "INSERT INTO llm_presets"
            " (label, api_key, base_url, model, protocol, headers, is_active)"
            " VALUES (?, ?, ?, ?, ?, ?, 0)",
            (label, api_key, base_url, model, protocol, _headers_to_json(headers)),
        )
        self._conn.commit()
        logger.info(
            "preset_added",
            label=label,
            model=model,
            protocol=protocol,
            headers=sorted((headers or {}).keys()),
        )
        return cur.lastrowid

    def delete_preset(self, preset_id: int) -> None:
        self._conn.execute("DELETE FROM llm_presets WHERE id = ?", (preset_id,))
        self._conn.commit()
        logger.info("preset_deleted", preset_id=preset_id)

    def activate_preset(self, preset_id: int | None) -> dict | None:
        """Activate a preset by ID and deactivate all others. None = deactivate all."""
        self._conn.execute("UPDATE llm_presets SET is_active = 0")
        if preset_id is not None:
            self._conn.execute("UPDATE llm_presets SET is_active = 1 WHERE id = ?", (preset_id,))
        self._conn.commit()
        if preset_id is None:
            logger.info("preset_deactivated_all")
            return None
        row = self._conn.execute(
            "SELECT id, label, base_url, api_key, model, protocol, headers"
            " FROM llm_presets WHERE id = ?",
            (preset_id,),
        ).fetchone()
        if row:
            logger.info("preset_activated", label=row["label"], model=row["model"])
            return {
                "label": row["label"],
                "base_url": row["base_url"],
                "api_key": row["api_key"],
                "model": row["model"],
                "protocol": row["protocol"] or "auto",
                "headers": _headers_from_json(row["headers"]),
            }
        return None

    def get_active_config(self) -> dict | None:
        """Get the active preset config (for create_llm())."""
        row = self._conn.execute(
            "SELECT api_key, base_url, model, protocol, headers"
            " FROM llm_presets WHERE is_active = 1"
        ).fetchone()
        if row:
            return {
                "api_key": row["api_key"],
                "base_url": row["base_url"],
                "model": row["model"],
                "protocol": row["protocol"] or "auto",
                "headers": _headers_from_json(row["headers"]),
            }
        return None

    def close(self) -> None:
        self._conn.close()
