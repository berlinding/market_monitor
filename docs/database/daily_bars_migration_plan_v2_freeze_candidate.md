# daily_bars Migration Plan v2 — Freeze Candidate

> 现有 `daily_bars`（Tushare A股日线）→ canonical schema 迁移方案
> 日期：2026-08-22 ｜ **Status: FREEZE CANDIDATE — NOT YET APPROVED**
> 基于 `daily_bars_migration_plan_v1.md` 修订；v1 保留不覆盖。
> **本轮不执行任何迁移**（不建 core.db/private.db，不改 market.db，不动 fetch_daily.py）。

---

## 0. 现状（2026-08-22 只读复核）

`data/market.db`（legacy）：

```
daily_bars(ts_code, trade_date, open, high, low, close, pre_close, change, pct_chg, vol, amount)
  PK(ts_code, trade_date)   -- 16,620 行 = 3 个交易日（08-14: 5,540 / 08-17: 5,539 / 08-20: 5,541）；distinct ts_code = 5,546
fetch_log(trade_date, fetched_at, rows, note)
```

- **文件未被修改**（sha256 = `93562960aa...d599004`，与 R1A.1 核对一致；git 忽略 `*.db`）。
- 数据来源：Tushare `daily` 接口（RAW 不复权）。
- 最近抓取（fetch_log）：2026-08-20 21:55（5541 行）。早期文档“5,540 条”为 2026-08-14 单日抓取口径，非当前总量。

目标（R1B 实施）：

```
entity_identifiers / instruments / instrument_identifiers (TUSHARE TICKER=ts_code)
        │
        ▼
market_prices_daily (instrument_uid, trade_date, OHLC, volume=LOTS, turnover=THOUSAND_CNY,
                     adjustment_type='RAW', source_id=TUSHARE, ingest_run_id, raw_artifact_id)
```

---

## 1. v2 关键修订（B14 —— Legacy Migration Provenance）

### 1.1 双完整性定义（替代"字段层完全无损"）

v1 声称"数值原样复制、键无损"。v2 明确定义：

> **normalized canonical completeness**（canonical 表内：键完整、行数一致、normalized 字段完整）
> **＋**
> **raw provenance completeness**（legacy 原始数据完整保留：备份 + raw_artifact + SHA-256，可随时重放）

**不再声称字段层完全无损**：`pre_close` / `change` / `pct_chg` 属派生值，**不进入 canonical**（可从 OHLC 推导）；其原始形式保留在 legacy 备份与 raw_artifact 中，任何时刻可复核。

### 1.2 Legacy 注册为 raw_artifact（B12/B14）

迁移前必须完成：

1. `data/market.db` 完整复制为 `data/market_backup_YYYYMMDD.db`（不删除原件）；
2. 计算备份文件 SHA-256；
3. `raw_artifacts` 登记一条：`artifact_type='DB_SNAPSHOT'`、`dataset_id=CN_EQUITY_DAILY`（或 LEGACY_DAILY_BARS）、`source_id=TUSHARE`、`run_id=NULL`（手工登记）、`local_path_or_reference=data/market_backup_YYYYMMDD.db`、`content_hash=SHA-256`、`retrieved_at`。

### 1.3 ingest_run 血缘（B13）

迁移本身作为一次 `ingest_runs` 记录（trigger_type='BACKFILL'），`market_prices_daily` 每行写 `ingest_run_id`；若迁移直接从备份文件读取，可同时关联 `raw_artifact_id`。之后生产行情每行带真实 ingest_run_id。

---

## 2. 迁移前置（R1B 开始前必须完成）

1. 建 canonical 库：`data/runtime/core.db` + `data/private/private.db`（R1B DDL，含 schema_migrations）。
2. **备份 + 注册 raw_artifact（§1.2）**。
3. 冻结写入：迁移期间暂停 fetch_daily.py 对 market.db 的写入（迁移完成后新数据直写 core.db）。

---

## 3. 迁移步骤（copy + validate，v2 更新）

### Step 1 — 创建 Entity（公司主体）

- 从 `daily_bars` 提取去重 `ts_code`（预计 ~3,000–5,000 个）；
- 每个 ts_code 对应一家 A 股公司 → 用 Tushare `stock_basic` 建立 `entities`（canonical_name=股票名称，country_code='CN'，entity_type='COMPANY'）＋ `entity_uid`（UUIDv4）；
- 缺失/失败的公司：登记 `data_gaps`，不阻塞迁移。

> ⚠️ 本轮禁止下载真实 stock_basic（见 §6 Not Done）；此步仅为 R1B 方案描述。

### Step 2 — 创建 Instrument + Identifier

对每个 ts_code：

1. 解析 `symbol`（`600519`）与 `exchange`（`.SH`→XSHG，`.SZ`→XSHE）；
2. `INSERT INTO instruments (entity_id, instrument_uid, instrument_type='EQUITY', primary_symbol, exchange_code, currency_code='CNY', country_code='CN', listing_date)`；
3. `INSERT INTO instrument_identifiers (instrument_id, provider='TUSHARE', identifier_type='TICKER', identifier=ts_code, valid_from=list_date, valid_to=NULL, is_primary=1)`；
4. 建立临时映射表 `_mig_ts_code_map(ts_code → instrument_id, instrument_uid)`（仅迁移期存在）。

**1 ts_code → 1 canonical instrument 保证不变**；A+H 或历史代码对应多个 instrument、entity 复用。

### Step 3 — 复制行情（copy，不做任何数值变换）

```sql
INSERT INTO market_prices_daily
  (instrument_id, instrument_uid 引用已含于 instrument_id, trade_date, open, high, low, close,
   volume, volume_unit, turnover, turnover_unit, currency_code,
   adjustment_type, source_id, ingest_run_id, raw_artifact_id, ingested_at)
SELECT m.instrument_id, d.trade_date, d.open, d.high, d.low, d.close,
       d.vol, 'LOTS', d.amount, 'THOUSAND_CNY', 'CNY',
       'RAW', <tushare_source_id>, <backfill_run_id>, <legacy_artifact_id>, <now_utc>
FROM daily_bars d JOIN _mig_ts_code_map m ON m.ts_code = d.ts_code;
```

- 数值原样复制；vol→volume（LOTS）、amount→turnover（THOUSAND_CNY），**不做乘除换算**。
- `pre_close / change / pct_chg` **不迁移**（B14：不进 canonical；原始值在 raw_artifact 中可追溯）。

### Step 4 — 验证（v2 更新：双完整性清单）

| # | 检查项 | 通过标准 |
|---|--------|---------|
| V1 | 行数 | `COUNT(market_prices_daily WHERE source=TUSHARE) == COUNT(daily_bars)` == 16,620（2026-08-22 复核基准，3 个交易日） |
| V2 | 键无损 | 逐 `(ts_code, trade_date)` 对比：无缺失、无多余 |
| V3 | 数值无损 | open/high/low/close/vol/amount 按 ts_code 分组 SUM 与 COUNT(非NULL) 一致 |
| V4 | 逐行抽查 | 随机 100 行全字段逐值相等 |
| V5 | NULL 泄漏 | canonical 无新增 NULL |
| V6 | 完整性 | instrument_id 存在、source/dataset/ingest_run 存在、trade_date 合法 |
| V7 | 校验和 | 全表 SUM(close) 等聚合一致（兜底） |
| **V8** | **raw provenance** | legacy 备份存在 + SHA-256 与 raw_artifacts.content_hash 一致（B14） |
| **V9** | **ingest 血缘** | 每行 ingest_run_id 非 NULL 且指向 backfill run；raw_artifact_id 可空但若填写必须存在（B13） |

### Step 5 — 切换（双写期）

- 迁移 + 验证通过后，新数据（fetch_daily.py 改造版）写 `core.db.market_prices_daily`；
- **legacy `daily_bars` 保留不删**，30 天观察期；
- 观察期内每日对比新增行数与预期交易日行情数一致。

### Step 6 — Rollback（任何一步失败）

- 删除/不提交 core.db 中该 backfill 相关行（`ingest_run_id` 过滤），legacy 未动，可重来；
- 迁移脚本必须幂等：重复运行以 `UNIQUE(instrument_id, trade_date, adjustment_type, source_id)` 冲突检测，不产生重复行。

---

## 4. v1→v2 变更汇总

| 项 | v1 | v2 |
|----|----|----|
| 跨库引用 | instrument_id 整数 | **instrument_uid（UUIDv4）**（B3） |
| 完整性定义 | 字段层无损 | **normalized completeness + raw provenance completeness**（B14） |
| legacy 处理 | 备份即可 | 备份 + **注册 raw_artifact + SHA-256**（B12/B14） |
| ingest 血缘 | 无 | **ingest_run_id 必填 + raw_artifact_id 可选**（B13） |
| 验证清单 | V1–V7 | **V1–V9**（+V8 provenance、V9 lineage） |
| pre_close/change/pct_chg | 不迁移（决策点） | **明确不迁移，属派生值，raw 可追溯**（B14） |
| entities | canonical_name UNIQUE | canonical_name 非唯一 + entity_uid（B2/B3） |

---

## 5. 风险与残余

- 残余：迁移脚本质量依赖 R1B 实现（V1–V9 清单逐项 PASS/FAIL）。
- 残余：stock_basic 拉取失败的公司 → data_gaps，行情仍迁移。
- 无数据删除风险：legacy 保留 + 备份 + artifact 注册，任何一步可回滚。

---

## 6. Not Done（本轮严格不执行）

- ❌ 未创建 core.db / private.db
- ❌ 未迁移 daily_bars（当前 16,620 行 / 3 个交易日，全部保留）
- ❌ 未修改 `data/market.db`（legacy 原样）
- ❌ 未修改 `fetch_daily.py` 生产路径
- ❌ 未下载真实 stock_basic
- ❌ 未接 FMP / SEC / OpenBB
