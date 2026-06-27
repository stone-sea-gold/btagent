"""Tests for FactorStore — written BEFORE implementation (TDD).

Tests cover:
- CRUD operations (create, read, list, delete)
- Search (SQL filtering + vector similarity)
- Input validation (Pydantic)
- Error handling (duplicate, not found, invalid)
"""

import pytest

from src.core.models import Factor, FactorCategory, FactorCreate
from src.exceptions import FactorDuplicateError, FactorNotFoundError, FactorValidationError


class TestFactorCreate:
    """Test FactorCreate input validation."""

    def test_valid_create(self):
        factor = FactorCreate(
            id="momentum_3m",
            name="3个月动量",
            description="过去3个月的收益率",
            category=FactorCategory.MOMENTUM,
            formula="Ref($close, 0) / Ref($close, 60) - 1",
            tags=["动量", "反转"],
        )
        assert factor.id == "momentum_3m"
        assert factor.category == FactorCategory.MOMENTUM

    def test_invalid_id_format(self):
        with pytest.raises(Exception):  # Pydantic ValidationError
            FactorCreate(
                id="Invalid-ID!",  # uppercase not allowed
                name="test",
                description="test",
                category=FactorCategory.MOMENTUM,
                formula="Ref($close, 0)",
            )

    def test_empty_name(self):
        with pytest.raises(Exception):
            FactorCreate(
                id="test_factor",
                name="",
                description="test",
                category=FactorCategory.MOMENTUM,
                formula="Ref($close, 0)",
            )

    def test_empty_formula(self):
        with pytest.raises(Exception):
            FactorCreate(
                id="test_factor",
                name="test",
                description="test",
                category=FactorCategory.MOMENTUM,
                formula="",
            )


class TestFactorStore:
    """Test FactorStore CRUD and search operations."""

    def test_create_and_get(self, factor_store):
        """Create a factor and retrieve it by ID."""
        factor = FactorCreate(
            id="momentum_3m",
            name="3个月动量",
            description="过去3个月的收益率",
            category=FactorCategory.MOMENTUM,
            formula="Ref($close, 0) / Ref($close, 60) - 1",
            tags=["动量"],
        )
        factor_store.create(factor)

        result = factor_store.get("momentum_3m")
        assert result.id == "momentum_3m"
        assert result.name == "3个月动量"
        assert result.formula == "Ref($close, 0) / Ref($close, 60) - 1"

    def test_get_not_found(self, factor_store):
        """Getting a non-existent factor raises FactorNotFoundError."""
        with pytest.raises(FactorNotFoundError):
            factor_store.get("nonexistent_factor")

    def test_create_duplicate(self, factor_store):
        """Creating a factor with duplicate ID raises FactorDuplicateError."""
        factor = FactorCreate(
            id="momentum_3m",
            name="3个月动量",
            description="test",
            category=FactorCategory.MOMENTUM,
            formula="Ref($close, 0)",
        )
        factor_store.create(factor)

        with pytest.raises(FactorDuplicateError):
            factor_store.create(factor)

    def test_list_all(self, factor_store, sample_factors):
        """List all factors."""
        for f in sample_factors:
            factor_store.create(f)

        result = factor_store.list_all()
        assert len(result) == len(sample_factors)

    def test_list_by_category(self, factor_store, sample_factors):
        """List factors filtered by category."""
        for f in sample_factors:
            factor_store.create(f)

        momentum_factors = factor_store.list_by_category(FactorCategory.MOMENTUM)
        assert all(f.category == FactorCategory.MOMENTUM for f in momentum_factors)
        assert len(momentum_factors) > 0

    def test_search_by_text(self, factor_store, sample_factors):
        """Search factors by text query (uses vector DB)."""
        for f in sample_factors:
            factor_store.create(f)

        results = factor_store.search("动量因子")
        assert len(results) > 0
        # Vector search returns results (ranking depends on embedding model)
        factor_ids = [r.factor.id for r in results]
        assert "momentum_3m" in factor_ids

    def test_search_by_tags(self, factor_store, sample_factors):
        """Search factors by tags."""
        for f in sample_factors:
            factor_store.create(f)

        results = factor_store.search_by_tags(["价值"])
        assert len(results) > 0
        assert all("价值" in f.factor.tags for f in results)

    def test_delete(self, factor_store):
        """Delete a factor."""
        factor = FactorCreate(
            id="temp_factor",
            name="temp",
            description="temporary",
            category=FactorCategory.MOMENTUM,
            formula="Ref($close, 0)",
        )
        factor_store.create(factor)
        factor_store.delete("temp_factor")

        with pytest.raises(FactorNotFoundError):
            factor_store.get("temp_factor")

    def test_delete_not_found(self, factor_store):
        """Deleting a non-existent factor raises FactorNotFoundError."""
        with pytest.raises(FactorNotFoundError):
            factor_store.delete("nonexistent")

    def test_builtin_factors_loaded(self, factor_store_with_builtins):
        """Built-in factors are loaded on initialization."""
        factors = factor_store_with_builtins.list_all()
        builtin = [f for f in factors if f.is_builtin]
        assert len(builtin) >= 15  # We expect 15+ builtin factors


# ── Fixtures ───────────────────────────────────────────────────────


@pytest.fixture
def factor_store(tmp_path):
    """Create a FactorStore with temporary storage."""
    from src.core.factor_store import FactorStore

    return FactorStore(
        db_path=str(tmp_path / "test_factors.db"),
        chroma_path=str(tmp_path / "chroma"),
    )


@pytest.fixture
def factor_store_with_builtins(tmp_path):
    """Create a FactorStore with built-in factors loaded."""
    from src.core.factor_store import FactorStore

    store = FactorStore(
        db_path=str(tmp_path / "test_factors.db"),
        chroma_path=str(tmp_path / "chroma"),
    )
    store.load_builtin_factors()
    return store


@pytest.fixture
def sample_factors():
    """Sample factor definitions for testing."""
    return [
        FactorCreate(
            id="momentum_3m",
            name="3个月动量",
            description="过去3个月的股票收益率，衡量短期趋势",
            category=FactorCategory.MOMENTUM,
            formula="Ref($close, 0) / Ref($close, 60) - 1",
            tags=["动量", "趋势", "短期"],
        ),
        FactorCreate(
            id="ep_ratio",
            name="盈利收益率 (EP)",
            description="每股收益除以股价，价值因子的核心指标",
            category=FactorCategory.VALUE,
            formula="$eps / Ref($close, 0)",
            tags=["价值", "基本面", "盈利"],
        ),
        FactorCreate(
            id="roe_ttm",
            name="ROE (TTM)",
            description="滚动净资产收益率，衡量盈利能力",
            category=FactorCategory.QUALITY,
            formula="$net_profit / $equity",
            tags=["质量", "盈利能力", "基本面"],
        ),
    ]
