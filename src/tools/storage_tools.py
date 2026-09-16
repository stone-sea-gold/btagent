"""Strategy storage tools for the Agent.

Supports:
- Basic CRUD (save, load, list)
- Version chain (parent_id, version)
- Vector search (agent_summary embedding)
- Bridge retrieval (SQL + vector intersection)
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

import chromadb

from src.config import settings
from src.core.models import StrategyConfig, StrategyRecord
from src.exceptions import StrategyNotFoundError
from src.logging import get_logger

logger = get_logger("storage_tools")


class StrategyStore:
    """SQLite + ChromaDB strategy persistence with version chain."""

    def __init__(self, db_path: str | None = None, chroma_path: str | None = None):
        self._db_path = db_path or settings.sqlite_db_path
        self._chroma_path = chroma_path or settings.chroma_persist_dir

        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        Path(self._chroma_path).mkdir(parents=True, exist_ok=True)

        # SQLite
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

        # ChromaDB for strategy semantic search
        self._chroma = chromadb.PersistentClient(path=self._chroma_path)
        self._collection = self._chroma.get_or_create_collection(
            name="strategies",
            metadata={"hnsw:space": "cosine"},
        )

    def _init_db(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS strategies (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                config_json TEXT NOT NULL,
                description TEXT DEFAULT '',
                agent_summary TEXT DEFAULT '',
                parent_id TEXT,
                version INTEGER DEFAULT 1,
                backtest_result_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)
        # Migration: add new columns if they don't exist (for existing databases)
        self._migrate_add_column("agent_summary", "TEXT DEFAULT ''")
        self._migrate_add_column("parent_id", "TEXT")
        self._migrate_add_column("version", "INTEGER DEFAULT 1")
        self._migrate_add_column("updated_at", "TEXT NOT NULL DEFAULT ''")
        self._conn.executescript("""
            CREATE INDEX IF NOT EXISTS idx_strategies_created_at ON strategies(created_at);
            CREATE INDEX IF NOT EXISTS idx_strategies_name ON strategies(name);
            CREATE INDEX IF NOT EXISTS idx_strategies_parent_id ON strategies(parent_id);
            CREATE INDEX IF NOT EXISTS idx_strategies_version ON strategies(version);
        """)
        self._conn.commit()

    def _migrate_add_column(self, column: str, col_type: str) -> None:
        """Add a column to the strategies table if it doesn't exist."""
        try:
            self._conn.execute(f"ALTER TABLE strategies ADD COLUMN {column} {col_type}")
        except sqlite3.OperationalError:
            pass  # Column already exists

    def save(
        self,
        name: str,
        config: dict,
        description: str = "",
        agent_summary: str = "",
        version: int = 1,
        parent_id: str | None = None,
        backtest_result_id: str | None = None,
    ) -> dict:
        """Save a strategy with optional version chain."""
        import uuid
        strategy_id = f"strat_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        now = datetime.now().isoformat()

        self._conn.execute(
            """INSERT INTO strategies
               (id, name, config_json, description, agent_summary, parent_id, version, backtest_result_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (strategy_id, name, json.dumps(config, ensure_ascii=False), description,
             agent_summary, parent_id, version, backtest_result_id, now, now),
        )
        self._conn.commit()

        # Add to vector DB if agent_summary is provided
        if agent_summary:
            doc_text = f"{name} {agent_summary}"
            self._collection.upsert(
                ids=[strategy_id],
                documents=[doc_text],
                metadatas=[{"name": name, "version": version}],
            )

        logger.info("strategy_saved", strategy_id=strategy_id, name=name, version=version)
        return {"strategy_id": strategy_id, "name": name, "version": version, "status": "saved"}

    def load(self, strategy_id: str) -> dict:
        """Load a strategy by ID."""
        row = self._conn.execute(
            "SELECT * FROM strategies WHERE id = ?", (strategy_id,)
        ).fetchone()
        if not row:
            raise StrategyNotFoundError(
                f"Strategy '{strategy_id}' not found",
                details={"strategy_id": strategy_id},
            )
        return self._row_to_dict(row)

    def delete(self, strategy_id: str) -> dict:
        """Delete a strategy by ID. Removes from SQLite and ChromaDB."""
        row = self._conn.execute(
            "SELECT * FROM strategies WHERE id = ?", (strategy_id,)
        ).fetchone()
        if not row:
            raise StrategyNotFoundError(
                f"Strategy '{strategy_id}' not found",
                details={"strategy_id": strategy_id},
            )

        name = row["name"]
        version = row["version"]

        self._conn.execute("DELETE FROM strategies WHERE id = ?", (strategy_id,))
        self._conn.commit()

        # Remove from vector DB
        try:
            ids = self._collection.get(ids=[strategy_id])
            if ids and ids["ids"]:
                self._collection.delete(ids=[strategy_id])
        except Exception:
            pass  # ChromaDB may not have this entry

        logger.info("strategy_deleted", strategy_id=strategy_id, name=name, version=version)
        return {"strategy_id": strategy_id, "name": name, "version": version, "status": "deleted"}

    def update_timestamp(self, strategy_id: str) -> None:
        """Update the updated_at timestamp for a strategy."""
        now = datetime.now().isoformat()
        self._conn.execute(
            "UPDATE strategies SET updated_at = ? WHERE id = ?", (now, strategy_id)
        )
        self._conn.commit()

    def list_all(self, limit: int = 20) -> list[dict]:
        """List all strategies, showing each record's version and the latest version for the name."""
        rows = self._conn.execute(
            """SELECT s.id, s.name, s.description, s.version, s.parent_id, s.created_at, s.updated_at,
                      (SELECT MAX(s2.version) FROM strategies s2 WHERE s2.name = s.name) AS latest_version
               FROM strategies s
               ORDER BY s.created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [
            {
                "strategy_id": row["id"],
                "name": row["name"],
                "description": row["description"],
                "version": row["version"],
                "latest_version": row["latest_version"],
                "parent_id": row["parent_id"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def get_version_chain(self, strategy_id: str) -> list[dict]:
        """Get the full version chain for a strategy.

        Walks up the parent_id chain and returns all versions in order.
        """
        chain = []
        current_id = strategy_id

        while current_id:
            row = self._conn.execute(
                "SELECT * FROM strategies WHERE id = ?", (current_id,)
            ).fetchone()
            if not row:
                break
            chain.append(self._row_to_dict(row))
            current_id = row["parent_id"]

        chain.reverse()  # oldest first
        return chain

    def get_latest_version(self, name: str) -> dict:
        """Get the latest version of a strategy by name."""
        row = self._conn.execute(
            "SELECT * FROM strategies WHERE name = ? ORDER BY version DESC LIMIT 1",
            (name,),
        ).fetchone()
        if not row:
            raise StrategyNotFoundError(
                f"Strategy '{name}' not found",
                details={"name": name},
            )
        return self._row_to_dict(row)

    def search_strategies(self, query: str, limit: int = 5) -> list[dict]:
        """Search strategies by semantic similarity (vector search)."""
        if self._collection.count() == 0:
            return []

        results = self._collection.query(
            query_texts=[query],
            n_results=min(limit, self._collection.count()),
        )

        search_results = []
        for i, strategy_id in enumerate(results["ids"][0]):
            try:
                strategy = self.load(strategy_id)
                distance = results["distances"][0][i] if results["distances"] else 0
                score = max(0, 1 - distance)
                strategy["relevance_score"] = round(score, 3)
                search_results.append(strategy)
            except StrategyNotFoundError:
                continue

        return search_results

    def _row_to_dict(self, row: sqlite3.Row) -> dict:
        return {
            "strategy_id": row["id"],
            "name": row["name"],
            "config": json.loads(row["config_json"]),
            "description": row["description"],
            "agent_summary": row["agent_summary"],
            "parent_id": row["parent_id"],
            "version": row["version"],
            "backtest_result_id": row["backtest_result_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"] if "updated_at" in row.keys() else "",
            "status": "loaded",
        }

    def close(self) -> None:
        self._conn.close()


# ── Tool functions ─────────────────────────────────────────────────


def save_strategy(
    name: str,
    config: dict,
    store: StrategyStore,
    description: str = "",
    agent_summary: str = "",
    version: int = 1,
    parent_id: str | None = None,
) -> dict:
    """Save a strategy to persistent storage."""
    return store.save(
        name=name, config=config, description=description,
        agent_summary=agent_summary, version=version, parent_id=parent_id,
    )


def load_strategy(strategy_id: str, store: StrategyStore) -> dict:
    """Load a strategy from persistent storage."""
    return store.load(strategy_id=strategy_id)


def list_strategies(store: StrategyStore, limit: int = 20) -> list[dict]:
    """List all saved strategies."""
    return store.list_all(limit=limit)


def search_strategies(query: str, store: StrategyStore, limit: int = 5) -> list[dict]:
    """Search strategies by semantic similarity."""
    return store.search_strategies(query=query, limit=limit)


def delete_strategy(strategy_id: str, store: StrategyStore) -> dict:
    """Delete a strategy from persistent storage."""
    return store.delete(strategy_id=strategy_id)
