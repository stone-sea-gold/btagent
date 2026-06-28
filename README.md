[README.md](https://github.com/user-attachments/files/29435322/README.md)
# AIFUND5 — A 股量化投资助手

面向个人投资者的 **Agent-native** 量化投资系统。通过自然语言与 AI Agent 交互，完成因子搜索、策略构建、回测分析、选股筛选、仓位管理等全流程量化投资任务。

## 特性

- **🤖 Agent-native 架构** — LangGraph 编排的 AI Agent 拥有 24 个工具，自动执行复杂量化任务
- **🔍 因子管理** — 搜索内置因子库（109+ 因子），或创建自定义因子
- **📈 策略构建与回测** — 组合因子构建策略，一键回测并获取夏普比率、最大回撤等指标
- **💾 策略持久化** — SQLite + ChromaDB 双存储，支持语义搜索和版本链
- **📊 选股分析** — 多级选股管线（因子打分 + 条件筛选）
- **💰 仓位管理** — 持仓保存、规则检查、违规预警
- **⚙️ 参数优化** — 网格搜索 / 贝叶斯优化，附带过拟合警告
- **🛡️ 止损设置** — 固定止损、追踪止损、最大回撤熔断
- **🔄 策略迭代** — 版本链管理，策略对比，增量修改
- **🌐 Web UI + CLI** — 支持浏览器对话和命令行两种交互方式

## 技术栈

| 层级 | 技术 |
|------|------|
| Agent 编排 | LangGraph |
| LLM | 支持 DeepSeek / Anthropic / OpenAI / 千问 / Kimi / GLM / MiniMax / MIMO 等 |
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

### 3. 下载 Qlib 数据（可选，回测需要）

```bash
python cli.py --init-data
```

下载 A 股数据约需 5-10 分钟。

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
│   │   ├── graph.py            # LangGraph 状态图（主编排器）
│   │   ├── state.py            # Agent 状态定义
│   │   └── prompts/system.md   # 系统提示词
│   ├── tools/                  # Agent 工具（24 个）
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
│   │   └── data_tools.py       # 数据覆盖检查
│   ├── core/                   # 核心业务逻辑
│   │   ├── models.py           # Pydantic 数据模型
│   │   ├── factor_store.py     # 因子 SQLite + ChromaDB 存储
│   │   ├── strategy_compiler.py# 策略编译器
│   │   ├── backtest_engine.py  # Qlib 回测封装
│   │   ├── session_store.py    # Session 持久化
│   │   ├── settings_store.py   # LLM 配置预设存储
│   │   └── ...
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

## Agent 工具清单

AI Agent 配备了 24 个工具，分为 8 个能力域：

| 域 | 工具 |
|----|------|
| 🔍 因子管理 | `search_factors`, `create_factor` |
| 📐 策略构建 | `compose_strategy` |
| 📈 回测 | `run_backtest`, `analyze_backtest` |
| 💾 策略存储 | `save_strategy`, `load_strategy`, `list_strategies`, `search_strategies`, `compare_strategies`, `update_strategy`, `get_version_chain` |
| 📊 选股 | `select_stocks` |
| 💰 仓位管理 | `save_holdings`, `get_portfolio_status`, `save_position_rules` |
| ⚙️ 参数优化 | `optimize_parameters` |
| 🛡️ 止损 | `add_stoploss_rules`, `run_backtest_with_stoploss`, `check_stoploss_scenarios` |

## CLI 使用

```bash
# 启动交互式对话
python cli.py

# 指定 session
python cli.py --session <session_id>

# 初始化数据
python cli.py --init-data
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
