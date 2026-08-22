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

## Current

- **R1A v2 Freeze Candidate —— Freeze Readiness: READY FOR BERLIN APPROVAL**
- docs/database/ 下 7 份文档：
  - core_domain_model_v2_freeze_candidate.md
  - database_schema_design_v2_freeze_candidate.md
  - data_dictionary_v2_freeze_candidate.md
  - storage_architecture_v2_freeze_candidate.md
  - daily_bars_migration_plan_v2_freeze_candidate.md
  - r1a1_schema_review_v2.md（R1A.2 Addendum：Blocking findings = 0）
  - database_design_decisions_v1.md（DB-D001–D024）
- 无进行中的实施工作；未创建任何新数据库，未迁移数据
- **注意：仍是 FREEZE CANDIDATE，不是 FROZEN。**

## Existing Prototype

- **Dividend / Quality Dashboard**（港股高股息/质量筛选面板）
- 位置：`prototypes/dividend_dashboard/`（`index.html` + `chart.umd.min.js` + `data/dashboard_data.js`；2026-08-22 从根目录迁入，git mv 保留历史）
- Status: **Prototype, not integrated with canonical DB**（未接入 core.db/private.db）
- 治理记录：`docs/prototypes/dividend_dashboard_status_v1.md`；决策：DB-D015
- 本轮不扩展、不继续开发；`Test1` 测试残留已于 2026-08-22 删除（独立 cleanup）

## Next

- **Berlin final review and freeze approval**：审查 R1A v2 Freeze Candidate（Freeze Readiness: READY FOR BERLIN APPROVAL）。若批准：标记 R1A v2 FROZEN，然后授权 R1B — SQL DDL & Migration Specification。
- 不自动开始 R1B。

## Not Authorized

- R1B（SQL DDL & Migration）
- 任何数据库实施 / 数据迁移
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

## Key Decisions（2026-08-22 R1A.2 增量，详见 DB-D017–D024）

- Instrument symbol is not identity：去 UNIQUE，ticker 历史归 instrument_identifiers（F1 / DB-D017）
- Dataset source 单真源：datasets.primary_source_id 删除（F2 / DB-D018）
- dataset_sources 增加 priority_rank 顺序（F4 / DB-D019）
- raw_artifacts hash 非唯一，run 内去重（F5 / DB-D020）
- event_evidence source-level 唯一性（F6 / DB-D021）
- events.source_id → discovered_by_source_id（F7 / DB-D022）
- account_type 规范化（F8A / DB-D023）
- event_analysis.analysis_uid + alerts.generic_analysis_uid（F8B / DB-D024）

## Next Authorized Step

- Berlin 最终审查 R1A v2 Freeze Candidate → 批准后标记 FROZEN → 授权 R1B
