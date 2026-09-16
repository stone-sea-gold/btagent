"""Tests for the agent tool registry.

The registry is the single source of truth for the agent's tool surface, so its
invariants are worth pinning down: adapters register once, the bind list and the
dispatch table are derived from the same registration, and registration order is
preserved because it determines the tool order sent to the model.
"""

import inspect

import pytest

from src.agent.registry import ToolRegistry


def _make(name: str, doc: str = "A tool."):
    """Create a stand-in adapter with a real __name__ and __doc__."""

    def adapter(query: str = "") -> str:
        return "{}"

    adapter.__name__ = name
    adapter.__doc__ = doc
    return adapter


class TestRegistration:
    def test_register_via_decorator_returns_function_unchanged(self):
        """LangChain derives the tool schema from the function itself, so the
        decorator must not wrap or replace it."""
        registry = ToolRegistry()

        @registry.tool("factor")
        def _search_factors(query: str) -> str:
            """Search factors."""
            return "[]"

        assert inspect.isfunction(_search_factors)
        assert _search_factors.__name__ == "_search_factors"
        assert _search_factors.__doc__ == "Search factors."
        assert _search_factors("a") == "[]"
        assert registry.names() == ["_search_factors"]

    def test_entry_records_name_domain_description(self):
        registry = ToolRegistry()
        adapter = _make("_t", "Does a thing.")
        registry.add(adapter, domain="factor")

        entry = registry.entries()[0]
        assert entry.name == "_t"
        assert entry.domain == "factor"
        assert entry.description == "Does a thing."
        assert entry.func is adapter

    def test_duplicate_name_rejected(self):
        registry = ToolRegistry()
        registry.add(_make("_dup"), domain="factor")
        with pytest.raises(ValueError, match="duplicate agent tool name"):
            registry.add(_make("_dup"), domain="backtest")

    def test_missing_docstring_rejected(self):
        """A tool without a docstring would silently lose its description."""
        registry = ToolRegistry()
        fn = _make("_nodoc")
        fn.__doc__ = None
        with pytest.raises(ValueError, match="no docstring"):
            registry.add(fn, domain="factor")


class TestDerivedSurfaces:
    def test_bind_and_dispatch_agree_and_preserve_order(self):
        registry = ToolRegistry()
        for name in ("_a", "_b", "_c"):
            registry.add(_make(name), domain="d1")

        bound = registry.bind()
        assert [f.__name__ for f in bound] == ["_a", "_b", "_c"]
        # The dispatch table must cover exactly the bound tools, in the same
        # order, or a model tool call could resolve to nothing.
        assert list(registry.dispatch()) == ["_a", "_b", "_c"]

    def test_dispatch_maps_to_bound_callables(self):
        registry = ToolRegistry()
        registry.add(_make("_a"), domain="d1")
        assert registry.dispatch()["_a"] is registry.bind()[0]


class TestDomainFiltering:
    def _registry(self):
        registry = ToolRegistry()
        registry.add(_make("_f1"), domain="factor")
        registry.add(_make("_s1"), domain="storage")
        registry.add(_make("_f2"), domain="factor")
        return registry

    def test_domains_groups_in_registration_order(self):
        assert self._registry().domains() == {
            "factor": ["_f1", "_f2"],
            "storage": ["_s1"],
        }

    def test_domain_names(self):
        assert self._registry().domain_names() == ["factor", "storage"]

    def test_filter_keeps_relative_order(self):
        registry = self._registry()
        assert registry.names(["factor"]) == ["_f1", "_f2"]
        assert list(registry.dispatch(["storage"])) == ["_s1"]

    def test_multiple_domains(self):
        assert self._registry().names(["storage", "factor"]) == ["_f1", "_s1", "_f2"]

    def test_unknown_domain_raises(self):
        """A typo in a domain name must fail loudly, not bind an empty toolset."""
        with pytest.raises(ValueError, match="unknown tool domain"):
            self._registry().bind(["faktor"])

    def test_no_filter_binds_everything(self):
        assert len(self._registry().bind()) == 3
