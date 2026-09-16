"""Agent tool adapters, split by capability domain.

Each module exposes ``register(registry, deps)`` and defines its adapters with
``@registry.tool("<domain>")``.  An adapter is a thin, typed shim between the
model's JSON arguments and the business services in :mod:`src.agent.deps`:

* it takes and returns JSON-friendly values, because that is what the model
  sends and reads;
* it delegates the actual work to ``src.tools.*`` / ``src.core.*``, which stay
  free of any agent concerns.

``build_registry`` composes the modules and is the only place that knows the
tool inventory.  The order of the ``register`` calls below determines the order
of the tool list bound to the model.
"""

from __future__ import annotations

from src.agent.adapters import (
    backtest,
    calendar,
    data,
    factor,
    fundamental,
    market_data,
    news,
    optimize,
    position,
    selection,
    signal,
    stoploss,
    storage,
    strategy,
)
from src.agent.deps import AgentDeps
from src.agent.registry import ToolRegistry

# Modules in tool-registration order. Kept explicit rather than discovered by
# scanning, so the tool list bound to the model can never change by accident.
_MODULES = (
    factor,
    strategy,
    backtest,
    storage,
    selection,
    position,
    optimize,
    stoploss,
    calendar,
    market_data,
    fundamental,
    signal,
    news,
    data,
)


def build_registry(deps: AgentDeps) -> ToolRegistry:
    """Build the agent's tool registry from every domain module."""
    registry = ToolRegistry()
    for module in _MODULES:
        module.register(registry, deps)
    return registry


__all__ = ["build_registry"]
