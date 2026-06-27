"""Pydantic data models for AIFUND5.

These models serve as the contract between:
- Agent tools (input validation)
- Core business logic (internal data)
- Storage layer (persistence)
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


# ── Factor Models ──────────────────────────────────────────────────


class FactorCategory(str, Enum):
    """Factor classification categories."""
    MOMENTUM = "momentum"
    VALUE = "value"
    QUALITY = "quality"
    VOLATILITY = "volatility"
    SIZE = "size"
    LIQUIDITY = "liquidity"
    GROWTH = "growth"
    TECHNICAL = "technical"


class Factor(BaseModel):
    """A quant factor with its Qlib expression and metadata."""
    id: str = Field(description="Unique factor identifier (e.g., momentum_3m)")
    name: str = Field(description="Human-readable name")
    description: str = Field(description="What this factor measures")
    category: FactorCategory
    formula: str = Field(description="Qlib expression (e.g., Ref($close, 20) / Ref($close, 60) - 1)")
    parameters: dict = Field(default_factory=dict, description="Configurable parameters with defaults")
    tags: list[str] = Field(default_factory=list, description="Searchable tags")
    is_builtin: bool = Field(default=True, description="Whether this is a built-in factor")
    created_at: datetime = Field(default_factory=datetime.now)


class FactorCreate(BaseModel):
    """Input model for creating a new factor."""
    id: str = Field(min_length=1, max_length=50, pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=500)
    category: FactorCategory
    formula: str = Field(min_length=1)
    parameters: dict = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class FactorSearchResult(BaseModel):
    """Result from factor search (RAG + SQL bridge)."""
    factor: Factor
    score: float = Field(description="Relevance score (0-1)")
    source: str = Field(description="Match source: 'vector', 'sql', or 'bridge'")


# ── Strategy Models ────────────────────────────────────────────────


class SelectionRule(str, Enum):
    """Stock selection rules."""
    TOP_K = "top_k"
    PERCENTILE = "percentile"
    THRESHOLD = "threshold"


class WeightScheme(str, Enum):
    """Portfolio weight allocation schemes."""
    EQUAL = "equal"
    MARKET_CAP = "market_cap"
    FACTOR_SCORE = "factor_score"


class RebalanceFreq(str, Enum):
    """Rebalance frequency."""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class StrategyConfig(BaseModel):
    """Structured strategy configuration.

    This is the intermediate representation between Agent decisions
    and Qlib strategy execution. No Python code is generated —
    the StrategyCompiler maps this to Qlib objects deterministically.
    """
    name: str = Field(description="Strategy display name")
    factor_ids: list[str] = Field(min_length=1, description="Factor IDs to use")
    factor_weights: dict[str, float] = Field(
        default_factory=dict,
        description="Per-factor weights (default: equal)"
    )
    selection_rule: SelectionRule = Field(default=SelectionRule.TOP_K)
    selection_params: dict = Field(
        default_factory=lambda: {"k": 10},
        description="Parameters for selection rule (e.g., {'k': 10})"
    )
    weight_scheme: WeightScheme = Field(default=WeightScheme.EQUAL)
    rebalance_freq: RebalanceFreq = Field(default=RebalanceFreq.MONTHLY)
    universe: str = Field(default="csi300", description="Stock universe (csi300, csi500, all)")
    start_date: str = Field(description="Backtest start date (YYYY-MM-DD)")
    end_date: str = Field(description="Backtest end date (YYYY-MM-DD)")
    benchmark: str = Field(default="SH000300", description="Benchmark index code")
    max_holding: int = Field(default=10, ge=1, le=100, description="Max stocks to hold")


class StrategyRecord(BaseModel):
    """Persisted strategy with version chain and agent summary.

    Version chain: parent_id points to the previous version.
    Agent summary: auto-generated description for vector search embedding.
    """
    id: str = Field(description="Unique strategy ID (auto-generated)")
    config: StrategyConfig
    description: str = Field(default="", description="Natural language description for RAG search")
    agent_summary: str = Field(default="", description="Agent-generated summary for vector search")
    parent_id: str | None = Field(default=None, description="Previous version ID (version chain)")
    version: int = Field(default=1, ge=1, description="Version number")
    created_at: datetime = Field(default_factory=datetime.now)
    backtest_result_id: str | None = Field(default=None)


class SessionRecord(BaseModel):
    """Persisted agent session state."""
    session_id: str = Field(description="Unique session ID")
    name: str = Field(default="", description="Session display name")
    current_strategy_id: str | None = Field(default=None)
    current_backtest_id: str | None = Field(default=None)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


# ── Backtest Models ────────────────────────────────────────────────


class BacktestMetrics(BaseModel):
    """Key backtest performance metrics."""
    total_return: float = Field(description="Total cumulative return")
    annualized_return: float = Field(description="Annualized return")
    sharpe_ratio: float = Field(description="Sharpe ratio")
    max_drawdown: float = Field(description="Maximum drawdown")
    max_drawdown_duration: int = Field(description="Max drawdown duration in days")
    volatility: float = Field(description="Annualized volatility")
    win_rate: float = Field(description="Win rate (days with positive return)")
    turnover: float = Field(description="Average daily turnover")


class BacktestResult(BaseModel):
    """Complete backtest result."""
    id: str = Field(description="Unique result ID")
    strategy_id: str
    metrics: BacktestMetrics
    equity_curve: list[dict] = Field(
        default_factory=list,
        description="Daily equity curve [{'date': ..., 'value': ...}]"
    )
    holdings_history: list[dict] = Field(
        default_factory=list,
        description="Daily holdings"
    )
    created_at: datetime = Field(default_factory=datetime.now)
    is_cached: bool = Field(default=False, description="Whether this was returned from cache")


# ── Agent Session Models ──────────────────────────────────────────


class ToolCallRecord(BaseModel):
    """Record of a single tool call within a session."""
    tool_name: str
    input_params: dict
    output_summary: str
    duration_ms: float
    timestamp: datetime = Field(default_factory=datetime.now)
    success: bool = True
    error: str | None = None


class SessionState(BaseModel):
    """Mutable state for an agent session.

    Tracks the current strategy being built/modified,
    decision history, and backtest results.
    """
    session_id: str
    current_strategy: StrategyConfig | None = None
    current_backtest: BacktestResult | None = None
    decision_log: list[ToolCallRecord] = Field(default_factory=list)
    conversation_history: list[dict] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
