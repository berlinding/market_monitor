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
- **R1B.1 — Implementation Safety Corrections**（2026-08-22，S1–S6 修正，只写不执行）

## Current

- **R1B + R1B.1 artifacts awaiting Berlin review**
- SQL DDL：`docs/database/sql/core_schema_v1.sql`（17 表）+ `private_schema_v1.sql`（7 业务表 + schema_migrations）
- Canonical migrations：`docs/database/sql/migrations/core/C0001_initial_core_schema.sql` + `private/P0001_initial_private_schema.sql`
- 规格文档：`migration_runner_spec_v1.md`（含 S1 事务契约 §4.2.1）/ `legacy_daily_bars_migration_spec_v1.md`（含 S2 时区策略 §7.1、S4 strict mapping gate、S5 backup 语义）/ `r1b_test_plan_v1.md` / `r1b_ddl_review_v1.md`（含 R1B.1 Addendum B19–B24）
- Decision Register：DB-D001–D038（DB-D034–D038 为 R1B.1 增量）
- 无进行中的实施工作；未创建任何新数据库，未迁移数据，未执行任何 SQL
- **注意：R1A v2 已 FROZEN（2026-08-22）。R1B/R1B.1 产物待审查。R1C 未开始。**

## Existing Prototype

- **Dividend / Quality Dashboard**（港股高股息/质量筛选面板）
- 位置：`prototypes/dividend_dashboard/`（`index.html` + `chart.umd.min.js` + `data/dashboard_data.js`；2026-08-22 从根目录迁入，git mv 保留历史）
- Status: **Prototype, not integrated with canonical DB**（未接入 core.db/private.db）
- 治理记录：`docs/prototypes/dividend_dashboard_status_v1.md`；决策：DB-D015
- 本轮不扩展、不继续开发；`Test1` 测试残留已于 2026-08-22 删除（独立 cleanup）

## Next

- **Berlin reviews R1B SQL DDL and Migration Specification（含 R1B.1 Safety Corrections）**；批准后进入 R1C — Database Implementation & Legacy Migration Dry Run。
- 不自动开始 R1C。

## Not Authorized

- R1C（Database Implementation & Legacy Migration Dry Run）
- 任何数据库创建 / SQL 执行 / 数据迁移
- 修改 fetch_daily.py 生产行为 / 启用 dual-write
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

## Key Decisions（2026-08-22 R1B.1 增量，详见 DB-D034–D038）

- Migration transaction atomicity：BEGIN IMMEDIATE 进 executescript + record 同事务 parameterized INSERT + 应用层 commit；文件内无 COMMIT（DB-D034）
- Legacy fetched_at = naive local time（fetch_daily.py `datetime.now()`），严禁直接加 Z；时区 CONFIRMED 才转换，UNRESOLVED → ABORT（DB-D035）
- event_evidence 唯一性 = `UNIQUE(event_id, source_id, evidence_key)`（source-safe，DB-D036 extends DB-D032）
- Strict migration mapping gate：legacy distinct ts_code == mapped count（100%），缺失/重复/歧义/未知 exchange → ABORT（DB-D037）
- Backup 验证区分 byte-copy（Type A，要求 hash 相等）与 logical backup（Type B，integrity + row/aggregate 校验）；artifact content_hash = backup 文件自身 hash（DB-D038）

## Next Authorized Step

- Berlin 审查 R1B + R1B.1（SQL DDL & Migration Specification + Safety Corrections）→ 批准后 R1C — Database Implementation & Legacy Migration Dry Run
