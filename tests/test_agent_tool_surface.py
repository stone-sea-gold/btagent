"""Regression guard on the agent's tool surface.

The tool surface is the agent's public contract with the model, so it is pinned
here explicitly.  ``EXPECTED_INVENTORY`` is written out longhand rather than
derived from the code: a snapshot that recomputes itself from the source would
happily accept any change, including ones that silently drop a capability.

These tests use an ``AgentDeps`` holding ``None`` because registration only
closes over the services — no adapter is called.
"""

import pytest

from src.agent.adapters import build_registry
from src.agent.deps import AgentDeps

EXPECTED_INVENTORY = {
    "factor": [
        "_search_factors",
        "_create_factor",
    ],
    "strategy": [
        "_compose_strategy",
    ],
    "backtest": [
        "_run_backtest",
        "_analyze_backtest",
    ],
    "storage": [
        "_save_strategy",
        "_load_strategy",
        "_list_strategies",
        "_search_strategies",
        "_delete_strategy",
        "_compare_strategies",
        "_update_strategy",
        "_get_version_chain",
    ],
    "selection": [
        "_select_stocks",
    ],
    "position": [
        "_save_holdings",
        "_get_portfolio_status",
        "_save_position_rules",
    ],
    "optimize": [
        "_optimize_parameters",
    ],
    "stoploss": [
        "_add_stoploss_rules",
        "_run_backtest_with_stoploss",
        "_check_stoploss_scenarios",
    ],
    "calendar": [
        "_get_current_date",
        "_resolve_relative_date",
        "_get_trading_days",
        "_check_data_coverage",
    ],
    "market_data": [
        "_fetch_stock_quote",
        "_fetch_stock_hist",
        "_fetch_financial_summary",
        "_fetch_sector_flow",
        "_fetch_quarterly_financials",
        "_fetch_industry_stocks",
        "_fetch_index_constituents",
    ],
    "fundamental": [
        "_fetch_stock_reports",
        "_fetch_industry_reports",
        "_fetch_eps_forecast",
        "_fetch_valuation",
    ],
    "signal": [
        "_fetch_northbound_flow",
        "_fetch_concept_blocks",
        "_fetch_fund_flow",
        "_fetch_fund_flow_120d",
        "_fetch_dragon_tiger",
        "_fetch_daily_dragon_tiger",
        "_fetch_lockup_expiry",
        "_fetch_industry_ranking",
        "_fetch_margin_trading",
        "_fetch_block_trade",
        "_fetch_holder_change",
        "_fetch_dividend_history",
    ],
    "news": [
        "_fetch_stock_news",
        "_fetch_market_telegraph",
        "_fetch_global_news",
        "_fetch_announcements",
        "_fetch_hot_list",
        "_fetch_hot_rank",
        "_fetch_hot_concept",
    ],
    "data": [
        "_sync_market_data",
        "_export_qlib_dataset",
    ],
}

# Flat order exactly as it was bound before the registry existed.
EXPECTED_ORDER = [
    name for names in EXPECTED_INVENTORY.values() for name in names
]


def _deps() -> AgentDeps:
    """Dependencies are only captured by the adapters, never used at registration."""
    return AgentDeps(
        factor_store=None,
        strategy_compiler=None,
        backtest_engine=None,
        strategy_store=None,
        session_store=None,
    )


@pytest.fixture(scope="module")
def registry():
    return build_registry(_deps())


class TestInventory:
    def test_total_tool_count(self, registry):
        assert len(registry) == 57

    def test_domains_and_tools_match_snapshot(self, registry):
        assert registry.domains() == EXPECTED_INVENTORY

    def test_registration_order_preserved(self, registry):
        """Order determines the tool list sent to the model, so it must be stable."""
        assert registry.names() == EXPECTED_ORDER

    def test_every_tool_is_callable_and_documented(self, registry):
        for entry in registry.entries():
            assert callable(entry.func), entry.name
            # The docstring is the description the model reads.
            assert entry.description.strip(), entry.name

    def test_bind_and_dispatch_are_consistent(self, registry):
        bound = registry.bind()
        dispatch = registry.dispatch()
        assert [f.__name__ for f in bound] == list(dispatch)
        assert len(bound) == 57

    def test_domain_count(self, registry):
        assert len(registry.domain_names()) == 14


class TestDomainScoping:
    def test_subset_binds_only_that_domain(self, registry):
        assert registry.names(["factor"]) == ["_search_factors", "_create_factor"]

    def test_subset_preserves_relative_order(self, registry):
        names = registry.names(["backtest", "storage"])
        assert names == EXPECTED_INVENTORY["backtest"] + EXPECTED_INVENTORY["storage"]

    def test_unknown_domain_rejected(self, registry):
        with pytest.raises(ValueError, match="unknown tool domain"):
            registry.bind(["nonexistent"])
