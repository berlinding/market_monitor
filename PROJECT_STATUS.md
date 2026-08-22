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

## Current

- **R1A v2 Freeze Candidate 待 Berlin 审查**：docs/database/ 下 7 份文档
  - core_domain_model_v2_freeze_candidate.md
  - database_schema_design_v2_freeze_candidate.md
  - data_dictionary_v2_freeze_candidate.md
  - storage_architecture_v2_freeze_candidate.md
  - daily_bars_migration_plan_v2_freeze_candidate.md
  - r1a1_schema_review_v2.md（Blocking findings = 0）
  - database_design_decisions_v1.md（DB-D001–D015）
- 无进行中的实施工作；未创建任何新数据库，未迁移数据

## Existing Prototype

- **Dividend / Quality Dashboard**（港股高股息/质量筛选面板）
- 位置：`prototypes/dividend_dashboard/`（`index.html` + `chart.umd.min.js` + `data/dashboard_data.js`；2026-08-22 从根目录迁入，git mv 保留历史）
- Status: **Prototype, not integrated with canonical DB**（未接入 core.db/private.db）
- 治理记录：`docs/prototypes/dividend_dashboard_status_v1.md`；决策：DB-D015
- 本轮不扩展、不继续开发；`Test1` 测试残留已于 2026-08-22 删除（独立 cleanup）

## Next

- **Berlin reviews the R1A v2 Freeze Candidate**。若批准：状态更新为 Frozen，然后授权 R1B — SQL DDL & Migration Specification。
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

- `data/market.db`：A股日线（`daily_bars` 5540 条 + `fetch_log`）—— 未改动，legacy 保留（2026-08-22 复核）
- 最近一次抓取：2026-08-16
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

## Key Decisions（2026-08-22 R1A.1 增量）

- 跨库引用一律使用 `*_uid`（UUIDv4）；INTEGER PK 仅作单库 surrogate（DB-D003）
- Entity 标识（LEI/SEC_CIK）与 Instrument 标识（ticker/ISIN/FIGI/CUSIP）严格分属（DB-D002）
- accounts 提升 Core；positions 账户级 OPEN 唯一（DB-D006/D007）
- generic analysis（core）与 private thesis analysis（private）分离；alerts 移入 private（DB-D008/D011）
- dataset_sources 定义 per-dataset 源优先级；data_sources.priority 弃用（DB-D009）
- raw_artifacts 提升 Core；行情带 ingest_run_id 血缘（DB-D012）
- legacy 双完整性定义：normalized completeness + raw provenance completeness（B14）

## Next Authorized Step

- Berlin 审查 R1A v2 Freeze Candidate → 批准后 Frozen → 授权 R1B
