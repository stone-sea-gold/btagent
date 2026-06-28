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


# ── Stock Selection Models ────────────────────────────────────────


class FilterOperator(str, Enum):
    """Filter comparison operators."""
    LT = "lt"
    LE = "le"
    GT = "gt"
    GE = "ge"
    EQ = "eq"
    BETWEEN = "between"


class ScoreStageConfig(BaseModel):
    """First stage: score and rank stocks by weighted factors."""
    factor_ids: list[str] = Field(min_length=1)
    factor_weights: dict[str, float] = Field(default_factory=dict)
    top_k: int = Field(default=50, ge=1, le=500)


class FilterCondition(BaseModel):
    """A single filter condition."""
    factor_id: str
    operator: FilterOperator
    value: float | None = None
    value_min: float | None = None
    value_max: float | None = None


class FilterStageConfig(BaseModel):
    """Second stage: filter stocks by conditions."""
    conditions: list[FilterCondition] = Field(min_length=1)


class StockSelectionConfig(BaseModel):
    """Full stock selection pipeline configuration."""
    name: str = Field(description="Selection name")
    universe: str = Field(default="csi300")
    score_stage: ScoreStageConfig
    filter_stages: list[FilterStageConfig] = Field(default_factory=list)
    date: str = Field(description="Evaluation date (YYYY-MM-DD)")


class SelectedStock(BaseModel):
    """A single stock in the selection result."""
    code: str
    name: str = ""
    composite_score: float
    factor_scores: dict[str, float] = Field(default_factory=dict)


class StockSelectionResult(BaseModel):
    """Stock selection result."""
    id: str
    config_name: str
    universe: str
    date: str
    total_scored: int
    total_selected: int
    stocks: list[SelectedStock]
    created_at: datetime = Field(default_factory=datetime.now)


# ── Position Management Models ────────────────────────────────────


class HoldingRecord(BaseModel):
    """A single stock holding."""
    stock_code: str
    stock_name: str = ""
    quantity: int = Field(ge=0)
    cost_price: float = Field(gt=0)
    current_price: float = Field(gt=0)
    market_value: float = Field(ge=0)
    pnl: float = 0.0
    pnl_pct: float = 0.0
    industry: str = ""
    weight: float = Field(default=0.0, ge=0.0, le=1.0)


class RuleType(str, Enum):
    """Position management rule types."""
    SINGLE_STOCK_LIMIT = "single_stock_limit"
    TOTAL_POSITION_LIMIT = "total_position_limit"
    INDUSTRY_LIMIT = "industry_limit"  # reserved for future


class PositionRule(BaseModel):
    """A position management rule."""
    rule_type: RuleType
    max_weight: float = Field(gt=0.0, le=1.0, description="Max weight as fraction (e.g., 0.1 = 10%)")
    scope: str = Field(default="", description="Industry name for industry_limit, empty otherwise")


class PositionViolation(BaseModel):
    """A rule violation detected in the portfolio."""
    rule_type: RuleType
    stock_code: str = ""
    industry: str = ""
    current_weight: float
    max_weight: float
    excess: float = Field(description="How much over the limit")
    message: str


# ── Parameter Optimization Models ─────────────────────────────────


class OptunaSearchMethod(str, Enum):
    """Parameter optimization search methods."""
    GRID = "grid"
    BAYESIAN = "bayesian"


class ParamRange(BaseModel):
    """A single parameter search range."""
    name: str = Field(description="Parameter path, e.g. 'selection_params.k'")
    low: float
    high: float
    step: float | None = Field(default=None, description="Step size for grid search")
    is_int: bool = Field(default=False, description="Round to integer")


class OptimizationConfig(BaseModel):
    """Parameter optimization configuration."""
    strategy_id: str = Field(description="Base strategy to optimize")
    method: OptunaSearchMethod
    param_ranges: list[ParamRange] = Field(min_length=1, max_length=10)
    metric: str = Field(default="sharpe_ratio", description="Metric to maximize")
    n_trials: int = Field(default=50, ge=5, le=500)
    start_date: str
    end_date: str
    overfit_warning_shown: bool = Field(default=False)


class OptimizationTrial(BaseModel):
    """Result of a single optimization trial."""
    trial_id: int
    params: dict[str, float]
    metric_value: float
    strategy_id: str = ""
    backtest_id: str = ""


class OptimizationResult(BaseModel):
    """Complete optimization result."""
    id: str
    config: OptimizationConfig
    best_params: dict[str, float]
    best_metric: float
    best_strategy_id: str
    trials: list[OptimizationTrial]
    total_trials: int
    overfit_warning: str = ""
    created_at: datetime = Field(default_factory=datetime.now)


# ── Stop-Loss Models ──────────────────────────────────────────────


class StopLossType(str, Enum):
    """Stop-loss rule types."""
    FIXED = "fixed"
    TRAILING = "trailing"
    MAX_DRAWDOWN = "max_drawdown"


class StopLossRule(BaseModel):
    """A stop-loss rule configuration."""
    rule_type: StopLossType
    threshold: float = Field(description="Percentage threshold (e.g., 0.08 = 8%)")
    scope: str = Field(default="portfolio", description="'portfolio' or stock_code")


class StopLossEvent(BaseModel):
    """Record of a stop-loss trigger."""
    rule_type: StopLossType
    stock_code: str = ""
    trigger_date: str
    trigger_price: float = 0.0
    peak_price: float = 0.0
    loss_pct: float
    action_taken: str = Field(description="e.g. 'sold 600519' or 'portfolio closed'")


# ── Multi-Market Placeholder ──────────────────────────────────────


class MarketType(str, Enum):
    """Supported market types."""
    A_SHARE = "a_share"
    # Future: HK = "hk", US = "us"


class MarketConfig(BaseModel):
    """Market-specific configuration (placeholder for multi-market)."""
    market: MarketType = Field(default=MarketType.A_SHARE)
    exchange: str = Field(default="SSE")
    currency: str = Field(default="CNY")
    trading_calendar: str = Field(default="china")


# ── LLM Settings Models ────────────────────────────────────────────


class LLMConfig(BaseModel):
    """User-overrideable LLM configuration."""
    provider: str = Field(default="custom", description="Provider label shown in UI")
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    is_active: bool = Field(default=True)
