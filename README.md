# AIFUND5 — A 股量化投资助手

面向个人投资者的 **Agent-native** 量化投资系统。通过自然语言与 AI Agent 交互，完成因子搜索、策略构建、回测分析、选股筛选、仓位管理等全流程量化投资任务。

## 特性

- **🤖 Agent-native 架构** — LangGraph 编排的 AI Agent 拥有 57 个工具、14 个能力域，自动执行复杂量化任务
- **🔍 因子管理** — 搜索内置因子库（109+ 因子），或创建自定义因子
- **📈 策略构建与回测** — 组合因子构建策略，一键回测并获取夏普比率、最大回撤等指标
- **💾 策略持久化** — SQLite + ChromaDB 双存储，支持语义搜索和版本链
- **📊 选股分析** — 多级选股管线（因子打分 + 条件筛选）
- **💰 仓位管理** — 持仓保存、规则检查、违规预警
- **⚙️ 参数优化** — 网格搜索 / 贝叶斯优化，附带过拟合警告
- **🛡️ 止损设置** — 固定止损、追踪止损、最大回撤熔断
- **🔄 策略迭代** — 版本链管理，策略对比，增量修改
- **🌐 Web UI + CLI** — 支持浏览器对话和命令行两种交互方式
- **🗄️ 自建A股数据层** — baostock/pytdx/akshare 多源适配，统一规范落盘 DuckDB，`$change` 与交易所官方涨跌幅在 74,409 个交易日观测上最大偏差 0.0002pp

## 技术栈

| 层级 | 技术 |
|------|------|
| Agent 编排 | LangGraph |
| LLM | 支持 DeepSeek / Anthropic / OpenAI / 千问 / Kimi / GLM / MiniMax / MIMO 等 |
| 数据源 | BaoStock（官方 SDK，主）· pytdx（TDX 协议，批量）· AKShare（兜底） |
| 行情仓库 | DuckDB（不复权原始价 + 复权因子分表，回测只读本地） |
| 回测引擎 | Qlib (Microsoft) |
| 因子/策略存储 | SQLite + ChromaDB（语义检索） |
| 后端 API | FastAPI |
| 前端 | React + Vite + Tailwind CSS |
| AI 前端 SDK | Vercel AI SDK (`useChat`) |
| 日志 | structlog (JSON) |
| 配置 | pydantic-settings (.env) |

## 快速开始

### 前置条件

- Python ≥ 3.10
- Node.js ≥ 18
- 一个 LLM API Key（DeepSeek / Anthropic / OpenAI 等）

### 1. 克隆并安装后端

```bash
git clone https://github.com/stone-sea-gold/btagent.git
cd AIFUND5

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# 安装依赖
pip install -e .
```

### 2. 配置 LLM

```bash
cp .env.example .env
```

编辑 `.env`，填入你的 API Key：

```ini
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-your-key-here
DEEPSEEK_BASE_URL=https://api.deepseek.com/anthropic
```

支持任意 OpenAI / Anthropic 兼容 API，详见下方 [LLM 配置](#llm-配置)。

### 3. 同步行情数据（自建数据层）

```bash
# 开发样本：三只代表性股票（含分红股与停牌股）× 一年，约 6 秒
python cli.py --sync-data --codes 600519.SH,600009.SH,000001.SZ --years 1

# 沪深300 成分股 × 一年，约 9 分钟
python cli.py --sync-data --index csi300 --years 1
```

数据落到 DuckDB 仓库，行情（不复权价）与复权因子分表存储，支撑增量同步（`--resume`）与复权校验。
参数详见 `python cli.py --help`。

> 旧命令 `python cli.py --init-data`（Qlib 官方数据下载）**已彻底移除**：回测引擎只读
> 自建数据层导出的数据集，不存在任何指向 qlib 官方数据的回退路径。

### 4. 安装前端

```bash
cd frontend
npm install
cd ..
```

### 5. 启动

**终端 1 — 后端：**
```bash
python -m uvicorn src.api.app:app --port 8000
```

**终端 2 — 前端：**
```bash
cd frontend && npm run dev
```

浏览器打开 `http://localhost:5173`。

## LLM 配置

### 首次使用

编辑 `.env` 文件即可。支持的主流厂商：

| 厂商 | Base URL | 协议 |
|------|----------|------|
| DeepSeek | `https://api.deepseek.com` | 加 `/anthropic` 走 Anthropic 协议 |
| Kimi | `https://api.moonshot.cn/v1` | OpenAI |
| 千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | OpenAI |
| GLM | `https://open.bigmodel.cn/api/paas/v4` | OpenAI |
| MiniMax | `https://api.minimax.chat/v1` | OpenAI |
| MIMO | `https://token-plan-cn.xiaomimimo.com/v1` | 加 `/anthropic` 走 Anthropic 协议 |
| Anthropic | `https://api.anthropic.com` | Anthropic |
| OpenAI | `https://api.openai.com/v1` | OpenAI |

### Web UI 热切换

在浏览器的 **设置** 页面中，可以保存多个厂商预设并一键切换。切换后 **下一条消息立即生效**，无需重启服务。

协议自动检测：URL 包含 `/anthropic` 时使用 Anthropic 协议，否则使用 OpenAI 协议。

## 项目结构

```
AIFUND5/
├── src/
│   ├── agent/                  # Agent 层
│   │   ├── graph.py            # 两节点 ReAct 循环（agent ⇄ tools）
│   │   ├── registry.py         # 工具注册表：工具面的唯一真实来源
│   │   ├── deps.py             # AgentDeps：工具闭包捕获的业务服务
│   │   ├── state.py            # AgentState 状态定义
│   │   ├── adapters/           # 57 个工具适配器，按 14 个能力域拆分
│   │   │   ├── factor.py       #   因子检索 / 创建
│   │   │   ├── strategy.py     #   策略组合
│   │   │   ├── backtest.py     #   回测执行 / 分析
│   │   │   ├── storage.py      #   策略存储 / 版本链
│   │   │   ├── selection.py    #   选股
│   │   │   ├── position.py     #   仓位管理
│   │   │   ├── optimize.py     #   参数优化
│   │   │   ├── stoploss.py     #   止损
│   │   │   ├── calendar.py     #   交易日历 / 数据覆盖
│   │   │   ├── market_data.py  #   行情 / 财务摘要
│   │   │   ├── fundamental.py  #   研报 / 估值
│   │   │   ├── signal.py       #   资金流 / 龙虎榜 / 解禁
│   │   │   └── news.py         #   新闻 / 公告 / 热榜
│   │   └── prompts/system.md   # 系统提示词
│   ├── tools/                  # 业务逻辑（无 Agent 依赖，可独立测试）
│   │   ├── factor_tools.py     # 因子搜索、创建
│   │   ├── strategy_tools.py   # 策略组合
│   │   ├── backtest_tools.py   # 回测执行、分析
│   │   ├── storage_tools.py    # 策略存储、版本链
│   │   ├── comparison_tools.py # 策略比较、更新
│   │   ├── selection_tools.py  # 选股
│   │   ├── position_tools.py   # 仓位管理
│   │   ├── optimize_tools.py   # 参数优化
│   │   ├── stoploss_tools.py   # 止损
│   │   ├── calendar_tools.py   # 交易日历
│   │   ├── data_tools.py       # 数据覆盖检查
│   │   └── astock_*.py         # 行情 / 信号 / 新闻数据源
│   ├── core/                   # 核心业务逻辑
│   │   ├── models.py           # Pydantic 数据模型
│   │   ├── factor_store.py     # 因子 SQLite + ChromaDB 存储
│   │   ├── strategy_compiler.py# 策略编译器
│   │   ├── backtest_engine.py  # Qlib 回测封装
│   │   ├── session_store.py    # Session 持久化
│   │   ├── settings_store.py   # LLM 配置预设存储
│   │   └── ...
│   ├── data/                   # 自建 A 股数据层
│   │   ├── codes.py            # 6 种代码记法互转（600519 / sh.600519 / SH600519 / 1.600519 ...）
│   │   ├── schema.py           # 统一行情模型与单位约定（volume 一律按股，price 一律不复权）
│   │   ├── provider.py         # Provider 抽象基类 + 多源降级链
│   │   ├── providers/baostock.py
│   │   ├── store.py            # DuckDB 仓库（幂等 upsert，同步断点）
│   │   ├── sync.py             # 手动拉取入口（--sync-data 的实现）
│   │   ├── derive.py           # 复权派生：后复权价 + $change 口径 + 因子链修复
│   │   └── verify.py           # 复权校验（对照官方涨跌幅 / 链单调性）
│   ├── api/                    # FastAPI
│   │   ├── app.py              # 应用入口
│   │   ├── routes/
│   │   │   ├── chat_sse.py     # SSE 聊天端点（Vercel AI SDK）
│   │   │   ├── factors.py      # 因子 API
│   │   │   ├── strategies.py   # 策略 API
│   │   │   ├── backtest.py     # 回测 API
│   │   │   └── settings.py     # LLM 配置 API
│   │   └── ...
│   ├── config.py               # pydantic-settings 配置
│   ├── llm_factory.py          # LLM 工厂（支持协议自动检测）
│   └── exceptions.py           # 统一异常层级
├── frontend/
│   └── src/
│       ├── App.tsx             # 路由入口
│       ├── pages/
│       │   ├── ChatPage.tsx    # AI 对话页面
│       │   ├── FactorsPage.tsx # 因子库
│       │   ├── StrategiesPage.tsx # 策略管理
│       │   ├── BacktestPage.tsx   # 回测结果
│       │   ├── PortfolioPage.tsx  # 仓位管理
│       │   ├── SettingsPage.tsx   # LLM 配置 + 预设
│       │   └── HistoryPage.tsx    # 历史对话
│       └── utils/
│           └── chatStore.ts    # 聊天持久化
├── cli.py                      # CLI 入口
└── factors/builtin/            # 内置因子定义
```

## Agent 架构

Agent 层是一个 **单 Agent + ReAct 工具循环**，刻意保持轻薄：

```
                 ┌─────────────┐
     ┌──────────>│   agent     │  调用 LLM（已 bind_tools）
     │           └──────┬──────┘
     │                  │ should_continue()
     │        ┌─────────┴─────────┐
     │        │ 有 tool_calls?     │ 无
     │        ▼                   ▼
     │   ┌─────────┐            END
     └───┤  tools  │  执行工具后回到 agent
         └─────────┘
```

| 模块 | 职责 |
|------|------|
| `agent/graph.py` | 只做编排：拼装 LLM、系统提示词与两节点循环 |
| `agent/registry.py` | **工具面的唯一真实来源**；bind 列表与 dispatch 表都由注册结果派生 |
| `agent/deps.py` | `AgentDeps`，工具闭包捕获的业务服务 |
| `agent/adapters/` | 57 个工具适配器，按 14 个能力域分文件 |
| `agent/state.py` | `AgentState`：`messages` 与 `tool_call_log` 带 reducer 追加，两个上下文字段保存最新值 |

设计要点：

- **一次注册，两处派生** —— 适配器用 `@registry.tool("factor")` 声明一次，交给模型的工具列表和执行时的分发表都由注册表派生，两者不可能漂移。
- **适配器即普通函数** —— 装饰器原样返回函数，LangChain 仍从 `__name__` / `__doc__` / 类型注解推导工具名、描述与参数 schema。
- **工具调用过程可见** —— 正因适配器是普通函数，LangChain 的 `on_tool_start` / `on_tool_end` 永不触发；图改用自定义流事件广播工具起止，SSE 按 AI SDK v4 的 `9:` / `a:` 转发，长耗时工具不再让页面看起来卡死。
- **阻塞代码不进事件循环** —— 调用同步业务层（qlib / DuckDB / ChromaDB / 外部 HTTP）的路由一律声明为 `def`，由 FastAPI 丢进线程池；只有真正异步的 SSE 端点保持 `async def`，规则由 `tests/test_api_routes.py` 锁定。
- **注册顺序即工具顺序** —— 交给模型的工具顺序稳定可复现。
- **业务逻辑与 Agent 解耦** —— `src/tools/` `src/core/` 不依赖 Agent，可独立测试；适配器只负责 JSON 出入参的转接。
- **按能力域绑定（可选）** —— `create_agent_graph(..., domains=["factor", "backtest"])` 可只暴露部分能力域，缩小交给模型的工具集；默认仍然暴露全部 57 个。

## Agent 工具清单

AI Agent 配备了 **57 个工具**，分为 **14 个能力域**（下表工具名省略 `_` 前缀）：

| 域 | 数量 | 工具 |
|----|------|------|
| 🔍 因子管理 | 2 | `search_factors`, `create_factor` |
| 📐 策略构建 | 1 | `compose_strategy` |
| 📈 回测 | 2 | `run_backtest`, `analyze_backtest` |
| 💾 策略存储 | 8 | `save_strategy`, `load_strategy`, `list_strategies`, `search_strategies`, `delete_strategy`, `compare_strategies`, `update_strategy`, `get_version_chain` |
| 📊 选股 | 1 | `select_stocks` |
| 💰 仓位管理 | 3 | `save_holdings`, `get_portfolio_status`, `save_position_rules` |
| ⚙️ 参数优化 | 1 | `optimize_parameters` |
| 🛡️ 止损 | 3 | `add_stoploss_rules`, `run_backtest_with_stoploss`, `check_stoploss_scenarios` |
| 📅 交易日历 | 4 | `get_current_date`, `resolve_relative_date`, `get_trading_days`, `check_data_coverage` |
| 📉 行情数据 | 7 | `fetch_stock_quote`, `fetch_stock_hist`, `fetch_financial_summary`, `fetch_sector_flow`, `fetch_quarterly_financials`, `fetch_industry_stocks`, `fetch_index_constituents` |
| 📑 研报估值 | 4 | `fetch_stock_reports`, `fetch_industry_reports`, `fetch_eps_forecast`, `fetch_valuation` |
| 🔥 资金信号 | 12 | `fetch_northbound_flow`, `fetch_concept_blocks`, `fetch_fund_flow`, `fetch_fund_flow_120d`, `fetch_dragon_tiger`, `fetch_daily_dragon_tiger`, `fetch_lockup_expiry`, `fetch_industry_ranking`, `fetch_margin_trading`, `fetch_block_trade`, `fetch_holder_change`, `fetch_dividend_history` |
| 🗄️ 数据仓库 | 2 | `sync_market_data`, `export_qlib_dataset` |
| 📰 新闻公告 | 7 | `fetch_stock_news`, `fetch_market_telegraph`, `fetch_global_news`, `fetch_announcements`, `fetch_hot_list`, `fetch_hot_rank`, `fetch_hot_concept` |

工具清单由 `tests/test_agent_tool_surface.py` 逐项锁定，改动工具面会直接让测试失败。

## 自建 A 股数据层

行情数据不依赖 Qlib 官方下载，而是自建一层：**多源适配 → 统一规范 → 落盘 DuckDB → 复权派生与校验 → 导出 Qlib**。

```
BaoStock ─┐                                ┌─> 复权因子（派生 + 对照官方涨跌幅校验）
pytdx ────┼─> Provider 适配层 ─> DuckDB ───┤
AKShare ──┘   （代码/单位/停牌 归一）       └─> Qlib bin 导出（回测读本地）
```

设计取舍与依据（都来自实测，记录在 `DATA_LAYER_PLAN.md`）：

| 决策 | 原因 |
|------|------|
| **存不复权原始价，复权因子独立成表** | 前复权价每来一次分红就重算整条历史，回测不可复现；不复权价是各源一致的客观事实，也是双源对账的前提 |
| **volume 统一按 `股`、amount 按 `元`** | 各源单位不一致且静默：BaoStock 发股，新浪/腾讯发手且会差 100 倍 |
| **`$change` 用复权口径计算** | 用不复权价算会在除权日得假涨跌停：600519 在 2020-06-24 除权日，官方 +0.1736%，raw 口径 -0.9827%，偏差 1.16pp |
| **单只失败不中断整轮同步** | `sync_state` 只记成功覆盖，失败下轮自动重试 |

复权校验结果（全仓库，2020-01-02 → 2024-12-31）：

```
298 只 / 74,488 天 · 对比交易所官方涨跌幅 74,409 天（最大偏差 0.0002pp）
0 天不符 · 0 处因子链倒退 · ✅ 通过
```

期间发现并修复了 BaoStock 复权因子链上的 rebase 伪影（000001.SZ 在 2020-12-31 无除权却下跳
16.82%，超过 9.5% 涨跌停阈值，会让 Qlib 误判跌停拒绝卖出）。

## 测试与质量

```bash
pytest tests/           # 345 通过 / 11 跳过
ruff check src/ tests/  # lint
```

- `AIFUND5_NETWORK_TESTS=1 pytest ...` 会额外跑一组对 BaoStock 真实服务的集成验收（不设该变量时跳过，避免 CI 依赖外网）。
- 校验规则刻意只用**真正独立**的信号对照（交易所官方涨跌幅、复权因子单调性）；
  一个初版检查因在数学上恒为真被否决，原因记录在 `src/data/verify.py` 模块文档里。

## 开发进度

详见 [DATA_LAYER_PLAN.md](DATA_LAYER_PLAN.md)（数据层的权威执行计划，含被实测推翻的早期结论）。

| Phase | 内容 | 状态 |
|-------|------|------|
| 0-4 | 可安装、数据层契约、baostock 主源、DuckDB 仓库、复权口径与校验 | ✅ 已完成 |
| 5 | 导出为 Qlib bin 格式 + `$factor` 量纲校准（实测裁决） | ✅ 已完成 |
| 6 | 接入回测引擎、Agent 数据工具（端到端回测已跑通） | ✅ 已完成 |

已知边界（诚实交代）：

- **幸存者/前视偏差**：当前用沪深300「当前成分股」，实测发现两只 2024 年尚不存在的成分股
  （001280.SZ 2025-12 上市、600930.SH 2025-07-16），回测历史时需在结果处显式声明偏差
- **回测策略选择**：qlib 0.9.7 的 `TopkDropout` 在 `n_drop=0` 时会因 `[-0:]` 陷阱逐日清仓
  （源码定位，见 DATA_LAYER_PLAN.md），已用 `max(1, ...)` 规避；但显示回测的**收益质量**
  （端到端 -0.25% / -40.9% 回撤）受策略实现影响，与数据链路无关，
  需接更合适的 alpha 模型后才呈现演示级效果
- 109 个内置因子中有 **9 个依赖基本面字段**（`$eps` 等），当前数据层只供行情，这 9 个被标记为不可用（方案 A，PIT 对齐待评估后接入）

## CLI 使用

```bash
# 启动交互式对话
python cli.py

# 指定 session
python cli.py --session <session_id>

# 同步行情到本地仓库（自建数据层）
python cli.py --sync-data --codes 600519.SH,600009.SH,000001.SZ --years 1
python cli.py --sync-data --index csi300 --years 1

# 导出 Qlib 数据集供回测引擎读取（省略目录则用默认路径）
python cli.py --export-qlib
```

CLI 内置命令：`/new`（新会话）、`/sessions`（列出会话）、`/switch <id>`（切换会话）、`quit`（退出）。

## 开发

```bash
# 运行测试
pytest tests/

# 后端热重载
python -m uvicorn src.api.app:app --port 8000 --reload

# 前端
cd frontend && npm run dev
```

## 许可证

MIT
