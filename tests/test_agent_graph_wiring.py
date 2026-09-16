"""Wiring tests for the agent graph and its module-level helpers.

``create_agent_graph`` is the agent's entry point, so its topology and the
behaviour of the helpers it delegates to are pinned here.  The graph is built
with dependencies set to ``None``: registration only closes over them, and the
model is not called.
"""

import json

import pytest

pytest.importorskip("langgraph", reason="langgraph is required to build the graph")
pytest.importorskip("langchain_core", reason="langchain_core is required to build the graph")

from langchain_core.messages import AIMessage  # noqa: E402
from langgraph.graph import END  # noqa: E402

from src.agent import graph as graph_mod  # noqa: E402
from src.agent.deps import AgentDeps  # noqa: E402


def _deps() -> AgentDeps:
    return AgentDeps(
        factor_store=None,
        strategy_compiler=None,
        backtest_engine=None,
        strategy_store=None,
        session_store=None,
    )


def _edge_pairs(compiled) -> set[tuple[str, str]]:
    """(source, target) pairs of the compiled graph.

    Goes through the public ``get_graph()`` view and reads ``source``/``target``
    so it works regardless of how the bundled langgraph version models edges.
    """
    view = compiled.get_graph() if hasattr(compiled, "get_graph") else compiled
    pairs = set()
    for edge in view.edges:
        source = getattr(edge, "source", None)
        target = getattr(edge, "target", None)
        if source is None or target is None:
            source, target = edge[0], edge[1]
        pairs.add((source, target))
    return pairs


@pytest.fixture(scope="module")
def compiled():
    return graph_mod.create_agent_graph(
        factor_store=None,
        strategy_compiler=None,
        backtest_engine=None,
        strategy_store=None,
        session_store=None,
        checkpointer=None,
    )


class TestTopology:
    def test_graph_compiles(self, compiled):
        assert compiled is not None

    def test_has_the_two_react_nodes(self, compiled):
        assert {"agent", "tools"} <= set(compiled.nodes)

    def test_tools_loops_back_to_agent(self, compiled):
        """Without this edge the agent could only ever call tools once."""
        assert ("tools", "agent") in _edge_pairs(compiled)

    def test_agent_routes_to_tools_or_end(self, compiled):
        pairs = _edge_pairs(compiled)
        assert ("agent", "tools") in pairs
        assert ("agent", END) in pairs


class TestDomainScoping:
    def test_unknown_domain_fails_loudly(self):
        with pytest.raises(ValueError, match="unknown tool domain"):
            graph_mod.create_agent_graph(
                factor_store=None,
                strategy_compiler=None,
                backtest_engine=None,
                strategy_store=None,
                session_store=None,
                domains=["not_a_domain"],
            )

    def test_registered_domains_build(self):
        graph = graph_mod.create_agent_graph(
            factor_store=None,
            strategy_compiler=None,
            backtest_engine=None,
            strategy_store=None,
            session_store=None,
            domains=["factor", "backtest"],
        )
        assert graph is not None


class TestLLMErrorHint:
    """Provider errors are mapped to actionable Chinese guidance."""

    @pytest.mark.parametrize(
        "message,expected",
        [
            ("Error code: 401 - unauthorized", "API Key"),
            ("402 insufficient_quota", "额度"),
            ("403 Forbidden", "权限"),
            ("404 not found", "端点"),
            ("Request timeout", "超时"),
            ("rate limit reached", "频率"),
            ("at least one message", "协议"),
        ],
    )
    def test_known_errors(self, message, expected):
        assert expected in graph_mod._llm_error_hint(message)

    def test_unknown_error_falls_back_and_truncates(self):
        hint = graph_mod._llm_error_hint("x" * 500)
        assert hint.startswith("LLM 调用失败")
        assert len(hint) <= 220


class TestNormalizeContent:
    def test_flattens_text_blocks(self):
        message = AIMessage(
            content=[{"type": "text", "text": "hello"}, {"type": "thinking", "thinking": "hmm"}]
        )
        graph_mod._normalize_content(message)
        assert message.content == "hello\nhmm"

    def test_leaves_plain_string_untouched(self):
        message = AIMessage(content="plain")
        graph_mod._normalize_content(message)
        assert message.content == "plain"


class TestSessionContext:
    """Session context is derived only from tools with an unambiguous contract."""

    def test_compose_strategy_populates_current_strategy(self):
        payload = json.dumps({"name": "s", "factor_ids": ["momentum_3m"]})
        assert graph_mod._session_context("_compose_strategy", payload) == {
            "current_strategy": {"name": "s", "factor_ids": ["momentum_3m"]}
        }

    def test_run_backtest_populates_last_result(self):
        payload = json.dumps({"sharpe_ratio": 1.5})
        assert graph_mod._session_context("_run_backtest", payload) == {
            "last_backtest_result": {"sharpe_ratio": 1.5}
        }

    def test_other_tools_contribute_nothing(self):
        assert graph_mod._session_context("_list_strategies", "[]") == {}

    def test_error_payload_ignored(self):
        payload = json.dumps({"error": "boom", "status": "error"})
        assert graph_mod._session_context("_compose_strategy", payload) == {}

    def test_malformed_json_ignored_rather_than_raising(self):
        assert graph_mod._session_context("_compose_strategy", "not json") == {}


class TestLLMCache:
    def test_invalidate_clears_both_slots(self):
        graph_mod._llm_cache["key"] = ("model", "key", "url")
        graph_mod._llm_cache["instance"] = object()
        graph_mod.invalidate_llm_cache()
        assert graph_mod._llm_cache["key"] is None
        assert graph_mod._llm_cache["instance"] is None
