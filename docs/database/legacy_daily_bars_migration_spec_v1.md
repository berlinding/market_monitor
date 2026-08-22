# Legacy daily_bars Migration Specification v1

> `data/market.db` daily_bars → canonical `market_prices_daily` 迁移规格
> 日期：2026-08-22 ｜ **Status: SPECIFICATION — NOT IMPLEMENTED / NOT EXECUTED**
> 依据：R1A v2 FROZEN + `daily_bars_migration_plan_v2_freeze_candidate.md` + B14 双完整性
> 本轮只写规格，**不执行任何迁移**（不建库、不改 market.db、不下载 stock_basic）。

---

## 0. Legacy 现状（2026-08-22 只读复核，事实基线）

| 项 | 值 |
|----|----|
| 文件 | `data/market.db`（2,252,800 bytes, mtime 2026-08-20 21:55） |
| SHA-256 | `93562960aa8296688cfd30d908984df62c4bb46978fb0d62ed1557aefd599004` |
| daily_bars 总数 | **16,620 行** |
| 交易日分布 | 2026-08-14 = 5,540 ／ 2026-08-17 = 5,539 ／ 2026-08-20 = 5,541 |
| distinct ts_code | **5,546** |
| fetch_log | 3 行（2026-08-16 23:39 / 2026-08-17 18:32 / 2026-08-20 21:55） |
| 最近抓取 | 2026-08-20 21:55（5541 行） |

daily_bars schema（legacy，本规格只读参考）：

```
daily_bars(ts_code, trade_date, open, high, low, close, pre_close, change, pct_chg, vol, amount)
  PK(ts_code, trade_date)
fetch_log(trade_date, fetched_at, rows, note)
```

---

## 1. 迁移分阶段总览（M0–M9）

| 阶段 | 名称 | 写入目标 | 可回滚 |
|------|------|---------|--------|
| M0 | Preflight | 无（只读 legacy） | — |
| M1 | Backup & Raw Artifact Registration | core.db: raw_artifacts | 是（删 artifact 行） |
| M2 | Source/Dataset Bootstrap | core.db: data_sources/datasets/dataset_sources | 是 |
| M3 | Entity/Instrument Bootstrap | core.db: entities/instruments | 是 |
| M4 | Identifier Mapping | core.db: instrument_identifiers + 临时映射表 | 是 |
| M5 | Ingest Run Backfill | core.db: ingest_runs | 是 |
| M6 | Daily Bar Copy | core.db: market_prices_daily | 是（按 run 过滤删除） |
| M7 | Validation | 只读校验 | — |
| M8 | Dual-write Observation | legacy + canonical 并行 | — |
| M9 | Retirement Gate | 决策点（Berlin 批准） | — |

每阶段必须在事务内完成或可整体回滚；**任何 abort 条件触发 → 立即停止，不"尽量迁完"**（§7）。

---

## 2. M0 — Preflight（只读，不写 legacy）

验证项：

1. `data/market.db` 存在且可只读打开；
2. `daily_bars` schema 与预期一致（列名/类型/主键 `(ts_code, trade_date)`）；
3. `fetch_log` schema 一致；
4. `COUNT(*)` == 16,620（以迁移时点实际值为准，2026-08-22 复核基线）；
5. distinct trade_date == 3，值 ∈ {20260814, 20260817, 20260820}；
6. distinct ts_code == 5,546；
7. NULL 检查：daily_bars 无意外 NULL（列级 count(null) 全部为 0）；
8. 重复 PK 检查：`SELECT COUNT(*) - COUNT(DISTINCT ts_code||trade_date) FROM daily_bars` == 0；
9. 计算 SHA-256、记录 file size / mtime / row counts → 写入 preflight 报告（log + 内存，不写 legacy）。

**通过后才进入 M1。** 任一失败 → ABORT。

---

## 3. M1 — Backup & Raw Artifact Registration（S5 修正：区分两种备份类型）

### 3.1 备份类型判定

| 类型 | 适用前提 | 要求 |
|------|---------|------|
| **Type A — Byte-for-byte frozen copy** | legacy writer 已停止；DB 状态稳定；WAL 已安全处理（checkpoint/无活跃事务）；使用明确文件级快照方案 | `source_sha256 == backup_sha256`（允许强校验） |
| **Type B — SQLite logical backup** | 使用 `sqlite3.Connection.backup()`（在线安全，推荐） | **不要求**源与备份字节相同；分别记录 `source_file_hash` 与 `backup_file_hash` |

**本规格默认采用 Type B（logical backup）**——避免“cp 正在写入的 SQLite 文件”的一致性风险，且逻辑备份字节不必与源相同。

### 3.2 Type B 校验（替代“源 hash == 备份 hash”的过强标准）

备份后对 **backup 文件**验证：

1. `PRAGMA integrity_check` == ok；
2. schema equality：表集合与列集合与源一致（`sqlite_master` 对比）；
3. `daily_bars` row count equality == 16,620；
4. `fetch_log` row count equality == 3；
5. trade_date distribution equality == {20260814, 20260817, 20260820}；
6. distinct ts_code equality == 5,546；
7. SUM / aggregate reconciliation（SUM(close)、SUM(vol)、SUM(amount) 按 trade_date）一致。

全部 PASS → backup 有效。任一 FAIL → ABORT。

### 3.3 raw_artifact hash 语义（S5 修正）

- **`content_hash` = 实际 backup artifact 文件自己的 SHA-256**（不是 source file hash）。
- migration report 单独记录：
  - `legacy_source_hash`（源文件 hash，M0 计算）
  - `backup_artifact_hash`（备份文件 hash，即 content_hash）
  - `backup_method`（如 `sqlite3.Connection.backup()`）
  - `backup_validation_result`（integrity + schema + row + aggregate 各 PASS/FAIL）

core.db 登记 raw_artifact（M2 后执行）：

- `artifact_type='DB_SNAPSHOT'`，`dataset_id=CN_EQUITY_DAILY`，`source_id=TUSHARE`，
  `run_id=NULL`（手工登记），`local_path_or_reference=data/raw/legacy/market_20260822_<hash8>.db`，
  `content_hash=backup_artifact_hash`（**备份文件自己的 SHA-256**），`retrieved_at=<now UTC>`。

### 3.4 Backup Gate（进入 M2/M3 前必须全部满足）

- backup created ✅
- backup integrity_check PASS ✅
- logical reconciliation PASS ✅
- backup hash recorded ✅

任一不满足 → **ABORT**（不进入 M2）。

---

## 4. M2 — Source/Dataset Bootstrap

初始化（幂等，存在则跳过/核对）：

- `data_sources`: `TUSHARE`（source_type='MARKET_DATA', status='ACTIVE'）
- `datasets`: `CN_EQUITY_DAILY`（dataset_type='PRICE_DAILY', granularity='DAILY',
  target_table='market_prices_daily', write_mode='UPSERT'）
- `dataset_sources`: (CN_EQUITY_DAILY, TUSHARE, role='PRIMARY', priority_rank=1, is_active=1)

不接入 FMP 等其它源（R1B 范围）。

---

## 5. M3 — Entity / Instrument Bootstrap（S4 修正：strict mapping gate）

**输入 artifact**：Tushare `stock_basic` 快照（ts_code, name, area, industry, list_date）。
执行前必须先下载并存为 raw_artifact（`data/raw/stock_basic_<date>.csv` 或等价），
登记 raw_artifact（artifact_type='FILE' / 'API_PAYLOAD'）。**迁移不直接调 API。**

### 5.0 交易所 suffix 支持（S4 修正，2026-08-22 复核 legacy 实际 suffix）

legacy `daily_bars` 实际出现的 ts_code suffix（只读枚举）：

| suffix | 交易所 | MIC | 示例 |
|--------|--------|-----|------|
| `.SH` | 上海证券交易所 | `XSHG` | `600519.SH` |
| `.SZ` | 深圳证券交易所 | `XSHE` | `000001.SZ` |
| `.BJ` | 北京证券交易所 | `XBSE` | `83xxxx.BJ` / `43xxxx.BJ` 等 |

- M0 preflight 必须**从 legacy 数据枚举全部实际 suffix**，并校验每个 suffix 都有 deterministic MIC mapping（上述表）。
- **出现未映射 suffix → ABORT**（不得硬编码 `.SH/.SZ` 而遗漏北交所）。
- 注意：北交所股票（`.BJ`）在 Tushare 体系中存在，mapping 不得遗漏。

流程（未来执行，R1C 实现）：

1. 从 stock_basic 快照读取去重 ts_code（必须与 legacy distinct 5,546 完全一致——**strict mapping gate，见 §5.0/§6**）；
2. 每个 ts_code：
   - `entities`：canonical_name=股票名称，entity_type='COMPANY'，country_code='CN'，
     `entity_uid=uuid4()`（**不是** hash(ts_code)，永久随机身份）；
   - `instruments`：instrument_type='EQUITY'，primary_symbol=ts_code 拆出交易所符号（如 `600519`），
     exchange_code=按 §5.0 suffix→MIC 映射（XSHG/XSHE/XBSE），currency_code='CNY'，country_code='CN'，listing_date=list_date，
     `instrument_uid=uuid4()`；
   - 同一公司 A+H/ADR 未来靠 entity_identifiers + manual reconciliation 合并，**不由 ts_code 直接等同**（§5.1）；
3. **mapping issue（stock_basic 缺失 ts_code / duplicate mapping / ambiguous mapping / unknown exchange）→ 记录 diagnostic（可同时写 data_gap 作为诊断记录）→ ABORT migration**。
   **data_gaps 只用于记录问题，不代表可以带着未映射 instrument 继续 M6。** 修完 mapping 后重新运行。

### 5.1 Entity 创建策略（关键）

- A股普通股票：一个上市公司 Entity → 一个主要 A-share Instrument；
- **Entity 不是 ts_code 的投影**：未来同一公司可能有 A/H/ADR 多 instrument；
  首次 bootstrap 基于 stock_basic 创建 entity，identity future merge 依赖
  `entity_identifiers`（LEI/SEC_CIK/PROVIDER_COMPANY_ID）+ 公司官方标识 + manual reconciliation；
- `entity_uid` / `instrument_uid` 必须随机 UUIDv4，**不得** `uid = hash(ts_code)`（hash 可被逆向/碰撞，且非稳定身份语义）。

### 5.2 ts_code identifier 类型（决策）

- `ts_code`（如 `600519.SH`）→ `instrument_identifiers`：
  - `provider='TUSHARE'`，`identifier_type='EXCHANGE_SYMBOL'`，`identifier='600519.SH'`，`is_primary=1`，`valid_from=list_date`
- 拆出的交易所符号（`600519`）→ 同一 instrument 第二行：
  - `provider='STANDARD'`，`identifier_type='TICKER'`，`identifier='600519'`（或视 Berlin 偏好调整）

> 采用 EXCHANGE_SYMBOL 理由：ts_code 是 Tushare 的交易所符号命名空间（含 `.SH/.SZ/.BJ` 后缀），
> 语义上属于"交易所符号"而非纯报价 ticker；TICKER 留给未来更通用的 provider 符号。
> 迁移期对 ts_code 做 UNIQUE 校验（重复 → 报错中止，绝不静默合并）。
> **strict mapping gate（S4）**：legacy distinct ts_code（5,546）必须 == mapped instrument count，
> 才允许进入 M5/M6。任何 stock_basic missing / duplicate / ambiguous / unknown exchange →
> ABORT BEFORE BAR COPY。

---

## 6. M4 — Identifier Mapping（S4 修正：strict gate）

- 建临时映射表 `_mig_ts_code_map(ts_code → instrument_id, instrument_uid)`（仅迁移期存在，完成后删除）；
- 每行来自 M3 建立的 instrument + instrument_identifiers；
- **strict mapping gate**：
  `COUNT(DISTINCT legacy ts_code) == COUNT(_mig_ts_code_map rows)` 必须成立（当前基线 5,546 == 5,546）；
- 任何无法映射的 ts_code → **ABORT BEFORE BAR COPY**（不允许带着未映射 instrument 继续）。

---

## 7. M5 — Ingest Run Backfill（S2 修正：legacy timestamp 时区语义）

legacy fetch_log 3 行 → 3 条 `ingest_runs`（**started_at 必须经时区转换，见 §7.1**）：

| legacy fetch_log（raw） | ingest_runs（转换后） |
|------------------------|----------------------|
| (20260814, fetched_raw=2026-08-16T23:39:29, 5540) | run1: dataset=CN_EQUITY_DAILY, source=TUSHARE, trigger_type='BACKFILL', started_at=<见 §7.1 转换>, status='SUCCESS', rows_loaded=5540 |
| (20260817, fetched_raw=2026-08-17T18:32:14, 5539) | run2: started_at=<见 §7.1 转换>, rows_loaded=5539 |
| (20260820, fetched_raw=2026-08-20T21:55:33, 5541) | run3: started_at=<见 §7.1 转换>, rows_loaded=5541 |

- mapping 键：`fetch_log.trade_date == daily_bars.trade_date`（直接匹配；格式统一为 YYYYMMDD）。
- **任何 trade_date 无对应 fetch_log 行 → ABORT**（不能默默制造 run）。
- 每行 daily_bars 的 `ingest_run_id` 由 trade_date 反查映射表。

### 7.1 Legacy Timestamp Timezone Policy（S2 修正，强制）

**事实**：`fetch_daily.py`（scripts/fetch_daily.py:165）用 `datetime.now().isoformat(timespec="seconds")`
写 `fetch_log.fetched_at` → 这是 **naive local timestamp**（如 `2026-08-16T23:39:29`），**不是 UTC**。
**严禁**直接把它标成 `...T23:39:29Z`。

规则：

1. **原始值永久保留**：migration report / notes 至少保留 `legacy_fetched_at_raw`（如 `2026-08-16T23:39:29`），不得丢失。
2. **必须确定 legacy host timezone**：R1C 执行前确认 legacy market.db 写入时主机（AI 机 Windows/WSL）实际时区。
   交叉验证来源：系统配置记录、日志时间、Git/cron 时间、fetch 日志与已知执行时间、Berlin 已知机器时区。
3. **若能确证为 Asia/Shanghai（UTC+08:00）**：
   `2026-08-16T23:39:29` → attach Asia/Shanghai → `2026-08-16T15:39:29Z`（正确转换）。
4. **若无法可靠证明时区**：**不得伪造 UTC**。设 `timestamp_resolution_status = UNRESOLVED`，
   **迁移暂停 ingest_run timestamp conversion，等待 Berlin 明确决定**——这是 migration abort/gate 条件之一。
5. 状态记录：`timestamp_resolution_status = CONFIRMED | UNRESOLVED`；
   CONFIRMED 时记录 `confirmed_timezone`（如 `Asia/Shanghai`）与依据。

---

## 8. M6 — Daily Bar Copy

字段映射（copy，不做数值变换）：

| daily_bars | market_prices_daily | 说明 |
|------------|---------------------|------|
| ts_code | instrument_id | 经 _mig_ts_code_map |
| trade_date | trade_date | 格式归一（YYYYMMDD → YYYY-MM-DD，应用层转换） |
| open/high/low/close | open/high/low/close | 原样 |
| vol | volume, volume_unit='LOTS' | 不换算 |
| amount | turnover, turnover_unit='THOUSAND_CNY' | 不换算 |
| — | currency_code='CNY' | 常量 |
| — | adjustment_type='RAW' | 常量 |
| — | source_id=TUSHARE | 常量 |
| — | ingest_run_id | 经 M5 映射（**必填**） |
| — | raw_artifact_id | = M1 legacy snapshot artifact（**必填**） |
| — | ingested_at | 迁移执行时刻 UTC（应用层写入） |
| **pre_close/change/pct_chg** | **不进入 canonical** | 派生值；原始值保留在 raw snapshot（B14） |

SQL 形态（规格，不执行）：

```sql
INSERT INTO market_prices_daily
  (instrument_id, trade_date, open, high, low, close,
   volume, volume_unit, turnover, turnover_unit, currency_code,
   adjustment_type, source_id, ingest_run_id, raw_artifact_id, ingested_at)
SELECT m.instrument_id, d.trade_date, d.open, d.high, d.low, d.close,
       d.vol, 'LOTS', d.amount, 'THOUSAND_CNY', 'CNY',
       'RAW', :tushare_source_id, :run_id, :legacy_artifact_id, :now_utc
FROM daily_bars d JOIN _mig_ts_code_map m ON m.ts_code = d.ts_code
WHERE d.trade_date = :trade_date;
```

按 trade_date 分批（每批对应一个 run），批内事务。

---

## 9. M7 — Validation（V1–V12）

| # | 检查项 | 通过标准 |
|---|--------|---------|
| V1 | row count | `COUNT(market_prices_daily WHERE source=TUSHARE) == COUNT(daily_bars)`（16,620，以迁移时点为准） |
| V2 | trade dates | canonical 日期集合 == legacy 日期集合（{2026-08-14, 2026-08-17, 2026-08-20}） |
| V3 | instrument mapping completeness | **legacy distinct ts_code == mapped instrument count（100%，strict gate）**；无未映射 |
| V4 | duplicate canonical keys | `UNIQUE(instrument_id, trade_date, adjustment_type, source_id)` 无冲突 |
| V5 | OHLC equality | 逐 (ts_code, trade_date) 对比 open/high/low/close 全等（抽查 100 行 + 聚合） |
| V6 | volume equality | vol == volume（SUM 按 trade_date 对比，tolerance=0） |
| V7 | turnover equality | amount == turnover（SUM 按 trade_date 对比，tolerance=0） |
| V8 | NULL / type validation | canonical 无新增 NULL；数值类型正确 |
| V9 | source/run lineage | 每行 source_id=TUSHARE 且 ingest_run_id 非 NULL 且存在；raw_artifact_id 存在；ingest_run.started_at 时区状态为 CONFIRMED |
| V10 | raw artifact existence/hash | M1 backup artifact 文件存在且 SHA-256 == raw_artifacts.content_hash（**backup artifact 自身 hash**） |
| V11 | orphan instrument refs | 所有 instrument_id 存在于 instruments；entity 可空但若存在则有效 |
| V12 | aggregate reconciliation | 按 trade_date 对比 `SUM(volume)` / `SUM(turnover)`，允许浮点 tolerance（如 1e-6 相对误差） |

- 任何 FAIL → 不回滚已迁数据，先诊断修复；修复后重跑校验；全部 PASS 才进入 M8。
- V1–V12 输出逐项 PASS/FAIL 报告。

---

## 10. Abort Conditions（任一触发 → 立即 ABORT，不"尽量迁完"）

1. 任何 ts_code 无法 mapping（M4 strict gate；当前基线 5,546 必须全部映射）；
2. row count mismatch（V1）；
3. duplicate canonical key（V4）；
4. hash mismatch（M1 backup artifact hash / V10）；
5. OHLC / volume / turnover mismatch 超出 tolerance（V5–V7, V12）；
6. 缺失 ingest_run（M5 / V9）；
7. foreign key violation（SQLite 约束错误）；
8. M0 preflight 任何一项失败；
9. **unsupported ts_code suffix（未知交易所，无 deterministic MIC mapping）→ ABORT（S4）**；
10. **legacy timestamp timezone UNRESOLVED → 暂停 ingest_run 转换，ABORT/gate（S2）**。

---

## 11. M8 — Dual-write Observation（政策）

- 迁移 + 验证通过后，canonical pipeline 开始写 `market_prices_daily`；legacy `daily_bars` 保留并行观察。
- 观察期（DB-D033）：**至少 20 个交易日，且不少于 30 个 calendar days，取较晚者**。
- 观察期每日对比：canonical 新增行数 == 预期交易日行情数，且与 legacy 并行结果一致。

---

## 12. M9 — Retirement Gate

停止 legacy write 的充要条件（全部满足 + **Berlin 明确批准**）：

1. Migration validation V1–V12 100% PASS；
2. Dual-write observation 通过（≥20 trading days 且 ≥30 calendar days，取较晚者）；
3. 无 unresolved data gaps；
4. Raw backup verified（M1 backup artifact 存在且 hash == content_hash；integrity_check PASS）；
5. Rollback tested（M6 按 run 删除 + 重放演练通过）；
6. Berlin explicit approval。

- 即使停止：legacy raw snapshot **永久保留**（`data/raw/legacy/`）。
- 原 `data/market.db` 是否删除：**必须另行授权**，本规格不授权删除。

---

## 13. Not Done（本轮）

- ❌ 未创建 core.db / private.db
- ❌ 未迁移任何 daily_bars（16,620 行全部保留）
- ❌ 未下载 stock_basic
- ❌ 未修改 fetch_daily.py / legacy market.db
- ❌ 未启用 dual-write
- ❌ 未执行任何 SQL
