"""Agent tools — public API."""

from src.tools.factor_tools import create_factor, search_factors
from src.tools.strategy_tools import compose_strategy
from src.tools.backtest_tools import analyze_backtest, run_backtest
from src.tools.storage_tools import list_strategies, load_strategy, save_strategy, search_strategies
from src.tools.comparison_tools import compare_strategies, update_strategy
from src.tools.selection_tools import select_stocks
from src.tools.position_tools import get_portfolio_status, save_holdings, save_position_rules
from src.tools.optimize_tools import optimize_parameters
from src.tools.stoploss_tools import add_stoploss_rules, check_stoploss_scenarios, run_backtest_with_stoploss
from src.tools.calendar_tools import get_current_date, resolve_relative_date, get_trading_days
from src.tools.data_tools import check_data_coverage

__all__ = [
    # Factor tools
    "search_factors",
    "create_factor",
    # Strategy tools
    "compose_strategy",
    # Backtest tools
    "run_backtest",
    "analyze_backtest",
    # Storage tools
    "save_strategy",
    "load_strategy",
    "list_strategies",
    "search_strategies",
    # Comparison tools
    "compare_strategies",
    "update_strategy",
    # Selection tools
    "select_stocks",
    # Position tools
    "save_holdings",
    "get_portfolio_status",
    "save_position_rules",
    # Optimization tools
    "optimize_parameters",
    # Stop-loss tools
    "add_stoploss_rules",
    "run_backtest_with_stoploss",
    "check_stoploss_scenarios",
    # Calendar tools
    "get_current_date",
    "resolve_relative_date",
    "get_trading_days",
    # Data tools
    "check_data_coverage",
]
