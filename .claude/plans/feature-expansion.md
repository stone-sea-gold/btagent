# AIFUND5 功能扩展实施计划

## Context

AIFUND5 当前是一个深度绑定 Qlib 的量化回测系统，数据来源单一（仅 Qlib）、选股方式单一（仅因子打分）、止损类型有限（3 种）、回测分析过于简单。本计划基于 [finance-quant-skills](https://github.com/lzwme/finance-quant-skills) 项目的参考价值，整合 5 项改进（排除 backtrader 引擎），在不破坏现有架构的前提下增强系统能力。

**核心设计原则：**
- 所有新增功能作为**独立 Tool** 接入，不修改现有 Qlib 回测管道
- 严格遵循项目现有的三层绑定模式（Tool函数 → graph闭包 → Agent注册）
- 外部 API 调用必须设置超时，失败时优雅降级
- 零配置优先：akshare/baostock/止损改进无需用户额外操作

---

## 架构总览

```
┌─────────────────────────────────────────────────────────┐
│                    Agent Layer (graph.py)                │
│  ┌─────────────┐ ┌──────────────┐ ┌───────────────────┐ │
│  │ 现有 23 个   │ │ 新增数据工具  │ │ 新增选股/分析工具 │ │
│  │ Tools       │ │ akshare_*    │ │ wencai_screen     │ │
│  │             │ │ baostock_*   │ │ analyze_report    │ │
│  └──────┬──────┘ └──────┬───────┘ └────────┬──────────┘ │
│         │               │                  │            │
│  ┌──────▼───────────────▼──────────────────▼──────────┐ │
│  │           system.md 路由指令                        │ │
│  │  因子选股 → select_stocks (Qlib)                    │ │
│  │  自然语言选股 → wencai_screen (问财)                │ │
│  │  数据查询 → akshare_*/baostock_*                    │ │
│  │  回测分析 → analyze_backtest + LLM 结构化报告       │ │
│  └────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────┐
│              Core Layer (现有，不修改管道)                 │
│  StrategyConfig → StrategyCompiler → BacktestEngine(Qlib)│
│  FactorStore → StockSelector(Qlib D.features)            │
│  StopLossEngine (扩展)                                   │
└─────────────────────────────────────────────────────────┘
```

**关键约束：** 现有 Qlib 回测管道（StrategyConfig → StrategyCompiler → BacktestEngine）**完全不改动**。新增的数据工具和选股工具作为并行通道接入 Agent。

---

## Phase 1: 止损策略丰富（零外部依赖，改现有代码）

### 1.1 扩展模型 — `src/core/models.py`

在 `StopLossType` 枚举中新增 3 个类型：

```python
class StopLossType(str, Enum):
    FIXED = "fixed"
    TRAILING = "trailing"
    MAX_DRAWDOWN = "max_drawdown"
    ATR = "atr"                    # 新增：ATR 止损
    TIME = "time"                  # 新增：持仓时间止损
    PROFIT_TRAILING = "profit_trailing"  # 新增：盈利回撤止损
```

扩展 `StopLossRule`：

```python
class StopLossRule(BaseModel):
    rule_type: StopLossType
    threshold: float = Field(description="Percentage threshold (e.g., 0.08 = 8%)")
    scope: str = Field(default="portfolio", description="'portfolio' or stock_code")
    atr_period: int = Field(default=14, description="ATR 计算周期（仅 ATR 止损用）")
    atr_multiplier: float = Field(default=2.0, description="ATR 倍数（仅 ATR 止损用）")
    max_holding_days: int = Field(default=0, description="最大持仓天数（仅时间止损用）")
    profit_trigger_pct: float = Field(default=0.1, description="盈利触发比例（仅盈利回撤止损用）")
    profit_drawback_pct: float = Field(default=0.05, description="盈利回撤比例（仅盈利回撤止损用）")
```

> **向后兼容：** 新增字段全部有默认值，现有 StopLossRule 构造不受影响。

### 1.2 扩展引擎 — `src/core/stoploss_engine.py`

在 `evaluate_day()` 方法签名中新增可选参数：

```python
def evaluate_day(
    self, date, portfolio_value, holdings, prices,
    peak_values, cost_prices, rules,
    portfolio_peak_value=0.0,
    atr_values: dict[str, float] | None = None,      # 新增
    holding_days: dict[str, int] | None = None,        # 新增
    cost_prices_for_profit: dict[str, float] | None = None,  # 新增
) -> list[StopLossEvent]:
```

新增 3 个私有方法：
- `_check_atr_stop()` — 当前价 < 买入价 - ATR × multiplier 时触发
- `_check_time_stop()` — 持仓天数 >= max_holding_days 时触发
- `_check_profit_trailing()` — 浮盈超过 profit_trigger_pct 后，从最高盈利点回落 profit_drawback_pct 时触发

> **向后兼容：** 新增参数全部默认 None，不传时行为与现有完全一致。

### 1.3 更新场景描述 — `src/tools/stoploss_tools.py`

在 `check_stoploss_scenarios()` 的 if-elif 链中新增 3 个分支，返回对应的中文描述。

### 1.4 更新系统提示 — `src/agent/prompts/system.md`

在「止损工作流」部分更新：三种类型 → 六种类型，补充 ATR/时间/盈利回撤的说明。

### 1.5 验证

- 运行现有测试 `pytest tests/test_stoploss_engine.py` 确保不破坏
- 新增测试覆盖 3 种新止损类型的触发/不触发场景
- 测试参数默认值的向后兼容性

---

## Phase 2: 数据源接入 — akshare（零配置）

### 2.1 依赖管理 — `pyproject.toml`

在 dependencies 中新增：
```
"akshare>=1.14.0",
```

### 2.2 异常类 — `src/exceptions.py`

新增数据源异常层级（不影响现有异常）：

```python
class DataSourceError(AIFundError):
    """Errors related to external data source operations."""

class DataSourceTimeoutError(DataSourceError):
    """Data source request timed out."""

class DataSourceUnavailableError(DataSourceError):
    """Data source is temporarily unavailable."""
```

### 2.3 数据工具 — `src/tools/market_data_tools.py`（新文件）

遵循项目 Tool 模式：`dict` 返回值、`try/except` 返回 `{"error": ..., "status": "error"}`。

提供以下工具函数：

| 函数 | 功能 | 超时 |
|---|---|---|
| `fetch_stock_quote(symbol)` | 个股实时行情（最新价、涨跌幅、成交量） | 10s |
| `fetch_stock_hist(symbol, start, end, period, adjust)` | 历史 K 线数据 | 15s |
| `fetch_financial_summary(symbol)` | 基本面摘要（PE/PB/ROE/市值等） | 10s |
| `fetch_northbound_flow(date)` | 北向资金流入流出 | 10s |
| `fetch_sector_flow(date)` | 行业板块资金流向 | 10s |
| `fetch_top_list(date)` | 龙虎榜数据 | 10s |

所有 akshare 调用通过 `functools.partial` + `concurrent.futures.ThreadPoolExecutor` 实现超时控制。akshare 是同步库，用线程池包装超时。

错误处理模式：
```python
try:
    df = ak.stock_zh_a_spot_em()
    # 转换为 dict list
    return {"data": records, "count": len(records), "status": "success"}
except Exception as e:
    logger.error("akshare_fetch_error", error=str(e))
    return {"error": f"数据获取失败: {e}", "status": "error"}
```

### 2.4 注册 Agent Tool — `src/agent/graph.py`

按现有三层绑定模式：
- Step A: `from src.tools.market_data_tools import fetch_stock_quote as _fetch_stock_quote_fn` 等
- Step B: 在 `create_agent_graph()` 中定义闭包（无服务依赖，直接透传）
- Step C: 加入 `tools` 列表和 `tool_func_map`

### 2.5 系统提示 — `src/agent/prompts/system.md`

新增「市场数据」分类：

```markdown
### 市场数据
- **fetch_stock_quote**: 获取个股实时行情（最新价、涨跌幅、成交量、换手率）
- **fetch_stock_hist**: 获取历史 K 线数据（日/周/月线，前复权/后复权）
- **fetch_financial_summary**: 获取个股基本面摘要（PE、PB、ROE、市值等）
- **fetch_northbound_flow**: 获取北向资金流入流出数据
- **fetch_sector_flow**: 获取行业板块资金流向
- **fetch_top_list**: 获取龙虎榜数据

当用户询问个股行情、财务数据、资金流向等信息时，使用上述工具获取实时数据。
注意：这些工具返回的是查询/展示数据，不直接进入回测管道。
```

### 2.6 API 路由 — `src/api/routes/market_data.py`（新文件）

GET 端点：
- `GET /api/market-data/quote?symbol=600519`
- `GET /api/market-data/history?symbol=600519&start=20240101&end=20241231`
- `GET /api/market-data/northbound?date=20241201`

在 `src/api/app.py` 注册路由。

### 2.7 验证

- 新增 `tests/test_market_data_tools.py`，mock akshare 调用
- 测试超时处理、空数据处理、网络异常处理
- 测试返回格式一致性

---

## Phase 3: 数据源接入 — baostock（零配置）

### 3.1 依赖管理 — `pyproject.toml`

```
"baostock>=0.8.8",
```

### 3.2 数据工具 — `src/tools/market_data_tools.py`（同文件扩展）

在同一文件中新增 baostock 函数：

| 函数 | 功能 | 超时 |
|---|---|---|
| `fetch_quarterly_financials(symbol, year, quarter)` | 季度财务指标（ROE/净利润率/毛利率等） | 15s |
| `fetch_industry_stocks(industry)` | 按行业获取股票列表 | 10s |
| `fetch_index_constituents(index)` | 指数成分股列表（沪深300/中证500等） | 10s |

baostock 需要 `bs.login()` / `bs.logout()` 会话管理。使用 context manager 模式：

```python
from contextlib import contextmanager

@contextmanager
def _baostock_session():
    import baostock as bs
    bs.login()
    try:
        yield bs
    finally:
        bs.logout()
```

### 3.3 注册、系统提示、API 路由

与 Phase 2 相同模式，扩展同一组文件。

### 3.4 验证

- 新增测试覆盖 baostock 函数
- 测试 login/logout 会话管理的异常安全性

---

## Phase 4: pywencai 自然语言选股（需要同花顺 Cookie）

### 4.1 依赖管理 — `pyproject.toml`

```
"pywencai>=0.3.0",
```

### 4.2 配置 — `src/config.py`

新增配置字段（默认空字符串，不影响启动）：

```python
# pywencai (同花顺问财)
wencai_cookie: str = ""
```

### 4.3 选股工具 — `src/tools/wencai_tools.py`（新文件）

```python
def wencai_screen(query: str, top_k: int = 50) -> dict:
    """自然语言选股（同花顺问财）。

    Args:
        query: 中文自然语言选股条件，如 "ROE大于15%且营收增速超过20%"
        top_k: 返回前 N 只股票

    Returns:
        股票列表 dict。
    """
```

关键设计点：
- Cookie 从 `settings.wencai_cookie` 读取
- Cookie 为空时返回明确错误信息 + 配置指引
- 调用间隔强制 ≥ 2 秒（用 `time.monotonic()` 控制）
- 返回格式对齐 `StockSelectionResult` 的结构（code、name），但不包含 composite_score（因为问财不提供打分）

返回格式：
```python
{
    "query": "ROE大于15%的股票",
    "stocks": [
        {"code": "600519", "name": "贵州茅台"},
        {"code": "000858", "name": "五粮液"},
    ],
    "total": 50,
    "source": "wencai",
    "status": "success",
}
```

### 4.4 注册 Agent Tool — `src/agent/graph.py`

同三层绑定模式。闭包中无服务依赖。

### 4.5 系统提示 — `src/agent/prompts/system.md`

在「选股」分类下新增：

```markdown
- **wencai_screen**: 自然语言选股（通过同花顺问财搜索引擎）
  - 适用场景：用户用自然语言描述选股条件，如"ROE大于15%且PE低于20"
  - 与 select_stocks 的区别：select_stocks 基于因子打分，wencai_screen 基于自然语言
  - 需要配置同花顺 Cookie（WENCAI_COOKIE 环境变量）
```

新增路由指令：
```markdown
### 选股路由规则
- 用户明确指定因子 ID 或要求因子打分 → 使用 select_stocks
- 用户用自然语言描述条件（如"低估值高分红"）→ 使用 wencai_screen
- 不确定时，优先使用 wencai_screen（门槛更低）
```

### 4.6 API 路由 — `src/api/routes/wencai.py`（新文件）

```python
POST /api/wencai/screen
Body: { "query": "ROE大于15%", "top_k": 50 }
```

### 4.7 验证

- 新增 `tests/test_wencai_tools.py`
- 测试 Cookie 为空时的优雅降级
- 测试调用频率限制
- Mock pywencai 返回值测试解析逻辑

---

## Phase 5: 回测分析报告升级（复用现有 LLM，无新依赖）

### 5.1 设计决策

**不在 Tool 内部调用 LLM。** 原因：
- `analyze_backtest` 当前是同步纯函数，引入 LLM 调用会改变其性质
- Agent 本身就是 LLM 驱动的，可以在获取 `analyze_backtest` 结果后自行生成深度报告

**方案：** 增强 `analyze_backtest` 的输出结构化程度 + 在 system.md 中新增报告生成框架。

### 5.2 增强分析函数 — `src/tools/backtest_tools.py`

改造 `analyze_backtest()` 函数，从简单指标罗列升级为结构化输出：

```python
def analyze_backtest(backtest_result: dict) -> str:
    """Generate structured analysis of backtest results.

    Returns Markdown with sections:
    1. 策略概述（策略名称、参数、回测区间）
    2. 收益分析（总收益、年化、与基准对比）
    3. 风险分析（最大回撤、波动率、回撤持续期）
    4. 效率指标（夏普比率、胜率、盈亏比）
    5. 风险评级（综合评级 + 具体风险点）
    6. 改进建议（基于指标的可操作建议）
    """
```

新增逻辑：
- 计算 Calmar Ratio（年化收益 / 最大回撤）
- 计算收益回撤比
- 基于多维度指标给出综合风险评级（A/B/C/D）
- 生成可操作的改进建议（如"回撤过大，建议降低集中度"）

### 5.3 系统提示 — `src/agent/prompts/system.md`

新增「报告生成框架」：

```markdown
### 回测分析报告框架

当用户要求详细分析或生成报告时，基于 analyze_backtest 的结果，按以下框架组织：

1. **策略概述** — 策略名称、因子选择、回测区间、持仓数量、调仓频率
2. **收益分析** — 总收益、年化收益、与基准（沪深300）的超额收益
3. **风险分析** — 最大回撤、年化波动率、最长回撤期
4. **效率指标** — 夏普比率、Calmar 比率、胜率
5. **综合评级** — A(优秀)/B(良好)/C(一般)/D(不佳)
6. **改进建议** — 基于指标给出 2-3 条可操作建议

评级标准：
- A 级：夏普 > 1.5，回撤 < 15%，年化 > 15%
- B 级：夏普 > 0.8，回撤 < 25%
- C 级：夏普 > 0，回撤 < 35%
- D 级：夏普 < 0 或回撤 > 35%
```

### 5.4 验证

- 更新现有 `test_tools.py` 中 analyze_backtest 相关测试
- 测试各评级条件的边界值
- 测试缺失指标时的降级处理

---

## 修改文件清单

### 新增文件（6 个）
| 文件 | 说明 |
|---|---|
| `src/tools/market_data_tools.py` | akshare + baostock 数据工具 |
| `src/tools/wencai_tools.py` | pywencai 自然语言选股 |
| `src/api/routes/market_data.py` | 市场数据 API 路由 |
| `src/api/routes/wencai.py` | 问财选股 API 路由 |
| `tests/test_market_data_tools.py` | 数据工具测试 |
| `tests/test_wencai_tools.py` | 问财工具测试 |

### 修改文件（9 个）
| 文件 | 改动范围 | 风险 |
|---|---|---|
| `pyproject.toml` | 新增 3 个依赖 | 低 |
| `src/config.py` | 新增 `wencai_cookie` 字段 | 低（有默认值） |
| `src/exceptions.py` | 新增 `DataSourceError` 层级 | 低（纯新增） |
| `src/core/models.py` | 扩展 `StopLossType` + `StopLossRule` | 低（新字段有默认值） |
| `src/core/stoploss_engine.py` | 新增 3 个止损方法 + 扩展 `evaluate_day` 签名 | 中（签名变更） |
| `src/tools/stoploss_tools.py` | 新增 3 个场景描述分支 | 低 |
| `src/tools/backtest_tools.py` | 增强 `analyze_backtest` 输出 | 中（输出格式变化） |
| `src/agent/graph.py` | 注册新 Tools | 低（纯新增） |
| `src/agent/prompts/system.md` | 新增工具文档 + 路由规则 + 报告框架 | 低 |

### 不修改的文件（关键确认）
| 文件 | 原因 |
|---|---|
| `src/core/backtest_engine.py` | Qlib 管道不改动 |
| `src/core/strategy_compiler.py` | Qlib 编译器不改动 |
| `src/core/stock_selector.py` | 因子选股管道不改动 |
| `src/core/factor_store.py` | 因子存储不改动 |
| `src/core/param_optimizer.py` | 优化器不改动 |
| `src/api/dependencies.py` | 新工具无服务依赖，不需改 ServiceContainer |
| `src/api/middleware.py` | 错误处理已覆盖 AIFundError 基类 |

---

## 实施顺序

```
Phase 1 (止损)  ──► Phase 2 (akshare) ──► Phase 3 (baostock) ──► Phase 4 (pywencai) ──► Phase 5 (报告)
   │                    │                      │                     │                     │
   ▼                    ▼                      ▼                     ▼                     ▼
 models.py          pyproject.toml         同 Phase2            config.py            backtest_tools.py
 stoploss_engine    market_data_tools      扩展同一文件          wencai_tools.py      system.md
 stoploss_tools     graph.py               graph.py             graph.py
 system.md          system.md              system.md            system.md
 tests              routes/market_data     routes 扩展           routes/wencai
                    tests                  tests                tests
```

每个 Phase 完成后运行 `pytest` 确保不破坏现有功能。

---

## 验证策略

### 每个 Phase 的验证清单

1. **单元测试** — 新增 `tests/test_*.py`，覆盖 Happy Path + 错误处理
2. **向后兼容** — 运行 `pytest` 全量测试，确认无回归
3. **集成验证** — 启动 API 服务，通过 `/health` 确认启动正常
4. **手动验证** — 通过 Agent 对话测试新工具是否可用

### 关键测试场景

| 场景 | 期望行为 |
|---|---|
| akshare 网络超时 | 返回 `{"error": "数据获取超时", "status": "error"}` |
| baostock 未安装 | 返回明确的 `pip install baostock` 指引 |
| pywencai Cookie 为空 | 返回配置指引而非崩溃 |
| ATR 止损参数缺失 | 降级为不触发（None 时跳过） |
| analyze_backtest 输入无 metrics | 返回错误提示而非崩溃 |

---

## 生产级检查清单

- [x] **环境变量**: 新增的 `wencai_cookie` 通过 pydantic-settings 从 `.env` 加载，不硬编码
- [x] **输入校验**: 所有 Tool 函数参数通过 Pydantic 或 try/except 校验
- [x] **超时控制**: 所有外部 API 调用（akshare/baostock/pywencai）设置超时
- [x] **异常屏障**: 新增 `DataSourceError` 层级，被 middleware 统一捕获
- [x] **无状态设计**: 新 Tool 函数无内部状态，ServiceContainer 不新增服务
- [x] **日志脱敏**: structlog 关键字参数模式，无敏感信息泄露
- [x] **依赖安全**: akshare/baostock/pywencai 均为成熟开源库，有活跃维护
- [x] **单向依赖**: 新增代码 → 现有代码，无反向依赖
