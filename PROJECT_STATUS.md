# PROJECT_STATUS.md

## Current Snapshot

Current Stage: R1 — Core Data Model
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

## Current

- **R1C Phase 1/1.1 artifacts awaiting Berlin approval for Phase 2**
- 实现：`scripts/migrate.py`（runner）+ `scripts/db_validators.py` + `scripts/timestamp_utils.py` + `scripts/legacy_migration_utils.py`
- 测试：`tests/` 6 个文件，**Ran 77 tests — OK（0 failed / 0 errors / 0 skipped）**：C0001/P0001 temp 执行、runner 原子性、17+ 约束、cross-db uid、synthetic legacy fixture（T-FROZEN-SOURCE-01/T-BASELINE-01/T-SNAPSHOT-BASELINE-01/T-SNAPSHOT-HASH-01/T-BACKUP-01/T-MAPPING-01/T-MAPPING-DUPLICATE-01/T-MAPPING-MISSING-FIELD-01/T-TIMEZONE-01/02/T-CHECKSUM-CRLF-01/T-MIGRATION-ENCODING-01/T-CLI-ALL-DBPATH-01/T-PROD-SYMLINK-01）、隐私边界
- Review：`docs/database/r1c_phase1_review_v1.md`（C1–C19 + Phase 1.1 Addendum C20–C27 全 PASS，**Blocking findings = 0**）
- Decision Register：DB-D001–D049
- 无进行中的实施工作；**未创建任何真实数据库，未迁移数据**

## Validation（R1C Phase 1.1）

- Temp core schema（C0001 17 表）PASS
- Temp private schema（P0001 7 业务表 + schema_migrations）PASS
- Runner atomicity PASS（事务原子 + checksum raw-bytes + plan/status 无写 + 生产路径保护 + `--db all`+`--db-path` 拒绝）
- Snapshot baseline authority PASS（live 只做 health preflight；authoritative manifest 从 frozen snapshot 生成；validate_snapshot 不重开 live）
- stock_basic input validation PASS（duplicate / missing field → ABORT）
- Constraint tests PASS（17+ 案例）
- Synthetic legacy fixture PASS（frozen snapshot 唯一源 + dynamic baseline + mapping gate + backup Type B）
- Privacy tests PASS（core 无 private 数据；private 无 credential）
- 真实 legacy 时区：**CONFIRMED = Asia/Shanghai**（/etc/timezone + 系统 CST + git author +0800 交叉验证）

## Real DB

- **NOT CREATED**（core.db / private.db 均未创建；PRODUCTION_WRITES_ENABLED = False 强制保护）
- **Real Legacy Migration: NOT EXECUTED**（16,620 行全部原样保留）

## Existing Prototype

- **Dividend / Quality Dashboard**（港股高股息/质量筛选面板）
- 位置：`prototypes/dividend_dashboard/`（`index.html` + `chart.umd.min.js` + `data/dashboard_data.js`；2026-08-22 从根目录迁入，git mv 保留历史）
- Status: **Prototype, not integrated with canonical DB**（未接入 core.db/private.db）
- 治理记录：`docs/prototypes/dividend_dashboard_status_v1.md`；决策：DB-D015
- 本轮不扩展、不继续开发；`Test1` 测试残留已于 2026-08-22 删除（独立 cleanup）

## Next

- **Berlin reviews R1C Phase 1/1.1 artifacts（runner + 77 tests + review）**；批准后进入 R1C Phase 2 — Full-Scale Real-Data Staging Rehearsal（real market.db → real frozen snapshot → real stock_basic snapshot → staging core/private.db → full V1–V12 → Berlin review）。
- 不自动开始 Phase 2。

## Not Authorized

- R1C Phase 2（Full-Scale Real-Data Staging Rehearsal）
- 创建 data/runtime/core.db 或 data/private/private.db
- 真实 backup market.db / 下载真实 stock_basic / 迁移真实 daily_bars / 启用 dual-write
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

- `data/market.db`：A股日线（`daily_bars` **16,620 行 = 3 个交易日**（08-14: 5,540 / 08-17: 5,539 / 08-20: 5,541；distinct ts_code 5,546）+ `fetch_log` 3 条）—— 未改动，legacy 保留（2026-08-22 只读复核；sha256 与 R1A.1 一致）
- 最近一次抓取（fetch_log）：2026-08-20 21:55（5541 行）
- canonical 设计目标：`data/runtime/core.db`（public）+ `data/private/private.db`（private），R1B 实施

## Runtime Status

- 开发阶段，无生产监控，无自动交易
- ⚠️ cron `market-monitor-daily-download` 最近一次运行失败（模型连接超时，2026-08-21 前后），下次运行 2026-08-24 07:10（约）

## Current Blockers

**R1B.1 完成后：Blocking findings remaining = 0 → No R1C blocker**（r1b_ddl_review_v1.md R1B.1 Addendum 确认）。

待 Berlin 决策的开放问题（不阻塞审查）：

1. sector/industry 是否 R1 就需要（否则 R2 建 entity_classifications）
2. financial_reports/financial_facts 是否随 FMP/SEC 接入提前升级（当前 Deferred）
3. ~~market_prices_daily upsert 策略~~ —— **已解决**：DB-D031 CONTROLLED UPSERT（不再开放）
4. ~~event_evidence 同源多版本证据是否需要 version 列~~ —— **已解决**：DB-D032/D036 evidence_key（R1 用 evidence_key；若未来需严格同源版本历史再评估 version 列）
5. legacy fetched_at 时区：R1C 执行前必须 CONFIRMED（Asia/Shanghai 或 Berlin 确认），否则迁移暂停（S2/DB-D035）

## Key Decisions（2026-08-22 R1C Phase 1.1 增量，详见 DB-D045–D049）

- Frozen snapshot owns authoritative migration baseline：live 只做 health preflight；manifest 从 snapshot 生成；validate_snapshot 不重开 live（DB-D045）
- stock_basic duplicate identity input is fatal：显式校验，绝不 last-one-wins（DB-D046）
- Migration checksum = SHA-256(exact raw migration file bytes)，单次计算（DB-D047）
- --db all + --db-path 互斥，parser.error 拒绝（DB-D048）
- Snapshot manifest contract：字段契约 + aggregates（DB-D049）

## Next Authorized Step

- Berlin 审查 R1C Phase 1/1.1 → 批准后 R1C Phase 2 — Full-Scale Real-Data Staging Rehearsal
