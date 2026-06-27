"""API request/response schemas."""

from pydantic import BaseModel, Field


# ── Factor Schemas ────────────────────────────────────────────────


class FactorSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=5, ge=1, le=50)


class FactorCreateRequest(BaseModel):
    id: str = Field(min_length=1, max_length=50, pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=500)
    category: str
    formula: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)


# ── Strategy Schemas ──────────────────────────────────────────────


class StrategyComposeRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    factor_ids: list[str] = Field(min_length=1)
    start_date: str
    end_date: str
    factor_weights: dict[str, float] = Field(default_factory=dict)
    selection_rule: str = Field(default="top_k")
    selection_params: dict = Field(default_factory=lambda: {"k": 10})
    weight_scheme: str = Field(default="equal")
    rebalance_freq: str = Field(default="monthly")
    universe: str = Field(default="csi300")
    max_holding: int = Field(default=10, ge=1, le=100)
    benchmark: str = Field(default="SH000300")


class StrategySaveRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    config: dict
    description: str = ""
    agent_summary: str = ""
    version: int = Field(default=1, ge=1)
    parent_id: str | None = None


class StrategyUpdateRequest(BaseModel):
    modifications: dict
    agent_summary: str = ""


class StrategyCompareRequest(BaseModel):
    strategy_ids: list[str] = Field(min_length=2, max_length=10)


# ── Backtest Schemas ──────────────────────────────────────────────


class BacktestRequest(BaseModel):
    strategy_config: dict


class BacktestAnalyzeRequest(BaseModel):
    backtest_result: dict


# ── Selection Schemas ─────────────────────────────────────────────


class SelectionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    factor_ids: list[str] = Field(min_length=1)
    top_k: int = Field(default=50, ge=1, le=500)
    factor_weights: dict[str, float] = Field(default_factory=dict)
    filter_conditions: list[dict] = Field(default_factory=list)
    universe: str = Field(default="csi300")
    date: str


# ── Portfolio Schemas ─────────────────────────────────────────────


class HoldingsSaveRequest(BaseModel):
    session_id: str
    holdings: list[dict]


class PositionRulesSaveRequest(BaseModel):
    session_id: str
    rules: list[dict]


# ── Calendar Schemas ──────────────────────────────────────────────


class ResolveDateRequest(BaseModel):
    expression: str = Field(min_length=1)
    reference_date: str = ""


# ── Chat Schemas ─────────────────────────────────────────────────


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    session_id: str = ""
