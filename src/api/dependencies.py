"""Application dependencies — service singletons.

All backend services are initialized once at startup and injected
into API routes via FastAPI's dependency injection system.
"""

from src.core.backtest_engine import BacktestEngine
from src.core.factor_store import FactorStore
from src.core.param_optimizer import ParamOptimizer
from src.core.position_manager import PositionManager
from src.core.session_store import SessionStore
from src.core.stock_selector import StockSelector
from src.core.strategy_compiler import StrategyCompiler
from src.tools.storage_tools import StrategyStore


class ServiceContainer:
    """Holds all backend service singletons."""

    def __init__(self):
        self.factor_store = FactorStore()
        self.factor_store.load_builtin_factors(force_update=True)
        self.strategy_compiler = StrategyCompiler(factor_store=self.factor_store)
        self.backtest_engine = BacktestEngine()
        self.strategy_store = StrategyStore()
        self.session_store = SessionStore()
        self.position_manager = PositionManager()
        self.param_optimizer = ParamOptimizer(
            strategy_compiler=self.strategy_compiler,
            backtest_engine=self.backtest_engine,
            strategy_store=self.strategy_store,
        )
        self.stock_selector = StockSelector(factor_store=self.factor_store)

    def close(self):
        """Clean up resources."""
        self.factor_store.close()
        self.backtest_engine.close()
        self.strategy_store.close()
        self.session_store.close()
        self.position_manager.close()


# Global singleton — initialized in app.py lifespan
_services: ServiceContainer | None = None


def get_services() -> ServiceContainer:
    """Get the global service container."""
    if _services is None:
        raise RuntimeError("Services not initialized. Call init_services() first.")
    return _services


def init_services() -> ServiceContainer:
    """Initialize the global service container."""
    global _services
    _services = ServiceContainer()
    return _services


def close_services():
    """Close the global service container."""
    global _services
    if _services:
        _services.close()
        _services = None
