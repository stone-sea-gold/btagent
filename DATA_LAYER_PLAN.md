# 数据层实施计划

本文件是**数据层的权威执行计划**,取代 `PLAN.md` 中关于数据获取的部分。

> **与既有文档的关系**
> - `PLAN.md` —— 原始总体计划(Phase 1a/1b/2/3)。其中 "Phase 1b 用 CopilotKit" 一项**已废弃**
>   (技术原因:CopilotKit 的 AG-UI Runtime 协议与本项目手写 SSE 无法接通,改为自研方案)。
>   本文件不修改该文档,仅作为数据层的现行计划。
> - `PHASE2_PLAN.md` —— 讲的是"策略管理 + 迭代",与本文件的 Phase 2 无关,注意勿混淆。

---

## 〇、术语约定(重要,先读这一节)

中文"因子"在本项目里指**两个毫不相干的东西**,英文都叫 "factor",极易混淆。本文件一律用全称:

| | **量化因子(alpha 因子)** | **复权因子(adjustment factor)** |
|---|---|---|
| 本项目中的位置 | `factors/builtin/factors.json`(109 个)、`src/core/models.py` 的 `Factor` | Qlib 数据格式的 `$factor` / `factor.day.bin` |
| 是什么 | 选股信号,如 `$close / Ref($close, 20) - 1` | 复权系数:`后复权价 = 不复权价 × factor` |
| **由谁计算** | **Qlib 表达式引擎**(在我们提供的数据之上自行计算) | **数据源提供**,本层负责落盘 |
| 需要数据源提供专用接口吗 | ❌ **不需要**。109 个因子里 96 个只是 `$close`/`$volume` 的表达式,只需行情数据 | ✅ 需要,或由后复权/不复权价格相除反推 |
| 缺了会怎样 | 无法选股 | Qlib 退化,`trade_unit`(一手 100 股取整)失效 |

**本文件后续出现的"复权因子"全部指右列。** 左列的量化因子由 Qlib 表达式引擎在行情数据之上计算,数据层只需保证价格字段正确,不涉及任何"因子接口"。

---

## 一、背景与目标

### 为什么需要自建数据层

项目原先依赖 `python cli.py --init-data` 下载 Qlib 官方数据。该路径的实测问题:

- `settings.qlib_data_path` 指向 `~/.qlib/qlib_data/cn_data`,**该目录不存在**
- 10 个测试因此被永久跳过,原因是 `"Qlib data not available"`
- 整条链路(数据 → 因子计算 → 回测)**从未用真实数据端到端跑通过**

因此改为:**自建数据层,从外部数据源拉取全 A 股历史数据落盘本地,Qlib 只作为回测引擎从本地读取。**

### 目标

1. 能从多个外部源拉取 A 股日线数据,统一为一种格式落盘
2. 数据可支撑**可复现**的回测(复权口径正确、无未来函数)
3. 导出的数据能被 Qlib 直接读取,且与 Qlib 的 A 股交易约束(T+1 / 涨跌停 / 一手 100 股 / 手续费)兼容
4. 任何平台可重建环境并运行

---

## 二、锁定的架构决策

| # | 决策 | 结论 | 理由 |
|---|------|------|------|
| 1 | 存储 | **DuckDB** | 列存、单文件、SQL 直查、对 5000 只 × 5 年(约 600 万行)切片查询性能好 |
| 2 | 复权口径 | **存不复权原始价 + 单独存复权因子** | 不复权价是客观事实、各源必须一致(交叉校验的前提);前复权每次分红重写历史,回测不可复现 |
| 3 | 复权因子来源 | 优先取源提供的因子接口;缺则 `factor = hfq_close / raw_close` 反推 | 实测 baostock 有 `query_adjust_factor`,无需反推;反推仅作为其他源的兜底 |
| 4 | Qlib 角色 | **保留作回测引擎**,数据层导出 `.bin` | Qlib 原生支持 A 股交易约束(见附录 A) |
| 5 | 首期范围 | **沪深 300 成分股 × 5 年** | 先跑通全链路,数据量小、迭代快 |
| 6 | 源优先级 | **baostock → pytdx → akshare** | 稳定优先:baostock 官方 SDK 稳定且自带日历/成分股;pytdx 走 TCP 不封 IP 适合批量;akshare 覆盖面最广作兜底 |
| 7 | 频率 | **仅日线**,基础设施预留分钟线 | `freq` 进主键、`ts` 用 TIMESTAMP,分钟线无需改表 |
| 8 | 代码规范形式 | `600519.SH` | 无歧义、按市场自然排序、可无损转其他 5 种格式 |

### "覆盖广优先"的取舍说明

用户要求"覆盖广的源作为最优先"。这里有两种读法,结论相反:

- **品类广**(akshare:股/期/基/债/汇/币/宏观)→ 但回测底座依赖爬虫接口,失效风险高
- **A 股数据完整度 + 稳定性**(baostock/pytdx)→ 底座可靠,但拿不到非 A 股品类

**采用后者**:回测底座按"稳定性 + 复权正确"选,因为底座数据要支撑数年历史回测,爬虫接口失效会导致整个回测跑不起来。品类广度交给现有的 55 个 `astock_*` 工具(新闻/龙虎榜/资金流等特色数据)。

---

## 三、当前状态

| Phase | 内容 | 状态 | 估时 |
|-------|------|------|------|
| **0** | 可安装 + 测试基线 | ✅ **完成** | 0.5d |
| **1** | 数据层三件套(schema/codes/provider) | ✅ **完成** | 0.5d |
| **2** | baostock provider 实现 | ✅ **完成** | 1.5d |
| **3** | DuckDB store + sync 入口 | ✅ **完成** | 1.5d |
| **4** | 复权因子落盘 + `$change` 口径 + 双源校验 | ✅ **完成** | 1.5d |
| **5** | Qlib 导出器 + `$factor` 量纲校准 | ✅ **完成** | 2d |
| **6** | 接入回测引擎 + Agent 工具 | ✅ **完成** | 1.5d |

**关键路径:数据层全部完成(Phase 0–6)。**

### Phase 0 已完成(含证据)

修掉两个**必然导致 `pip install -e .` 失败**的硬 bug:

| Bug | 修正 | 证据 |
|-----|------|------|
| `build-backend = "setuptools.backends._legacy:_Backend"` | → `setuptools.build_meta` | setuptools 84.0.0 wheel 的 343 个文件中无 `backends` 模块 |
| `"qlib>=0.9.0"` | → `"pyqlib>=0.9.6"` | `pip index versions qlib` → 无可用发行版;`pyqlib` → 0.9.6/0.9.7 |

环境侧解决:直连 PyPI 仅 37 kB/s → 改用清华镜像(161 秒装完);pip 缓存目录不可写 → 重定向 `PIP_CACHE_DIR`;chromadb 首次需下载 79MB ONNX 模型 → 分片续传下载器(SHA256 校验通过)。

**测试基线:218 passed / 10 skipped**(起点为 0 个测试能跑)。

### Phase 1 已完成

| 文件 | 行数 | 内容 |
|------|------|------|
| `src/data/codes.py` | 203 | 6 种代码格式互转 |
| `src/data/schema.py` | 203 | `Bar` / `AdjustFactor` / `Instrument` / `Freq` + 单位约定 |
| `src/data/provider.py` | 218 | `DataProvider` 基类 + `ProviderChain` 降级链 |
| `src/config.py` | +8 | 数据层配置项 |
| `tests/test_data_{codes,schema,provider}.py` | 479 | 80 passed,ruff 全过 |

---

## 四、目录结构

```
src/data/
├── codes.py          ✅ 6 种代码格式互转
├── schema.py         ✅ Bar / AdjustFactor / Instrument / Freq
├── provider.py       ✅ Provider 基类 + 降级链
├── providers/
│   ├── baostock.py   ✅ Phase 2 主源
│   ├── tdx.py        ⬜ Phase 4+ 批量源(收编现有 pytdx)
│   └── akshare.py    ⬜ Phase 4+ 兜底源
├── store.py          ✅ Phase 3 DuckDB 仓库
├── derive.py         ✅ Phase 4 复权派生 + $change + 链修复
├── verify.py         ✅ Phase 4 复权校验(对比官方涨跌幅 + 链单调性)
├── sync.py           ✅ Phase 3 手动拉取入口
└── qlib_export.py    ✅ Phase 5 DuckDB → Qlib .bin 导出器
```

### DuckDB 表结构

```sql
CREATE TABLE bars (
  freq     VARCHAR,      -- 'day' / '1min' / '5min' ...（Qlib 同名频率字符串）
  code     VARCHAR,      -- 规范形式 600519.SH
  ts       TIMESTAMP,    -- 日线为当日 00:00:00
  open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE,   -- 一律不复权
  volume DOUBLE,         -- 统一为「股」，不是手
  amount DOUBLE,         -- 统一为「元」
  is_suspended BOOLEAN,
  source   VARCHAR,
  PRIMARY KEY (freq, code, ts)
);

CREATE TABLE adjust_factors (   -- 复权因子,只存日频;须前向填满每个交易日
  code VARCHAR, ts DATE, factor DOUBLE, source VARCHAR,
  PRIMARY KEY (code, ts)
);

CREATE TABLE calendar (
  freq VARCHAR, ts TIMESTAMP,
  PRIMARY KEY (freq, ts)
);

CREATE TABLE instruments (
  code VARCHAR PRIMARY KEY, name VARCHAR,
  start_date DATE, end_date DATE
);
```

---

## 五、待完成阶段(详细步骤)

### Phase 2:baostock provider ✅ 已完成(1.5d)

**产出**:`src/data/providers/baostock.py`、`tests/test_provider_baostock.py`

**步骤**:

1. 实现 `BaoStockProvider(DataProvider)`,声明能力:`BARS`(day)、`FACTORS`、`CALENDAR`、`INSTRUMENTS`
2. 代码转换用 `Security.to_baostock()`(`sh.600519`)
3. 复权因子:**已核实 baostock 提供专用接口**(无需反推)
   - `query_adjust_factor(code, start_date, end_date)` —— 按**除权除息日期**返回复权因子
   - `query_daily_adjust_factor(date)` —— 按指定日期返回
   - `query_history_k_data_plus` 的 `adjustflag`:1=后复权、2=前复权、3=不复权
4. ⚠️ **稀疏的复权因子必须前向填满每个交易日**(本阶段最易踩的坑)
   - `query_adjust_factor` 只在**除权除息日**返回值,其余交易日无行
   - Qlib 的判据是「**任何一个 NaN 就退化**」:
     ```python
     if self.quote_df["$factor"].isna().any():
         self.trade_w_adj_price = True   # trade_unit 失效
     ```
   - 因此入库前必须 **forward-fill 到全局交易日历的每一天**,否则绝大多数日子是 NaN,
     `trade_unit`(一手 100 股取整)依然失效 —— 这个坑不读 Qlib 源码看不出来
5. 单位归一:baostock 的 volume 是**股**,amount 是**元**,需实测确认后再映射
6. 停牌日归一:baostock 停牌日的返回形态需实测,统一到 `is_suspended`
7. 登录会话管理 + 错误映射到 `DataSourceError`

**验收标准**:
- 能拉出茅台 5 年**不复权**日线,行数与 `query_trade_dates` 交易日历吻合
- 能拉出对应复权因子,且**前向填满后无任何 NaN**,每个交易日都有值
- `pytest tests/test_provider_baostock.py` 通过

**baostock 对四类能力的接口映射**(已核实,共 26 个 `query_*` 接口):

| 本层能力 | baostock 接口 |
|----------|---------------|
| `BARS` | `query_history_k_data_plus`(配 `adjustflag`);分钟线亦支持 |
| `FACTORS` | `query_adjust_factor` / `query_daily_adjust_factor` |
| `CALENDAR` | `query_trade_dates` |
| `INSTRUMENTS` | `query_stock_basic` / `query_all_stock`;`query_hs300_stocks`、`query_zz500_stocks`、`query_sz50_stocks` 取指数成分 |

**风险**:
- baostock 数据更新有延迟(通常 T+1),需在文档中说明
- 批量拉取较慢,沪深 300 × 5 年需实测耗时
- `query_hs300_stocks` 只返回**当前**成分股,拿不到历史变动 → 存在幸存者偏差,
  需在文档中声明(见第七章风险登记)

**✅ 完成情况与实测结论**

产出:`src/data/providers/baostock.py`(443 行)、`tests/test_provider_baostock.py`(460 行,37 个用例)。
验收已通过:茅台 5 年 1212 根日线 + 1212 行复权因子(**与交易日历天数完全吻合、无 NaN**)、沪深 300 全部 300 只。

实测确认的关键事实(全部写入了模块文档字符串):

| 项 | 实测结果 |
|----|---------|
| **volume 单位** | **股**。验证:`amount/volume = 1127.41` ≈ 当日收盘 1130;若为「手」会差 100 倍 |
| amount 单位 | 元 |
| 字段类型 | **全部为字符串**,价格 4 位小数,需显式转换 |
| **停牌日** | **返回一个 `tradestatus="0"` 的平盘 bar**(OHLC 全等于前收),**volume/amount 为空字符串**而非 0。见下方「停牌语义」 |
| `query_adjust_factor` | **稀疏**:5 年仅 9 行(只在除权除息日有值) |
| 因子列选择 | 必须用 `backAdjustFactor`。`adjustFactor` 在部分行不一致(2023-06-30 为 0.988591 vs 6.889798) |
| **`query_stock_basic` 上限** | **4000 行封顶**,且按代码排序 → **茅台 sh.600519 不在结果内**。单只查询精确可用 |
| `query_all_stock` | 同样 4000 行封顶 |
| **性能** | 单只 5 年日线 ≈ **4 秒** → 沪深 300 × 5 年 ≈ **20 分钟** |

**⚠️ 停牌语义(一处被实测推翻的早期结论)**

早期用茅台、平安银行探测时未发现停牌行,曾错误推断「停牌日直接不返回」。实测 600009 在
**2022-04-08**(该日为交易日但停牌)的真实返回:

```
date        open    high    low     close   preclose  volume  amount  tradestatus
2022-04-08  50.4300 50.4300 50.4300 50.4300 50.4300   ""      ""      "0"
```

即:**停牌日会返回一个平盘 bar,`tradestatus="0"`,volume/amount 为空字符串**。

- Provider 侧:`is_suspended=True` + volume/amount 归零,**不丢弃该行**(保留停牌可见性);
  仅当 `tradestatus="1"` 而 volume 为空时才报错。
- **⚠️ Phase 5 必须处理**:Qlib 靠「`$close` 缺失」判定停牌(`check_stock_suspended`)。
  若把这个平盘 bar 原样写入,**Qlib 会认为该股当日可交易**,从而在停牌日成交 —— 回测结果失真。
  **导出器必须把停牌日渲染为 NaN。**

> **教训**:这个 bug 在「1 只股票 × 1 年」的数据量下**不会暴露**(2024 年这 10 只票停牌 bar 数为 0)。
> 它是靠「10 只 × 5 年」才浮出来的 —— 见下方「数据量与验证策略」。

**两个由实测驱动的重要设计决定**:

1. **因子从纪元(1990-01-01)起查,而非从 `start` 起。**
   否则区间开头的日子没有前置除权事件可填;若改用「区间内首个事件回填」,会把分红调整
   施加到分红**发生之前**的日子 —— 未来函数。实测验证:2020-01-02 的因子取到 `6.491130`,
   来自 2019-06-28 那次除权(在请求区间之外)。稀疏数据使这次全历史扫描几乎零成本。
2. **`INSTRUMENTS` 能力主动不声明。**
   上市日期只能逐个代码查询,凑齐全市场要数千次往返。与其声明一个无法低成本履行的能力,
   不如提供两个有界方法:`get_index_constituents()`(取指数成分)与
   `resolve_listing_spans(codes)`(为已收窄的代码集补日期区间)。
   `instruments/all.txt` 所需的日期区间也可直接由已落盘的 bar 数据派生。

---

### 附:数据量与验证策略(是否必须 5 年?)

**结论:开发期用 1 年,验证期分宽度与深度两个维度,5 年只在特定环节必需。**

实测同步成本(修复停牌 bug 后):

| 范围 | 根数 | 耗时 | 每只 |
|------|------|------|------|
| 1 只 × 1 年(仅 bars) | 242 | 0.19s | 0.19s |
| 1 只 × 5 年(仅 bars) | 1212 | 2.63s | 2.63s |
| 10 只 × 5 年(仅 bars) | 12120 | 19.41s | 1.94s |
| **297 只 × 1 年 + 因子(真实同步)** | **71,150** | **549.7s** | **1.85s** |
| 3 只 × 5 年 + 因子(真实同步) | 3,636 | 15.4s | 5.13s |

> ⚠️ **注意**:仅测 `get_bars` 会**低估**真实成本 —— 每个代码实际有**两次**网络往返
> (行情 + 复权因子)再加一次日历查询。按真实同步折算:
> **沪深300 × 1 年 ≈ 9 分钟,沪深300 × 5 年 ≈ 25 分钟**。

**逐项评估「五年」的必要性**:

| 理由 | 是否成立 | 依据 |
|------|---------|------|
| 因子回看窗口需要长历史 | ❌ **基本不成立** | 实测 109 个因子**最长回看仅 120 天**(`momentum_6m`);88 个只需 ≤20 天。1 年完全够算 |
| 复权因子链需多年才能验证 | ✅ **成立** | 1 年仅见 1–2 个阶梯,5 年见 8 个,才能验证**累积**链正确 |
| **数据边界情况需更长窗口** | ✅ **成立且已证实** | 停牌 bug 在 2024 单年样本中**零暴露**,靠 5 年样本才浮现 |
| 回测统计显著性 | ✅ 成立 | 1 年约 240 天,夏普比率标准误极大,结论不可用 |
| 多市场状态(牛/熊/震荡) | ✅ 成立 | 单一年份可能只覆盖一种状态 |
| 跨源对账需要样本量 | ✅ 成立 | 更多交易日 = 更多发现不一致的机会 |

**宽度与深度发现的是不同类别的问题,不可互相替代**:

- **宽度(股票数)**→ 暴露个股数据怪癖:停牌、涨跌停、新股上市首日、退市
- **深度(年数)**→ 暴露时序问题:复权链累积、跨除权日口径、市场状态切换

**建议策略**:

| 阶段 | 数据量 | 理由 |
|------|--------|------|
| Phase 3/4 开发迭代 | **1 只 × 1 年**(0.2 秒) | 秒级反馈,改代码不看表 |
| Phase 3/4 验证 | **沪深300 × 1 年**(3 分钟) | 覆盖**宽度**,暴露个股怪癖 |
| **必须含的样本** | 至少 1 只**有分红** + 1 只**有停牌**的票 | 这两类边界是最容易出错的地方 |
| Phase 5 Qlib 校准 | **跨多年 + 跨除权日 + 含停牌** | 复权链与停牌 NaN 处理都需深度 |
| Phase 6 端到端 | **5 年** | 统计显著性 + 完整演示效果 |

**5 年的真实成本很低**(一次同步约 10 分钟),真正的成本在下游回测与因子计算 ——
那部分可以用抽样控制,不必为省同步时间而牺牲数据深度。

---

### Phase 3:DuckDB store + sync 入口 ✅ 已完成(1.5d)

**产出**:`src/data/store.py`、`src/data/sync.py`、`src/data/providers/akshare.py`、`src/data/providers/tdx.py`

**步骤**:

1. `MarketStore`:建表、批量 upsert、按 `(freq, code, ts)` 幂等写入
2. 查询接口:`get_bars(code, start, end, freq)`、`get_panel(codes, start, end, fields)`
3. `sync.py` 手动拉取入口,提供 CLI:
   ```bash
   python cli.py --sync-data --index csi300 --start 2020-01-01 --end 2024-12-31
   python cli.py --sync-data --codes 600519,000001
   python cli.py --sync-data --resume        # 断点续传
   ```
4. 成分股获取:沪深 300 成分股及其**历史变动**(避免幸存者偏差)
5. 收编现有 pytdx 实现为 `providers/tdx.py`
6. 落盘时记录 `source`,便于溯源与交叉校验

**验收标准**:
- 沪深 300 × 5 年日线全部落库(约 37 万行)
- **重复执行 sync 幂等**,不产生重复行
- `SELECT` 查询能正确按日期/代码切片
- 中断后 `--resume` 能继续

---

**✅ 完成情况(实测)**

产出:`src/data/store.py`(364 行)、`src/data/sync.py`(258 行)、
`tests/test_data_store.py` + `tests/test_data_sync.py`(53 个用例)。
新增 CLI:`python cli.py --sync-data --index csi300 --years 1`。

真实端到端结果(3 只 × 5 年):

```
[1/3] 600519.SH  1212 根
[2/3] 600009.SH  1212 根
[3/3] 000001.SZ  1212 根
3 只已同步 · 3,636 根 bar · 3,636 行复权因子 · 15.4s
仓库现状:3,636 根 bar · 3 只 · 2020-01-02 → 2024-12-31 · 3,636 行复权因子
```

**幂等性验收**:第二次执行同一命令 → `0 只已同步 · 3 只已存在跳过 · 0.0s`,仓库仍为 3,636 根。✅

**停牌数据落库验收**:600009.SH 有 **11 根 `is_suspended=True` 的 bar**
(2021-06-10 起连续多日,volume=0),证明 Phase 2 的停牌修复贯通到仓库层。✅

**宽度验证(沪深300 × 1 年,真实执行)**:

```
297 只已同步 · 71,150 根 bar · 71,874 行复权因子 · 3 只已存在跳过 · 549.7s
仓库现状:74,786 根 bar · 298 只 · 3 只已存在跳过
```

⚠️ **期间发现一个幸存者偏差的具体实例**:成分股 300 只,但库中只有 **298 只有 bar**。
查证原因 —— 两只**在 2024 年尚不存在**:

| 代码 | 名称 | 上市日 |
|------|------|--------|
| `001280.SZ` | 中国铀业 | **2025-12-03** |
| `600930.SH` | 华电新能 | **2025-07-16** |

这正说明用**当前成分股**回测历史的问题:不仅会漏掉当年被剔除的差股票(幸存者偏差),
还会**混入当时尚未上市的公司**(前视偏差)。两种偏差方向相反但都高估回测表现。
Phase 6 必须在回测结果处显式声明。

**设计要点**:

- `bars` 以 `(freq, code, ts)` 为主键 → 日线与分钟线共存,重复同步幂等
- `adjust_factors` 独立成表 → 新分红只延长因子表,**不重写任何历史价格**
- `sync_state` 记录每只票已拉区间 → `--resume` 的载体;记录时**只扩不缩**,
  保证先同步相邻窗口能扩展覆盖而非重置
- **单只失败不中断整轮**(收集进 `SyncResult.failures`),且失败码**不记入
  `sync_state`**,下次运行自动重试
- `updated_at` 存 UTC(hash 时间戳是「时刻」,与 `bars.ts` 的「交易日历日期」刻意区分);
  不用 `TIMESTAMPTZ` 是因为 DuckDB 读回时需要 `pytz`,为一个无人查询的审计字段引入依赖不划算

**开发样本策略已落地**:`DEV_CODES = ("600519.SH", "600009.SH", "000001.SZ")` ——
刻意包含**分红股**(复权链推进)与**有停牌的股**(2021 与 2022 均有停牌),并有测试
`test_dev_codes_cover_the_awkward_cases` 断言这一点,防止将来被改成无意义的切片。

---

### Phase 4:复权因子落盘 + `$change` 复权口径 + 双源校验 ✅ 已完成(1.5d)

**产出**:`src/data/derive.py`、`src/data/verify.py`、`tests/test_derive.py`

**步骤**:

1. 复权因子落盘:优先用源提供的因子接口(baostock 的 `query_adjust_factor`),缺失时用 `factor = hfq_close / raw_close` 反推,落 `factors` 表
2. ⚠️ **`$change` 必须用复权口径计算**:
   ```python
   change = hfq_close / prev_hfq_close - 1     # ✅
   change = raw_close / prev_raw_close - 1     # ❌ 除权日算出假跌停
   ```
   用不复权价算 `$change`,一次 10 送 10 会得到 -50%,Qlib 会**误判跌停导致无法卖出**。
   这类 bug 不报错,只让回测**静默失真**,所以设为独立验收项。
3. 双源交叉校验:`verify.py` 对同一只票从两个源取**不复权价**,逐日比对,不一致即报警
4. 跨除权日专项测试:构造已知送转的票(茅台/宁德),验证 `change` 序列无假涨跌停

**验收标准**:
- 跨除权日 `$change` **无假涨跌停信号**
- 两个源的不复权价逐日一致(容差内)
- 复权因子序列单调平滑,无跳变异常

---

**✅ 完成情况(实测)**

产出:`src/data/derive.py`(180 行)、`src/data/verify.py`(292 行)、
`tests/test_data_derive.py` + `tests/test_data_verify.py`(36 个用例)。

## `$change` 口径 —— 用真实数据验证

在 600519 的 2020-06-24 除权日(分红 17.02 元 / 前收 1474.50):

| 口径 | 2020-06-24 涨跌幅 |
|------|------------------|
| **交易所官方 `pctChg`** | **+0.1736%** |
| hfq 口径(`hfq_close / prev_hfq_close - 1`) | **+0.1736%** ✅ 完全一致 |
| raw 口径(`raw_close / prev_raw_close - 1`) | **-0.9827%** ❌ 偏离 1.16pp |

**hfq 口径精确复现了交易所官方数字**,raw 口径的偏差恰好等于分红率。

> 诚实说明:茅台的分红率只有 1–2%,**不足以触发 9.5% 的涨跌停阈值**;但 `$change`
> 的数值本身是错的(会影响任何使用该字段的因子),而遇到 **10送10**(约 50% 折价)就会
> 真的被 Qlib 判为跌停而拒绝卖出。

## ⚠️ 校验抓到的真实缺陷:baostock 因子链存在 rebase 伪影

校验对比官方涨跌幅时,发现 **000001.SZ 在 2020-12-31 不符,偏差 16.94pp**。追查结果:

```
baostock query_adjust_factor(sz.000001):
  2020-05-28   backAdjustFactor = 119.960317
  2020-12-31   backAdjustFactor =  99.787353   ← 下降 16.82%!
  2021-05-14   backAdjustFactor = 100.572054
```

而 `query_dividend_data` 显示该股 2020 年**只有 2020-05-28 一次分红**,2020-12-31 无任何
除权事件。进一步验证:**baostock 自己的后复权价**(`adjustflag=1`)在同一天也有
**-16.2098% 的跳变** —— 所以伪影在**数据源**里,不在我们的应用方式。

**后复权因子在数学上只能单调不减**,下降必然是数据源的 rebase。危害具体:
-16.8% **超过 9.5% 涨跌停阈值** → Qlib 会判为跌停拒绝卖出,回测结果失真。

**修复**:`derive.enforce_monotonic_chain()` 在伪影日保持前值,并把后续整段按同一比例
缩放,使链保持连续且**后续真实除权的步长不变**。修复后:

```
2020-05-28  119.960317
2021-05-14  120.903653   (原 100.572054 × 1.202159)
```

**影响范围**:重刷沪深300后发现 5 只票有伪影(`sh.600372`、`sh.600760`、`sh.601607`、
`sz.000001`、`sz.000002`),首次出现在 1991–2020 年不等。注意:**多数伪影发生在 1990–2000
年代**(在同步窗口之外),但由于是 rebase,**会缩放其后所有因子值** —— 所以受影响的
2024 年因子同样需要重刷。这也说明「只扫窗口内因子」会系统性低估问题范围。

## 全仓校验结果(298 只)

```
298 只 / 74,488 天 · 对比官方涨跌幅 74,409 天(最大偏差 0.0002pp)
0 天不符 · 0 处因子链倒退 · 0 只无法检查 · ✅ 通过
```

**最大偏差 0.0002 个百分点**,即推导出的 `$change` 与交易所官方数字在 74,409 个观测上
实质完全一致。

## 一个被主动否决的校验设计

初版写了一个「对比 hfq 口径与 raw 口径的偏离」检查,写测试时发现它是**恒真式**:

```
(C_t·f_t)/(C_{t-1}·f_{t-1}) - 1  ==  C_t/C_{t-1} - 1   当且仅当  f_t == f_{t-1}
```

而因子就在同一行数据里,所以该检查只能复述输入,**在任何输入上都会通过,包括严重错误的输入**。
这比没有检查更糟 —— 它会带来没有赚到的信心。**已删除**,并在 `verify.py` 文档字符串中
写明了否决理由。保留的两个检查都是真正独立的:

1. **对比交易所官方涨跌幅**(`bars.pct_change`,独立产生)—— 正是它抓到了 rebase 伪影
2. **因子链单调性**(后复权因子的构造性不变量)

> **关于「双源校验」**:原计划是拉两个数据源互相对价。实测在本环境**只有 baostock 可用**
> —— pytdx 的 TDX 服务器无响应,akshare 被东财拒绝连接(`RemoteDisconnected`)。
> 因此改用**更强且可离线重复**的方案:把交易所官方涨跌幅落库(`bars.pct_change`),
> 让校验不依赖网络。用户所在网络环境下 akshare/pytdx 大概率可用,届时可再补真·双源对价。

---

### Phase 5:Qlib 导出器 + `$factor` 量纲校准 ✅ 已完成(2d)

**产出**:`src/data/qlib_export.py`、校准测试

**这是数据层与 Qlib 之间的唯一桥梁。**

**Qlib 磁盘格式**(核实自 `scripts/dump_bin.py`):

```
qlib_dir/
├── calendars/day.txt          # 每行 "%Y-%m-%d"
├── instruments/all.txt        # 每行 "SH600519\t起始\t结束"（大写、无点）
└── features/sh600519/         # 目录名 = code_to_fname().lower()
    ├── open.day.bin
    ├── close.day.bin
    ├── volume.day.bin
    ├── factor.day.bin         # ★ 必需
    └── change.day.bin         # ★ 必需
```

**⚠️ 停牌日必须渲染为 NaN**(见 Phase 2「停牌语义」):Qlib 以「`$close` 缺失」判定停牌,
写入平盘 bar 会让回测在停牌日成交。

**三个必须遵守的格式细节**:
1. **float32 小端**:`np.hstack([date_index, values]).astype("<f").tofile(...)`
2. **每个 .bin 的第一个元素是该股在全局日历中的起始索引**,其后才是数据
3. `data_merge_calendar` 会把数据 reindex 到全局日历上,**缺失日期变 NaN**

**Qlib 回测必需字段**(核实自 `qlib/backtest/exchange.py`):

```python
necessary_fields = {buy_price, sell_price, "$close", "$change", "$factor", "$volume"}
```

**⚠️ `$factor` 量纲校准(本阶段核心风险)**

Qlib 把 factor 当作**份额换算系数**使用:

```python
return (deal_amount * factor + 0.1) // self.trade_unit * self.trade_unit / factor
```

且源码中明确:

```python
if self.quote_df["$factor"].isna().any():
    self.trade_w_adj_price = True
    self.logger.warning("factor.day.bin file not exists... trade unit is not supported")
else:
    self.trade_w_adj_price = False
```

即:**有 factor → 启用 `trade_unit`(一手 100 股取整);无 factor → 退化且 trade_unit 失效。**

`$factor` 的精确量纲约定(是否含送股再投资、与后复权价的比例关系)**无法靠读源码可靠推导**,必须实测校准。**不猜**。

**校准方法**:
1. 选一只已知有送转的票,手工计算除权日前后的真实收益率
2. 与 Qlib 回测输出对比
3. 对不上就调整 factor 口径

**验收标准**:
- `qlib.init(provider_uri=...)` 能读到导出的数据
- 回测能跑通
- **跨除权日收益与手算一致**(这是数据层成立的最终判据)

---

**✅ 完成情况(实测,全部通过)**

产出:`src/data/qlib_export.py`、`tests/test_data_qlib_export.py`(9 个用例)、
CLI `--export-qlib OUT_DIR`。

## 导出与 Qlib 读取验收

```
python cli.py --export-qlib /tmp/qlib_full     # 298 只 / 1212 天 / 7 字段 / 18MB / 9 秒
```

**Qlib 亲自读回验收**(pyqlib 0.9.7，`qlib.init(provider_uri=...)` 后用 `D.features`)：

```
                 $open        $close    $volume   $factor   $change
2020-01-02   7321.9946   7334.9771  14809916.0  6.491130      NaN
2020-06-24   9611.3603   9587.7851  2513899.0  6.566931  0.001736   ← 除权日因子步进
2024-12-31  11020.9033  11010.7891  3935445.0  7.224927 -0.000656
instruments 数: 298
```

`$factor` 除权日步进可见、`$change` 用复权口径(即官方涨跌幅)。✅

## ⚠️ `$factor` 量纲校准 —— 结论:我的约定与 Qlib 原生语义**一致**(实测验证)

计划里的核心风险关卡。原判断「无法靠读源码推导,必须实测,可能需要人工介入」——
**实际上用仓库里已有的独立锚点(交易所官方涨跌幅)+ 本地跑 Qlib 就完成了闭环,无需人工操作**。

校准方法:逐一候选约定(`$close`=后复权 vs 原始价),同一份本地数据导出后用
**买入持有**回测,对比 `∏(1+官方涨跌幅)`;匹配的即正确量纲。

裁决过程(pyqlib 0.9.7，`BaseTest` 阶段用 `Exchange` 直接下单,绕开策略层):

| 检验 | 实测结果 |
|------|---------|
| **整手对账** | `deal_amount × factor = 123.245 × 6.49113 = 800.00` 精确整手(800 原始股 = 8手)✅ |
| **现金流恒等式** | `trade_val = 862,848.03 = 800 × 1,078.56`（当日**原始**收盘价 × 原始股数）✅ |
| **持仓重估值** | `price = 7001.0732 = raw(1078.56) × factor(6.49113)` 精确等于我的后复权价 ✅ |
| bench 列 | Qlib 回测的 `bench` 列逐日等于官方涨跌幅(-4.55% 等) ✅ |

**结论**:`adj_price × adj_amount ≡ raw_price × raw_shares`(money 不变恒等式)在 Qlib
的执行路径里成立,即 **`$close`=后复权、`$factor`=hfq/raw** 是正确约定 —— 恰好就是我
导出的那套。那份「校准失败需要人工介入」的风险**实测后不存在**。

## 停牌日 → NaN 的落地验证

Qlib 靠「`$close` 缺失」判定停牌(见 Phase 2 记录)。600009 的 11 根停牌 bar 导出后:

```
停牌日 close=NaN、change=NaN、volume=NaN       ← Qlib 会判定为不可交易 ✅
停牌日 factor=2.593（保留数值，避免整体退化为复权价模式） ✅
```

## 一处 Phase 6 需要处理的已知问题

**Qlib 自带的 `TopkDropoutStrategy` 会逐日买进卖出**,即使信号恒定、交易域收窄到
单只票、`trade_unit=None` 也如此。轮换导致手续费累计 961 万元(本金 100 万),
最终账户残值 -129% —— **与数据量纲无关**(证据:`turnover_rate` 逐日等于 0.95 且在
`trade_unit=None` 时同样轮换)。根因需要在 Phase 6 接入回测引擎时定位
(候选:`TopkDropout` 对「单只票 universe」的处理,或 `signal` 的 T+1 对齐)。
校准结论不受影响:三个独立环节都已验证。

---

### Phase 6:接入回测引擎 + Agent 工具 ✅ 已完成(1.5d)

**产出**:改造 `src/core/backtest_engine.py`、新增 data 域 agent adapter

**步骤**:

1. `backtest_engine.py` 的 `qlib.init` 指向导出的本地数据目录
2. 按附录 A 配置 `exchange_kwargs`,启用 A 股约束
3. 新增 `src/agent/adapters/data.py`,暴露 `sync_market_data` / `export_qlib_dataset` 等工具
4. 用 `ToolRegistry` 的域级绑定能力,评估是否启用工具路由(55 个工具平铺已接近 LLM 选择能力上限)

**验收标准**:
- 对话触发回测,用**本地数据**产出**非零**指标 + **有波动**的净值曲线
- 10 个 skip 测试转为通过

---

### 补充范围:基本面字段(109 个量化因子里 9 个依赖)

**这是原计划遗漏的一项,由核实因子公式时发现。**

实测 `factors/builtin/factors.json` 的 109 个量化因子,其公式引用的数据字段分布为:

| 字段 | 被引用次数 | 来源 |
|------|-----------|------|
| `$close` / `$volume` / `$high` / `$low` / `$open` | 131 / 31 / 21 / 18 / 8 | **行情数据**(本计划已覆盖) |
| `$revenue_ttm` | 5 | ⚠️ 基本面 |
| `$net_profit_ttm` | 2 | ⚠️ 基本面 |
| `$eps` / `$beps` / `$total_share` / `$equity` / `$total_assets` / `$cost_ttm` / `$total_market_value` / `$turnover_rate` | 各 1 | ⚠️ 基本面 / 股本 |

**9 个因子需要行情之外的字段**:`ep_ratio`、`bp_ratio`、`sp_ratio`、`roe_ttm`、`roa_ttm`、`gross_margin`、`ln_market_cap`、`turnover_20d`、`revenue_growth_yoy`。

**若数据层只提供 OHLCV,这 9 个因子在 Qlib 求值时会报错或产出 NaN** —— 用户在 Agent 里选到它们就会失败,直接影响演示。

**baostock 的对应接口**(已核实存在):

| 需要的字段 | baostock 接口 |
|-----------|---------------|
| 盈利能力(`$net_profit_ttm`、`$eps`、`$roe`) | `query_profit_data` |
| 资产负债(`$total_assets`、`$equity`、`$total_share`) | `query_balance_data` |
| 现金流(`$cost_ttm`) | `query_cash_flow_data` |
| 成长性(`$revenue_ttm` 同比) | `query_growth_data` |
| 营运能力 | `query_operation_data` |
| 杜邦分析 | `query_dupont_data` |
| 估值 / 市值 | 由 `$close × $total_share` 派生,或 `query_stock_basic` |

**决策:已采用方案 A(2026-09 确认)**

- ✅ **方案 A(已定)**:首期只供应 OHLCV,把这 9 个因子**显式标记为不可用** ——
  在 `factor_store` 与 Agent 提示词中都标注所需字段缺失。先跑通 100 个纯行情因子。
- ⬜ 方案 B(暂缓):同期接入基本面字段可覆盖全部 109 个因子,但增加约 2 个工作日,
  且基本面数据是**季度频 + 需按公告日做 PIT(point-in-time)对齐**,才能避免未来函数 ——
  复杂度显著更高。待 Phase 6 端到端跑通后再评估。

**方案 A 的落地项(并入 Phase 6)**:

1. 在 `Factor` 模型或 `factors.json` 中增加「所需数据字段」标注;
2. `factor_store` 加载内置因子时,对缺字段的 9 个标记 `unavailable`;
3. Agent 系统提示词中说明这 9 个因子当前不可用,避免模型选中后报错;
4. 新增一个校验测试:断言被标记不可用的因子集合恰好是这 9 个,防止将来字段补齐后遗忘。

> **注意 PIT 陷阱**:基本面数据若按报告期而非**公告日**对齐,会把"财报发布前"的价格
> 配上"财报发布后"的数据,产生未来函数。这是量化回测中最经典的错误之一,
> 也是方案 B 成本高的真正原因。

---

**✅ 完成情况(全部实测)**

产出:`src/data/qlib_dataset.py`(共享数据集解析)、`src/agent/adapters/data.py`(3 个数据域工具)、
`tests/test_agent_data_adapters.py`(5 用例)、skip 条件更新(2 个测试文件)、
引擎接线 + 换手率真实计算 + 禁止静默归零 + `strategy_compiler` n_drop 边界。

## 1. 引擎接线到自建数据集

`backtest_engine` 与 `stock_selector` 共用 `src/data/qlib_dataset.provider_uri()`:
优先 `qlib_export_path`(数据层导出)，次选官方下载;`ensure_init()` 集中处理
（qlib 全局单 provider，谁先 init 谁钉住进程 —— 必须全走同一解析）。

**端到端验收（真实引擎回测，全部由仓库数据驱动）**：

```
== 端到端回测结果（e2e_demo, momentum_3m × topk=10）
  总收益        -0.25%
  最大回撤      -40.90%
  波动率         22.63%
  换手率        105.54%   ← 不再恒为 0（P0 修复生效）
  净值点数      1211
  净值变动日    911/1211（有波动 ✅）
```

十个 skip 测试解禁通过（`test_backtest_engine` 5 个全部通过）。

## 顺手修复的两个演示风险（P0）

| 问题 | 修复 |
|------|------|
| 换手率硬编码 0 | 从 Qlib report 的 `turnover` 列取**日均**换手率（fraction），前端指标卡终于有真值 |
| 失败静默返回全 0 | `_parse_metrics` 异常 → **抛 `BacktestError`**，不再输出假成绩单 |

## ⚠️ 发现并定位 Qlib 0.9.7 的一个上游缺陷（简历素材）

辐 解释了 Phase 5 观测到的「逐日买进卖出」：qlib 的
` qlib/contrib/strategy/signal_strategy.py:220`（`method_sell="bottom"`）：

```python
sell = last[last.isin(get_last_n(comb, self.n_drop))]
```

`get_last_n(li, n) = list(li)[-n:]` —— **`n_drop=0` 时 `[-0:]` 即 `[0:]`，整个列表**
（Python `-0 ≡ 0` 的经典陷阱）。于是持有日必然卖光、次日空仓再买回，循环往复。
**与数据/量纲完全无关**（`trade_unit=None` 下同样轮换）。

应对：`strategy_compiler` 将 `n_drop` 加固为 `max(1, k//5)`、引擎也是 `max(1, topk)`，
并在代码注释中写明依据。残留问题：轮换在**单只票 universe** 依然存在
（`n_drop≥1` 时 1 只票也被列为 bottom），所以 demo 回测的收益质量需要在
Phase 6bis 调参（topk 更大的 universe + 实际 alpha 模型）。

## 数据域工具（agent 面）

| 工具 | 说明 |
|------|------|
| `sync_market_data(index/codes/start/years/source)` | 从数据源同步行情+复权因子到仓库 |
| `export_qlib_dataset(out_dir)` | 导出 Qlib bin 数据集（默认路径 + 指数不入交易域）|

覆盖查询不在这里：它由日历域的 `check_data_coverage` 提供（见下），仓库统计已并入其返回。

工具面从 55 → 58 个工具 / 14 个域。其中 `get_data_coverage` 与日历域既有的
`check_data_coverage` 职责重复,模型需要在两个同名概念间自行猜测,后续已合并为单一
`check_data_coverage`（并把仓库总量并入其返回），现为 **57 个工具 / 14 个域**，
`test_agent_tool_surface` 锁定项已同步更新。

## 六、并行的质量修复项(不属数据层,但影响演示)

| 优先级 | 问题 | 位置 | 影响 |
|--------|------|------|------|
| **P0** | **换手率硬编码为 0** | `backtest_engine.py:314` | 前端有"换手率"指标卡但永远显示 0%,懂行者一眼看穿 |
| **P0** | **回测失败静默降级为全 0** | `backtest_engine.py:319-324` | 失败时返回"全 0 成绩单",用户看到夏普 0.00 却不知是失败 |
| P1 | SSE 不转发 tool 事件 | `chat_sse.py` | 用户看不到 Agent 的工具调用过程,黑盒感极强 |
| P2 | Agentic UI 未实现 | `frontend/src/` | Agent 只能输出文字,无法驱动页面(自研方案,已放弃 CopilotKit) |
| P2 | 跨平台交付物缺失 | 项目根 | 无 `uv.lock`、无 setup 脚本、README 无 Windows 说明 |
| P3 | 无鉴权 | `src/api/` | 任何人可调 LLM Key 烧钱 |
| P3 | 无 CI / Docker / DB 迁移机制 | — | 工程化缺口 |
| P3 | README 与实际不符 | `README.md` | 宣称 24 个工具,**实际注册 55 个**;仍写 CopilotKit |

---

## 七、风险登记

| 风险 | 概率 | 影响 | 应对 |
|------|------|------|------|
| **factor 口径校准失败** | 中 | 高 | Phase 5 独立设卡;失败则退到无 factor 模式(trade_unit 失效,已知且可文档化) |
| **`$change` 用错口径** | 中 | 高(静默失真) | Phase 4 设跨除权日专项测试 |
| 复权因子稀疏未填满 | **高** | 中 | `query_adjust_factor` 只在除权除息日有值;Qlib 遇任一 NaN 即退化 → **入库前必须 forward-fill 到每个交易日**(Phase 2 步骤 4) |
| 沪深 300 成分股历史变动难获取 | 中 | 中 | 退化为"当前成分股"并**在文档中声明幸存者偏差** |
| baostock 数据更新延迟 | 高 | 低 | 文档说明;必要时用 akshare 补最新几日 |
| **全市场枚举受 4000 行封顶限制** | **已确认发生** | 中 | Phase 3 用指数成分股而非全市场枚举;`query_stock_basic` 单只查询精确可用 |
| 网络慢(实测直连 PyPI 37 kB/s) | 高 | 中 | 全程使用国内镜像;大批量下载用分片续传 |
| pyqlib 在 py3.12 兼容性 | 低 | 中 | 已实测可装(Linux/Windows 均有 cp312 wheel) |

---

## 附录 A:Qlib 原生支持的 A 股约束(核实自源码)

`qlib/backtest/exchange.py` 的 `Exchange` 类原生支持,无需自研:

| 约束 | 参数 | 实现 |
|------|------|------|
| **涨跌停** | `limit_threshold` | `limit_buy = $change >= thr`;`limit_sell = $change <= -thr` |
| **停牌** | 自动 | `check_stock_suspended`:`$close is None` 即停牌 |
| **手续费** | `open_cost` / `close_cost` | 默认 0.0015 / 0.0025 |
| **最低佣金** | `min_cost` | 默认 5 元 |
| **冲击成本/滑点** | `impact_cost` | 按成交量占比平方建模 |
| **一手 100 股** | `trade_unit` | 源码注释:`100 for China A market` |
| **成交量上限** | `volume_threshold` | 支持 `cum` / `current` 两种模式 |

> 这条核实结果**推翻了本项目早期"需自研回测才能实现 A 股约束"的判断**,是保留 Qlib 的直接依据。

## 附录 B:关键判据速查

```bash
# 端到端成功的最终标志
python cli.py                        # 启动对话
> 帮我回测一个动量策略               # Agent 自动执行
# 期望:净值曲线有波动、夏普非零、无 skip

# 数据层验收
pytest tests/ -q                     # 期望 10 个 skip 消失
python cli.py --sync-data --index csi300 --start 2020-01-01
```
