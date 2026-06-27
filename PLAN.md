# AIFUND5 - A股量化投资助手 完整实施计划

## 项目定位

面向个人投资者的 A 股投资助手，通过自然语言交互完成策略构建、因子管理、回测执行和策略迭代。

核心理念：**Agent-native 架构** — Agent 是应用的操作系统，不是插件。

---

## 架构决策汇总

| # | 决策 | 结论 |
|---|------|------|
| 1 | 执行模型 | CLI first，Web later（CopilotKit + React） |
| 2 | LLM-Qlib 交互 | RAG 因子库 + 结构化策略组合（无代码生成） |
| 3 | Agent 角色 | Agent-native：LangGraph 编排器 + 全应用级 Tool 访问 |
| 4 | 因子库 | Agent 可扩展（day 1 支持 create_factor） |
| 5 | 策略存储 | 双存储：SQLite（结构化）+ Vector DB（语义） |
| 6 | 会话模型 | 自主执行 + 事后修正（mutable strategy, immutable backtest） |
| 7 | MVP 工具 | 8 个 Tool |
| 8 | 编排层 | LangGraph（Phase 1a） |
| 9 | Web UI | CopilotKit + React（Phase 1b） |

---

## 技术栈

| 层次 | 技术 | 用途 |
|------|------|------|
| Agent 编排 | LangGraph | 状态图、Tool 调用、会话管理 |
| LLM | Claude API (Anthropic) | 意图解析、因子选择、结果分析 |
| 回测引擎 | Qlib (Microsoft) | A 股数据、策略执行、回测模拟 |
| 因子存储 | SQLite + ChromaDB | 结构化查询 + 语义检索 |
| 策略存储 | SQLite + ChromaDB | 双桥接检索 |
| 数据校验 | Pydantic | Tool 输入校验、数据模型 |
| 日志 | structlog | JSON 结构化日志 + Trace ID |
| API 服务 | FastAPI | 后端 API（Phase 1b 用） |
| 前端 | React + CopilotKit | Agent-native Web UI（Phase 1b） |

---

## 项目结构

```
AIFUND5/
├── PLAN.md                         # 本文件
├── CLAUDE.md                       # 开发规范
├── pyproject.toml                  # 项目配置
├── .env.example                    # 环境变量模板
├── .gitignore
├── src/
│   ├── __init__.py
│   ├── config.py                   # 配置管理（pydantic-settings）
│   ├── exceptions.py               # 统一异常定义
│   ├── logging.py                  # structlog 配置
│   ├── agent/                      # LangGraph 编排层
│   │   ├── __init__.py
│   │   ├── graph.py                # 状态图定义
│   │   ├── state.py                # SessionState 数据模型
│   │   ├── nodes/                  # 图节点
│   │   │   ├── __init__.py
│   │   │   ├── parse_intent.py     # 意图解析
│   │   │   ├── tool_executor.py    # 工具执行
│   │   │   └── response.py         # 结果生成
│   │   └── prompts/
│   │       └── system.md           # System prompt
│   ├── tools/                      # Agent 工具层
│   │   ├── __init__.py
│   │   ├── factor_tools.py         # search_factors, create_factor
│   │   ├── strategy_tools.py       # compose_strategy
│   │   ├── backtest_tools.py       # run_backtest, analyze_backtest
│   │   └── storage_tools.py        # save/load/list strategies
│   ├── core/                       # 核心业务逻辑
│   │   ├── __init__.py
│   │   ├── models.py               # Pydantic 数据模型
│   │   ├── factor_registry.py      # FactorRegistry 接口
│   │   ├── factor_store.py         # 因子存储（SQLite + Vector DB）
│   │   ├── strategy_compiler.py    # 策略编译器
│   │   ├── backtest_engine.py      # Qlib 回测封装
│   │   └── strategy_store.py       # 策略双存储
│   ├── data/                       # 数据层
│   │   ├── __init__.py
│   │   └── qlib_setup.py           # Qlib 初始化
│   └── api/                        # FastAPI（Phase 1b）
│       ├── __init__.py
│       └── routes.py
├── factors/
│   ├── builtin/
│   │   └── factors.json            # 预置因子定义
│   └── custom/                     # Agent 创建的因子
├── strategies/                     # 策略持久化
├── tests/
│   ├── conftest.py
│   ├── test_factor_store.py
│   ├── test_strategy_compiler.py
│   ├── test_backtest_engine.py
│   ├── test_tools.py
│   └── test_agent_graph.py
└── cli.py                          # CLI 入口
```

---

## Phase 1a：LangGraph 后端 + CLI

### Step 0: 基础设施层
- 统一异常屏障（exceptions.py）
- Claude API 封装（timeout=60s, max_retries=3, exponential backoff）
- structlog 配置（JSON 日志 + session_id Trace ID）
- .env + .gitignore + pydantic-settings（config.py）
- verify: 故意触发异常，确认日志格式正确、错误信息友好

### Step 1: 项目骨架 + Qlib 初始化
- pyproject.toml（依赖声明）
- 目录结构创建
- Qlib 初始化 + A 股数据下载（Alpha360）
- verify: `python -c "import qlib; qlib.init()"` 成功

### Step 2: 数据模型 + 因子库 (TDD)
- Pydantic 模型：Factor, FactorCreate, StrategyConfig, BacktestResult
- FactorRegistry 接口
- SQLite 存储 + 索引（factors.tags, strategies.created_at, strategies.sharpe_ratio）
- ChromaDB 向量索引
- 预置 15 个经典因子
- TDD: 先写 test_factor_store.py 测试用例，再实现
- verify: 全部测试通过 + search_factors("动量") 返回正确结果

### Step 3: 策略编译器 (TDD)
- StrategyCompiler: 结构化策略描述 → Qlib SignalStrategy 对象
- TDD: 先写测试（正常组合、空因子、非法参数、边界值），再实现
- verify: 全部测试通过

### Step 4: 回测引擎封装 (TDD)
- BacktestEngine: 封装 Qlib backtest API
- 结果解析（夏普、回撤、年化等）
- 幂等检查：相同 (strategy_hash, date_range) 返回缓存
- TDD: 先写测试，再实现
- verify: 全部测试通过 + 重复调用返回缓存

### Step 5: Agent 工具层
- 8 个 Tool 函数实现
- 每个 Tool 输入使用 Pydantic 校验
- 单元测试
- verify: 每个 tool 独立调用返回正确结果

### Step 6: LangGraph 编排
- StateGraph 定义（parse → execute → respond）
- SessionState 管理（mutable strategy, immutable backtest records）
- Claude API 接入（Tool Node）
- Agent 决策日志记录
- verify: 自然语言输入 → Agent 自动完成全流程

### Step 7: CLI 入口
- 命令行交互循环
- 结果格式化输出
- verify: python cli.py 启动，输入指令得到回测结果

---

## Phase 1b: CopilotKit 前端（1-2 周）

### Step 8: React + CopilotKit
- Next.js 项目 + CopilotKit provider
- Chat 界面
- 对接 FastAPI 后端

### Step 9: 前端组件
- 回测结果展示（收益曲线、指标表格）
- 策略管理面板

---

## Phase 2: 策略管理 + 迭代（1-2 周）

### Step 10: 策略持久化完善
- 双桥接检索（SQL + Vector 取交集）

### Step 11: 策略迭代
- Session state 支持增量修正

### Step 12: 策略比较
- compare_strategies tool

---

## Phase 3: 扩展功能（持续迭代）

- 独立选股 tool
- 仓位管理
- 参数优化
- 多市场支持
