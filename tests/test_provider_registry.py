"""Tests for the shared data-provider registry.

Sharing one instance per source is what removes the repeated BaoStock login
(measured at 75-78s), so the lifecycle contract is pinned here: the same
instance comes back for the same name, and dropping it is explicit.
"""

import pytest

from src.data import providers
from src.exceptions import DataSourceError


class _FakeProvider:
    """Stands in for a real provider; only the lifecycle is under test."""

    def __init__(self) -> None:
        self.closed = 0

    def close(self) -> None:
        self.closed += 1


@pytest.fixture
def registry(monkeypatch):
    """An isolated registry, so tests cannot observe each other's instances."""
    monkeypatch.setattr(providers, "_instances", {})
    monkeypatch.setattr(providers, "PROVIDERS", {"fake": _FakeProvider})
    return providers


class TestGetProvider:
    def test_the_same_name_yields_the_same_instance(self, registry):
        assert registry.get_provider("fake") is registry.get_provider("fake")

    def test_an_unknown_name_is_rejected(self, registry):
        with pytest.raises(DataSourceError, match="unknown data source"):
            registry.get_provider("nope")


class TestReset:
    def test_reset_drops_and_closes_the_instance(self, registry):
        first = registry.get_provider("fake")

        registry.reset_provider("fake")

        assert first.closed == 1
        assert registry.get_provider("fake") is not first

    def test_resetting_an_unknown_name_is_harmless(self, registry):
        registry.reset_provider("nope")


class TestCloseAll:
    def test_close_providers_closes_everything(self, registry):
        first = registry.get_provider("fake")

        registry.close_providers()

        assert first.closed == 1
        assert registry.get_provider("fake") is not first
