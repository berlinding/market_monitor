# daily_bars Migration Plan v1

> 现有 `daily_bars`（Tushare A股日线，~5,540 条）→ canonical schema 迁移方案
> 日期：2026-08-17 ｜ 状态：**Design only —— 本轮不执行任何迁移**
> 原则：copy + validate，禁止 destructive rewrite

---

## 0. 现状

`data/market.db`（legacy，本轮不动）：

```
daily_bars(ts_code, trade_date, open, high, low, close, pre_close, change, pct_chg, vol, amount)
  PK(ts_code, trade_date)   -- 约 5,540 行
fetch_log(trade_date, fetched_at, rows, note)
```

目标（R1B 实施）：

```
instrument_identifiers  (TUSHARE provider, identifier_type='TICKER', identifier=ts_code)
        │
        ▼
instruments             (EQUITY, primary_symbol=ts_code 拆出的交易所符号, exchange_code=XSHG/XSHE)
        │
        ▼
market_prices_daily     (instrument_id, trade_date, OHLC, volume=LOTS, turnover=THOUSAND_CNY,
                         adjustment_type='RAW', source_id=TUSHARE)
```

Tushare ts_code 格式：`600519.SH`（上海）/ `000001.SZ`（深圳）。symbol 与交易所均从 ts_code 解析。

---

## 1. 迁移前置（R1B 开始前必须完成）

1. **建 canonical 库**：`data/runtime/core.db` + `data/private/private.db`（R1B DDL，含 schema_migrations）。
2. **备份 legacy**：`data/market.db` 完整复制为 `data/market_backup_YYYYMMDD.db`（不删除原件）。
3. **冻结写入**：迁移期间暂停 fetch_daily.py 对 market.db 的写入（迁移完成后新数据直写 core.db）。

---

## 2. 迁移步骤（copy + validate）

### Step 1 — 创建 Entity（公司主体）

- 从 `daily_bars` 提取全部去重 `ts_code`（预计 ~3,000–5,000 个）；
- 每个 ts_code 对应一家 A 股公司 → 用 Tushare `stock_basic` 拉取 `ts_code, name, area, industry, list_date` 建立 `entities`（canonical_name=股票名称，country_code='CN'，entity_type='COMPANY'）；
- 缺失/失败的公司：登记 `data_gaps`，不阻塞迁移（该部分行情仍可迁移，entity 后补）。

### Step 2 — 创建 Instrument + Identifier

对每个 ts_code：

1. 解析 `symbol`（如 `600519`）与 `exchange`（`.SH`→XSHG，`.SZ`→XSHE）；
2. `INSERT INTO instruments (entity_id, instrument_type='EQUITY', primary_symbol=symbol, exchange_code, currency_code='CNY', country_code='CN', listing_date=list_date)`；
3. `INSERT INTO instrument_identifiers (instrument_id, provider='TUSHARE', identifier_type='TICKER', identifier=ts_code, valid_from=list_date, valid_to=NULL, is_primary=1)`；
4. 建立临时映射表 `_mig_ts_code_map(ts_code → instrument_id)`（仅迁移期存在，完成后删除）。

**1 ts_code → 1 canonical instrument 的保证**：ts_code 是 Tushare 内唯一 key；迁移期对 ts_code 做 UNIQUE 校验（重复则报错中止，绝不静默合并）。若同一公司多 ts_code（如 A+H 或历史代码），则对应多个 instrument，entity 复用——这正是身份模型的意义。

### Step 3 — 复制行情（copy，不做任何数值变换）

```sql
INSERT INTO market_prices_daily
  (instrument_id, trade_date, open, high, low, close,
   volume, volume_unit, turnover, turnover_unit, currency_code,
   adjustment_type, source_id, ingested_at)
SELECT m.instrument_id, d.trade_date, d.open, d.high, d.low, d.close,
       d.vol, 'LOTS', d.amount, 'THOUSAND_CNY', 'CNY',
       'RAW', <tushare_source_id>, <now_utc>
FROM daily_bars d JOIN _mig_ts_code_map m ON m.ts_code = d.ts_code;
```

- **数值原样复制**：open/high/low/close 直接搬；vol→volume（单位标注 LOTS）、amount→turnover（单位标注 THOUSAND_CNY），**不做乘除换算**（换算在查询层，避免引入换算错误）。
- `pre_close / change / pct_chg` **不迁移**：可从 OHLC 推导，且属于派生值；如 Berlin 需要保留原始派生列，可加列（R1B 决策点）。
- 一个 source_id：Tushare（`data_sources.source_code='TUSHARE'`），dataset_id：`CN_EQUITY_DAILY`。

### Step 4 — 验证（验证不通过 → 不回滚，先修复；全部通过才进入 Step 5）

| # | 检查项 | 通过标准 |
|---|--------|---------|
| V1 | 行数 | `COUNT(market_prices_daily WHERE source=TUSHARE) == COUNT(daily_bars)` 且 = 5,540（基准数） |
| V2 | 键无损 | 逐 `(ts_code, trade_date)` 对比：canonical 行数 == legacy 行数，无缺失、无多余 |
| V3 | 数值无损 | 按 ts_code 分组对比 open/high/low/close/vol/amount 的 `SUM` 与 `COUNT(非NULL)` 完全一致 |
| V4 | 逐行抽查 | 随机 100 行全字段逐值相等 |
| V5 | NULL 泄漏 | canonical 无新增 NULL（legacy NULL 位置一致） |
| V6 | 完整性 | 所有 instrument_id 存在、所有 source_id/dataset_id 存在、trade_date 格式合法 |
| V7 | 校验和 | 全表 `SUM(close)` 等聚合值与 legacy 一致（最终兜底） |

验证脚本输出逐项 PASS/FAIL 报告，FAIL 即中止（见 Step 6）。

### Step 5 — 切换（双写期）

- 迁移 + 验证通过后，新数据（fetch_daily.py 改造版）开始写 `core.db.market_prices_daily`；
- **legacy `daily_bars` 保留不删**，进入 30 天观察期；
- 观察期内每日对比：`market_prices_daily` 新增行数 == 预期交易日行情数，且与 legacy 并行运行结果一致（若 legacy 继续更新则双写对比）。

### Step 6 — Rollback（任何一步失败）

- 迁移失败 → 直接中止，legacy 未动、canonical 半成品可整体删除重来（canonical 是新建库，删除无风险）；
- 观察期发现问题 → 停写 canonical，恢复 legacy 写入，修复后重跑；
- **Rollback 成本 = 删除新库行 + 恢复 legacy 指针**，legacy 自始至终未被动过。

### Step 7 — 旧表处理（什么条件下才能删除）

删除 `daily_bars`（或 `market.db`）必须**同时满足**：

1. 观察期 ≥ 30 天且每日一致性对比全通过；
2. `market_prices_daily` 已连续 N 天由新 pipeline 成功写入（无缺口）；
3. 最终备份 `data/market_backup_*.db` 存在且校验可读；
4. **Berlin 明确批准**（PROJECT_RULES §6：删除重要数据需用户授权）。

在此之前：`daily_bars` 以只读方式保留在 `market.db`（或将 market.db 重命名 `market_legacy.db` 归档，不删除）。

---

## 3. 明确不做的事（本轮/本方案边界）

- ❌ 本轮不执行任何上述步骤（R1B 才实施）；
- ❌ 不修改 `fetch_daily.py` 生产逻辑（R1B 另建新 pipeline，旧脚本保留到切换完成）；
- ❌ 不做数值换算（vol→股、amount→元）——保留 raw + 显式单位；
- ❌ 不合并重复 ts_code、不猜 entity 映射（映射失败进 data_gaps）。
