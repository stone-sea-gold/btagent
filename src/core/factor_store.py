"""FactorStore — dual-storage factor registry.

Storage:
- SQLite: structured data (id, name, category, formula, tags, created_at)
- ChromaDB: vector embeddings for semantic search

Operations:
- CRUD (create, get, list, delete)
- Search (SQL filters + vector similarity)
- Load builtin factors from JSON
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

import chromadb

from src.config import settings
from src.core.models import (
    Factor,
    FactorCategory,
    FactorCreate,
    FactorSearchResult,
)
from src.exceptions import FactorDuplicateError, FactorNotFoundError
from src.logging import get_logger

logger = get_logger("factor_store")


class FactorStore:
    """Dual-storage factor registry with SQLite + ChromaDB."""

    def __init__(self, db_path: str | None = None, chroma_path: str | None = None):
        self._db_path = db_path or settings.sqlite_db_path
        self._chroma_path = chroma_path or settings.chroma_persist_dir

        # Ensure parent directories exist
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        Path(self._chroma_path).mkdir(parents=True, exist_ok=True)

        # SQLite setup (check_same_thread=False for LangGraph tool execution)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

        # ChromaDB setup
        self._chroma = chromadb.PersistentClient(path=self._chroma_path)
        self._collection = self._chroma.get_or_create_collection(
            name="factors",
            metadata={"hnsw:space": "cosine"},
        )

        logger.info(
            "factor_store_initialized",
            db_path=self._db_path,
            chroma_path=self._chroma_path,
        )

    def _init_db(self) -> None:
        """Create tables if they don't exist."""
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS factors (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                category TEXT NOT NULL,
                formula TEXT NOT NULL,
                parameters TEXT NOT NULL DEFAULT '{}',
                tags TEXT NOT NULL DEFAULT '[]',
                is_builtin INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_factors_category ON factors(category);
            CREATE INDEX IF NOT EXISTS idx_factors_is_builtin ON factors(is_builtin);
            CREATE INDEX IF NOT EXISTS idx_factors_created_at ON factors(created_at);
        """)
        self._conn.commit()

    # ── CRUD ───────────────────────────────────────────────────────

    def create(self, factor: FactorCreate) -> Factor:
        """Create a new factor. Raises FactorDuplicateError if ID exists."""
        # Check for duplicate
        existing = self._conn.execute(
            "SELECT id FROM factors WHERE id = ?", (factor.id,)
        ).fetchone()
        if existing:
            raise FactorDuplicateError(
                f"Factor '{factor.id}' already exists",
                details={"id": factor.id},
            )

        now = datetime.now().isoformat()
        self._conn.execute(
            """INSERT INTO factors (id, name, description, category, formula, parameters, tags, is_builtin, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)""",
            (
                factor.id,
                factor.name,
                factor.description,
                factor.category.value,
                factor.formula,
                json.dumps(factor.parameters, ensure_ascii=False),
                json.dumps(factor.tags, ensure_ascii=False),
                now,
            ),
        )
        self._conn.commit()

        # Add to vector DB
        doc_text = f"{factor.name} {factor.description} {' '.join(factor.tags)}"
        self._collection.upsert(
            ids=[factor.id],
            documents=[doc_text],
            metadatas=[{"category": factor.category.value, "tags": ",".join(factor.tags)}],
        )

        logger.info("factor_created", factor_id=factor.id, category=factor.category.value)
        return self.get(factor.id)

    def get(self, factor_id: str) -> Factor:
        """Get a factor by ID. Raises FactorNotFoundError if not found."""
        row = self._conn.execute(
            "SELECT * FROM factors WHERE id = ?", (factor_id,)
        ).fetchone()
        if not row:
            raise FactorNotFoundError(
                f"Factor '{factor_id}' not found",
                details={"id": factor_id},
            )
        return self._row_to_factor(row)

    def list_all(self) -> list[Factor]:
        """List all factors."""
        rows = self._conn.execute("SELECT * FROM factors ORDER BY category, id").fetchall()
        return [self._row_to_factor(row) for row in rows]

    def list_by_category(self, category: FactorCategory) -> list[Factor]:
        """List factors filtered by category."""
        rows = self._conn.execute(
            "SELECT * FROM factors WHERE category = ? ORDER BY id",
            (category.value,),
        ).fetchall()
        return [self._row_to_factor(row) for row in rows]

    def delete(self, factor_id: str) -> None:
        """Delete a factor. Raises FactorNotFoundError if not found."""
        existing = self._conn.execute(
            "SELECT id FROM factors WHERE id = ?", (factor_id,)
        ).fetchone()
        if not existing:
            raise FactorNotFoundError(
                f"Factor '{factor_id}' not found",
                details={"id": factor_id},
            )

        # Prevent deleting builtin factors
        row = self._conn.execute(
            "SELECT is_builtin FROM factors WHERE id = ?", (factor_id,)
        ).fetchone()
        if row["is_builtin"]:
            raise ValueError(f"Cannot delete builtin factor '{factor_id}'")

        self._conn.execute("DELETE FROM factors WHERE id = ?", (factor_id,))
        self._conn.commit()

        # Remove from vector DB
        self._collection.delete(ids=[factor_id])
        logger.info("factor_deleted", factor_id=factor_id)

    # ── Search ─────────────────────────────────────────────────────

    def search(self, query: str, limit: int = 5) -> list[FactorSearchResult]:
        """Search factors by natural language query (vector search)."""
        if self._collection.count() == 0:
            return []

        results = self._collection.query(
            query_texts=[query],
            n_results=min(limit, self._collection.count()),
        )

        search_results = []
        for i, factor_id in enumerate(results["ids"][0]):
            try:
                factor = self.get(factor_id)
                # ChromaDB returns distances; convert to similarity score
                distance = results["distances"][0][i] if results["distances"] else 0
                score = max(0, 1 - distance)  # cosine distance to similarity
                search_results.append(
                    FactorSearchResult(factor=factor, score=score, source="vector")
                )
            except FactorNotFoundError:
                continue

        return search_results

    def search_by_tags(self, tags: list[str]) -> list[FactorSearchResult]:
        """Search factors that match ALL given tags (SQL filter)."""
        factors = self.list_all()
        results = []
        for f in factors:
            if all(tag in f.tags for tag in tags):
                results.append(
                    FactorSearchResult(factor=f, score=1.0, source="sql")
                )
        return results

    # ── Builtin Factors ────────────────────────────────────────────

    def load_builtin_factors(self) -> int:
        """Load built-in factors from JSON file. Returns count loaded."""
        builtin_path = Path(settings.factors_builtin_dir) / "factors.json"
        if not builtin_path.exists():
            logger.warning("builtin_factors_not_found", path=str(builtin_path))
            return 0

        with open(builtin_path, encoding="utf-8") as f:
            factors_data = json.load(f)

        loaded = 0
        for data in factors_data:
            try:
                # Skip if already exists
                self._conn.execute(
                    "SELECT id FROM factors WHERE id = ?", (data["id"],)
                ).fetchone()
                if self._conn.execute(
                    "SELECT id FROM factors WHERE id = ?", (data["id"],)
                ).fetchone():
                    continue

                now = datetime.now().isoformat()
                self._conn.execute(
                    """INSERT INTO factors (id, name, description, category, formula, parameters, tags, is_builtin, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)""",
                    (
                        data["id"],
                        data["name"],
                        data["description"],
                        data["category"],
                        data["formula"],
                        json.dumps(data.get("parameters", {}), ensure_ascii=False),
                        json.dumps(data.get("tags", []), ensure_ascii=False),
                        now,
                    ),
                )

                # Add to vector DB
                doc_text = f"{data['name']} {data['description']} {' '.join(data.get('tags', []))}"
                self._collection.upsert(
                    ids=[data["id"]],
                    documents=[doc_text],
                    metadatas=[{"category": data["category"], "tags": ",".join(data.get("tags", []))}],
                )
                loaded += 1
            except Exception as e:
                logger.warning("builtin_factor_load_error", factor_id=data.get("id"), error=str(e))

        self._conn.commit()
        logger.info("builtin_factors_loaded", count=loaded)
        return loaded

    # ── Internal ───────────────────────────────────────────────────

    def _row_to_factor(self, row: sqlite3.Row) -> Factor:
        """Convert a SQLite row to a Factor model."""
        return Factor(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            category=FactorCategory(row["category"]),
            formula=row["formula"],
            parameters=json.loads(row["parameters"]),
            tags=json.loads(row["tags"]),
            is_builtin=bool(row["is_builtin"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
