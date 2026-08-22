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

## Current

- **R1B artifacts awaiting Berlin review**
- SQL DDL：`docs/database/sql/core_schema_v1.sql`（17 表）+ `private_schema_v1.sql`（7 业务表 + schema_migrations）
- Canonical migrations：`docs/database/sql/migrations/core/C0001_initial_core_schema.sql` + `private/P0001_initial_private_schema.sql`
- 规格文档：`migration_runner_spec_v1.md` / `legacy_daily_bars_migration_spec_v1.md` / `r1b_test_plan_v1.md` / `r1b_ddl_review_v1.md`
- Decision Register：DB-D001–D033（DB-D025 R1A v2 frozen … DB-D033 retirement gate）
- 无进行中的实施工作；未创建任何新数据库，未迁移数据，未执行任何 SQL
- **注意：R1A v2 已 FROZEN（2026-08-22）。R1B 产物待审查。R1C 未开始。**

## Existing Prototype

- **Dividend / Quality Dashboard**（港股高股息/质量筛选面板）
- 位置：`prototypes/dividend_dashboard/`（`index.html` + `chart.umd.min.js` + `data/dashboard_data.js`；2026-08-22 从根目录迁入，git mv 保留历史）
- Status: **Prototype, not integrated with canonical DB**（未接入 core.db/private.db）
- 治理记录：`docs/prototypes/dividend_dashboard_status_v1.md`；决策：DB-D015
- 本轮不扩展、不继续开发；`Test1` 测试残留已于 2026-08-22 删除（独立 cleanup）

## Next

- **Berlin reviews R1B SQL DDL and Migration Specification**；批准后进入 R1C — Database Implementation & Legacy Migration Dry Run。
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

无阻塞性 blocker。待 Berlin 决策的开放问题（不阻塞审查）：

1. sector/industry 是否 R1 就需要（否则 R2 建 entity_classifications）
2. financial_reports/financial_facts 是否随 FMP/SEC 接入提前升级（当前 Deferred）
3. market_prices_daily upsert 策略：受控 upsert vs 严格版本化（raw_artifacts 已 Core，可支撑 price_revisions）
4. event_evidence 同源多版本证据是否需要 version 列（R1B 决策点）

## Key Decisions（2026-08-22 R1B 增量，详见 DB-D025–D033）

- R1A v2 FROZEN（Berlin 2026-08-22 批准）（DB-D025）
- event_entities/event_instruments = CONTROLLED MUTABLE（DELETE+INSERT，无 status/valid_to）（DB-D026）
- 所有 timestamp 由 application 层写 UTC ISO-8601，不用 CURRENT_TIMESTAMP（DB-D027）
- JSON 校验在 application 层，不硬依赖 JSON1（DB-D028）
- Migration files = canonical executable source；consolidated schema = review snapshot（DB-D029）
- core/private 独立 migration history（C0001… / P0001…）（DB-D030）
- Market price CONTROLLED UPSERT，不同 source 不互覆（DB-D031）
- event_evidence 用 evidence_key（方案 B）业务唯一（DB-D032）
- Legacy dual-write：≥20 trading days 且 ≥30 calendar days 取较晚者；退休门 6 条件 + Berlin 批准（DB-D033）

## Next Authorized Step

- Berlin 审查 R1B SQL DDL & Migration Specification → 批准后 R1C — Database Implementation & Legacy Migration Dry Run
