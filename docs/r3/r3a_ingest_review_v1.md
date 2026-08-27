# R3-A Review — Canonical Incremental Daily-Bar Ingestion（v1）

> 日期：2026-08-27 ｜ Status: PASS（Blocking findings = 0）
> 范围：A 股日线 canonical 增量入库（`scripts/ingest_daily.py`）+ production smoke + 全量 reconciliation
> 前置：R1/R2 COMPLETE；production core.db 已初始化（R2 Part A）

## 1. Ingestion Architecture

```
legacy market.db (fetch_daily.py 每日写入, read-only)
   │  --date YYYY-MM-DD / --latest
   ▼
ingest_daily.py
   1. load_legacy_day()     读取该交易日 daily_bars（ts_code/o/h/l/c/vol/amount）
   2. export_raw_payload()  导出 data/raw/tushare/daily_YYYY-MM-DD.json（sha256）→ raw_artifact
   3. resolve_dataset/source CN_EQUITY_DAILY(1) / TUSHARE(1) / PRIMARY link
   4. build_ts_code_map()   通过 instrument_identifiers(TUSHARE/EXCHANGE_SYMBOL) 解析稳定 instrument_uid
   5. identity expansion    新 ts_code（新上市/复牌）→ 从已注册 stock_basic artifact 解析并新建 instrument
   6. BEGIN IMMEDIATE        事务：ingest_run(RUNNING) + raw_artifact + bars(controlled upsert) + SUCCESS
   7. post-validation        loaded == expected，否则回滚 + FAILED run
   ▼
production core.db.market_prices_daily（source_id/ingest_run_id/raw_artifact_id 全链）
```

- **幂等**：`ON CONFLICT(instrument_id, trade_date, adjustment_type, source_id) DO UPDATE`（DB-D031 延续）——重跑同日 row count 不变。
- **失败语义**：未知 instrument（core+stock_basic 均无）/ 异常日期（legacy 无数据）/ NULL 必填字段 / mapping 不完整 → 明确异常，0 行写入，绝不静默丢行。
- **Production guard**：写 production 路径需 `--allow-production`（R3-A Berlin 授权）；`--reconcile` 只读。

## 2. Production Smoke（真实新交易日）

| 交易日 | legacy rows | canonical rows | mapping coverage | mismatch | run_id |
|---|---|---|---|---|---|
| 2026-08-25 | 5,546 | 5,546 | 100% | 0 | 8 |
| 2026-08-26 | 5,547 | 5,547 | 100% | 0 | 9 |

- **Identity expansion（实测）**：08-25 首次出现 2 个 core 中不存在的 ts_code：
  - `600984.SH` 建设机械（listing 2004-07-07，**复牌**首日）
  - `688835.SH` 高凯技术（listing 2026-08-25，**新上市**首日）
  - 均从已注册 stock_basic artifact（raw_artifacts id=2）解析创建；**已有 5,548 个 instrument_uid 全部未变**（5,550 = 5,548 + 2 新增）。
- **幂等重跑**：08-25 重跑（run 10）→ row count 仍 5,546；total 49,882 不变；dup keys = 0。
- **Reconciliation**：08-25 / 08-26 / 08-24（baseline sanity）全部 0 mismatch，legacy==canonical row count 与 OHLC/volume/turnover 逐行一致（含新上市 688835.SH 两日 bar 一致）。
- **Lineage**：ingest_runs 8/9/10 SUCCESS（rows_expected==rows_loaded）；raw_artifacts 3/4/5（FILE + content_hash==文件 sha256）；bars 全行 source_id/ingest_run_id/raw_artifact_id 非空（orphan=0）。
- **production core 最终状态**：49,882 bars / 9 个交易日（08-14→08-26）/ max trade_date **2026-08-26** / 5,550 instruments / 11,100 identifiers / 10 ingest_runs。

## 3. Tests

- **143 tests — OK（0 failed / 0 errors / 0 skipped）** = 128（上一轮）+ 15 新增：
  - `tests/test_r3_ingest.py`（11）：T-R3A-LOAD-01、IDEMPOTENT-01、UNKNOWN-01、BADDATE-01、PARTIAL-01、MAPPING-01、STABLEUID-01、LINEAGE-01、RECONCILE-01、GUARD-01、DISCOVER-01
  - identity expansion（4）：T-R3A-SYNC-01/02/03/04
- 全部 temp DB（TemporaryDirectory），未触碰 production DB（smoke 为独立授权步骤）。

## 4. Findings

- **Blocking：0**
- Non-blocking notes：
  1. identity expansion 依赖已注册 stock_basic artifact 的**时效性**——若某日出现全新上市且 stock_basic 快照早于上市日，需刷新 artifact（R3 稳定运行观察项）。
  2. `--latest` 自动发现依赖 legacy 已下载；若 legacy cron 失败，ingest 会因 legacy 无数据明确失败（符合设计）。
  3. trigger_type 当前 MANUAL；未来 cron 化用 SCHEDULED（decision R3-D005 已预留）。

## 5. Next（不自动执行）

- Berlin 审查本 review + r3a_decisions_v1.md → 授权 R3 稳定运行观察（连续多日自动增量入库）→ 再评估 R3-B（canonical fetch 独立化 / legacy 依赖解除）。
