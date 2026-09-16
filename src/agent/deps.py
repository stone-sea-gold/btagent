"""Dependencies the agent adapters close over.

``create_agent_graph`` used to take eight positional-ish parameters and thread
them through a 55-tool closure by hand.  Bundling them in one frozen record
means an adapter module receives a single object, and adding a dependency is a
one-line change instead of a signature change in several places.

These are the business services owned by the application layer; the agent only
reads them.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.core.backtest_engine import BacktestEngine
from src.core.factor_store import FactorStore
from src.core.param_optimizer import ParamOptimizer
from src.core.position_manager import PositionManager
from src.core.session_store import SessionStore
from src.core.stock_selector import StockSelector
from src.core.strategy_compiler import StrategyCompiler
from src.tools.storage_tools import StrategyStore


@dataclass(frozen=True)
class AgentDeps:
    """Business services the agent tools operate on."""

    factor_store: FactorStore
    strategy_compiler: StrategyCompiler
    backtest_engine: BacktestEngine
    strategy_store: StrategyStore
    session_store: SessionStore
    position_manager: PositionManager | None = None
    param_optimizer: ParamOptimizer | None = None
    stock_selector: StockSelector | None = None
