# PROJECT_STATUS.md

## Current Snapshot

Current Stage: R1 — Core Data Model **COMPLETE**（R1 Finalization Gate PASS 2026-08-25）
System Status: Development
Production Monitoring: NOT ENABLED
Automated Trading: DISABLED
## Roadmap

R0 — Project Governance & Architecture
R1 — Core Data Model
R2 — Portfolio & Watchlist
R3 — Data Pipeline
R4 — Event Engine
R5 — Event Intelligence
R6 — Alert System
R7 — Daily Briefing
R8 — Historical Intelligence
R9 — Quant Layer

## Completed

- R0 — Project Governance & Architecture（2026-08-17）
- R1A v1 — Core Domain Model & Data Contract（2026-08-17，设计未实施）
- Credential Security（2026-08-17，API.txt 保密规则）
- R1A.1 — Recovery, Repository Reconciliation & Schema Freeze Candidate（2026-08-22）
- R1A.2 — Final Freeze Corrections（2026-08-22，F1–F8 修正）
- **R1A v2 — FROZEN**（2026-08-22，Berlin 批准）
- **R1B — SQL DDL & Migration Specification**（2026-08-22，只写不执行）
- **R1B.1 — Implementation Safety Corrections**（2026-08-22，S1–S6 修正）
- **R1C Phase 0 — Pre-Implementation Reconciliation**（2026-08-22，P0-1/P0-2/P0-3）
- **R1C Phase 1 — Temp-DB Implementation & Validation**（2026-08-22，62 tests OK）
- **R1C Phase 1.1 — Final Pre-Production Hardening**（2026-08-22，H1–H4，77 tests OK）
- **R1C Phase 1.2 — Canonical Date Contract Fix**（2026-08-22，D1–D5，99 tests OK）
- **R1C Phase 2 — Full-Scale Real-Data Staging Rehearsal**（2026-08-25，**FINAL RESULT: PASS**：real market.db → frozen snapshot → 真实 stock_basic → staging core/private.db → 38,789 行全量迁移 → V1–V18 全 PASS + 100% full-row reconciliation 0 mismatch）
- **R1 Finalization Gate — Clean-Commit Reproducibility Rehearsal**（2026-08-25，**FINAL RESULT: PASS**：commit `a6007b3` clean tree 上独立复现真实 staging，git_dirty=false，runner 属 HEAD，**R1 — Core Data Model: COMPLETE**）

## Current

- **R1 Finalization Gate complete — awaiting Berlin review of finalization artifacts**
- 实现：`scripts/migrate.py`（runner）+ `scripts/db_validators.py` + `scripts/timestamp_utils.py` + `scripts/date_utils.py` + `scripts/legacy_migration_utils.py` + `scripts/phase2_staging_rehearsal.py`（含 reproducibility gate）
- 测试：`tests/` 8 个文件，**Ran 103 tests — OK（0 failed / 0 errors / 0 skipped）**
- Review：`docs/database/r1c_phase1_review_v1.md`（C1–C34 全 PASS）+ `docs/database/r1c_phase2_review_v1.md`（P2-1…P2-10）+ `docs/database/r1_finalization_review_v1.md`（**Blocking findings = 0**）
- Decision Register：DB-D001–D057
- 无进行中的实施工作；**未创建任何生产数据库，未执行真实迁移**

## Validation（R1C Phase 1.2）

- Canonical trade_date = YYYY-MM-DD PASS（legacy 20260814 → canonical 2026-08-14；T-CANONICAL-TRADE-DATE-01）
- Canonical listing_date = YYYY-MM-DD PASS（20010827 → 2001-08-27；T-CANONICAL-LIST-DATE-01）
- Canonical valid_from = YYYY-MM-DD PASS（instrument_identifiers.valid_from == 2001-08-27）
- Invalid dates fail-fast PASS（20260230/20261340/abcdefgh/空 → DateNormalizationError / MappingGateError）
- Snapshot manifest JSON-safe PASS（json.dumps 成功；T-MANIFEST-JSON-01）
- V2/V12 校验用 normalized date semantics（不再 raw==raw oracle）
- 其余全部 PASS：Temp core/private schema、runner atomicity、constraints、cross-db uid、legacy fixture、privacy、H1–H4
- 真实 legacy 时区：**CONFIRMED = Asia/Shanghai**

## Real DB

- **NOT CREATED**（data/runtime/core.db / data/private/private.db 均未创建；PRODUCTION_PATHS 硬拒绝）
- **Real Legacy Migration: NOT EXECUTED**（38,789 行全部原样保留）

## Staging Rehearsal（R1C Phase 2，2026-08-25 run `20260825T030439Z`）

- **FINAL RESULT: PASS**（report：`data/staging/r1c_phase2/20260825T030439Z/migration_report.json`，gitignored）
- 数据规模：38,789 行 / 7 交易日（08-14→08-24）/ 5,548 标的（SH·SZ·BJ）
- frozen snapshot：`data/raw/legacy/market_20260825T030439Z.db`（sha256 `ac5b2acd…`；8-23 旧快照保留）
- stock_basic：真实下载 5,550 条（L 单查覆盖 5,548/5,548 = 100%），CSV+meta 落盘 `data/raw/tushare/`
- staging：core.db（17 tables，C0001）+ private.db（8 tables，P0001），FK check 全空
- 迁移：5,548 entities / 5,548 instruments / 11,096 identifiers（1:1）、7 ingest_runs、38,789 bars 全量
- V1–V18 全 PASS；full-row reconciliation：38,789 行 checked，0 mismatch
- live market.db 运行前后 sha256 一致（`7b435961…`）

## R1 Finalization Rehearsal（2026-08-25 run `20260825T043812Z`）

- **FINAL RESULT: PASS**（report：`data/staging/r1_finalization/20260825T043812Z/r1_finalization_report.json`，gitignored）
- **Clean-commit reproducibility**：HEAD==origin/main==`a6007b3`，working tree clean，git_dirty=false
- runner 属 HEAD：HEAD runner sha256 `d429dae7…` == report runner_sha256（可精确重建）
- C0001 sha256 `0dd5b58e…` / P0001 sha256 `2cce514f…`（raw-byte 契约）
- 数据规模：38,789 行 / 7 交易日 / 5,548 标的；stock_basic 5,550 条（L 单查 100% 覆盖）
- staging：core.db（17 tables，C0001）+ private.db（8 tables，P0001），FK check 全空
- 迁移：5,548 entities / 5,548 instruments / 11,096 identifiers（1:1）、7 ingest_runs、38,789 bars 全量
- V1–V18 全 PASS；full-row reconciliation：38,789 行 checked，0 mismatch
- safety：production core/private 不存在、live 只读（sha256 before==after `7b435961…`）、token 未暴露、dual-write off

## Existing Prototype

- **Dividend / Quality Dashboard**（港股高股息/质量筛选面板）
- 位置：`prototypes/dividend_dashboard/`（`index.html` + `chart.umd.min.js` + `data/dashboard_data.js`；2026-08-22 从根目录迁入，git mv 保留历史）
- Status: **Prototype, not integrated with canonical DB**（未接入 core.db/private.db）
- 治理记录：`docs/prototypes/dividend_dashboard_status_v1.md`；决策：DB-D015
- 本轮不扩展、不继续开发；`Test1` 测试残留已于 2026-08-22 删除（独立 cleanup）

## Next

- **Berlin reviews R1 Finalization artifacts（`r1_finalization_report.json` + `r1_finalization_review_v1.md` + 103 tests）**；批准后进入 R2 Minimal Portfolio & Watchlist + vertical-slice MVP。
- 不自动开始生产迁移（PRODUCTION_WRITES_ENABLED 保持 False）；不自动开始 R2。

## Not Authorized

- 生产迁移：创建 data/runtime/core.db 或 data/private/private.db / 迁移真实 daily_bars / 启用 dual-write
- 修改 fetch_daily.py 生产行为
- Dashboard 继续开发

## Active Components

（暂无）

## Data Sources

- Tushare — A股行情/财务/指数（已接入，密钥在 `~/API.txt`）
- FMP — 美股/全球基本面（密钥已配置，未接入）
- Alpha Vantage — 美股/外汇/加密（密钥已配置，未接入）
- FRED — 美国宏观（密钥已配置，未接入）
- EIA — 能源（密钥已配置，未接入）
- US Census — 贸易/人口普查（密钥已配置，未接入）

## Data Status

### Current Live Legacy Snapshot（2026-08-25 finalization preflight 实测）

- `data/market.db`：A股日线 `daily_bars` **38,789 行 = 7 个交易日**（08-14: 5,540 / 08-17: 5,539 / 08-18: 5,540 / 08-19: 5,541 / 08-20: 5,541 / 08-21: 5,543 / 08-24: 5,545；distinct ts_code 5,548）+ `fetch_log` 7 条
- 最近一次抓取：2026-08-24 18:33（5545 行）；sha256 `7b435961…`（finalization 前后一致）
- **live mutable state**——每日下载 cron 可能继续追加新交易日，行数会增长

### Last Validated Staging Snapshot（2026-08-25 run `20260825T043812Z`）

- frozen snapshot `data/raw/legacy/market_20260825T043812Z.db`（sha256 `ac5b2acd…`）—— **validated frozen state**，migration 的唯一权威基线（P0-3/DB-D040）
- canonical 设计目标：`data/runtime/core.db`（public）+ `data/private/private.db`（private），R1B 实施，生产迁移未授权

## Runtime Status

- 开发阶段，无生产监控，无自动交易
- legacy downloader（`fetch_daily.py`）存在且每日 cron 运行；production canonical monitoring NOT ENABLED
- legacy downloader operational status（cron 健康度/缺口回补）requires separate R3 review

## Current Blockers

**R1B.1 完成后：Blocking findings remaining = 0 → No R1C blocker**（r1b_ddl_review_v1.md R1B.1 Addendum 确认）。

待 Berlin 决策的开放问题（不阻塞审查）：

1. sector/industry 是否 R1 就需要（否则 R2 建 entity_classifications）
2. financial_reports/financial_facts 是否随 FMP/SEC 接入提前升级（当前 Deferred）
3. ~~market_prices_daily upsert 策略~~ —— **已解决**：DB-D031 CONTROLLED UPSERT（不再开放）
4. ~~event_evidence 同源多版本证据是否需要 version 列~~ —— **已解决**：DB-D032/D036 evidence_key（R1 用 evidence_key；若未来需严格同源版本历史再评估 version 列）
5. legacy fetched_at 时区：R1C 执行前必须 CONFIRMED（Asia/Shanghai 或 Berlin 确认），否则迁移暂停（S2/DB-D035）

## Key Decisions（2026-08-25 R1 Finalization 增量，详见 DB-D054–D057）

- R1 real-data migration validated on clean committed code（DB-D054）
- Reproducibility report records dirty state and runner hash（DB-D055）
- R1 closed after real-data clean-commit validation（DB-D056）
- Future product work proceeds via vertical slice, not further R1.x expansion（DB-D057）

## Next Authorized Step

- Berlin 审查 R1 Finalization 产物（r1_finalization_report.json + r1_finalization_review_v1.md）→ 批准后 R2 Minimal Portfolio & Watchlist + vertical-slice MVP（生产迁移授权另议）
