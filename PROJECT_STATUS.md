# PROJECT_STATUS.md

## Current Snapshot

Current Stage: R1 — Core Data Model: In Progress (R1A 已完成)
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
- R1A — Core Domain Model & Data Contract（2026-08-17，设计冻结，未实施）

## Current

- R1A 设计完成：docs/database/ 六份文档（domain model / schema design / data dictionary / storage architecture / migration plan / schema review）
- 无进行中的实施工作；未创建任何新数据库，未迁移数据

## Next

- R1B — SQL DDL & Migration Specification（不自动开始，待 Berlin 授权）

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

- `data/market.db`：A股日线（`daily_bars` 5540 条 + `fetch_log`）—— 未改动，legacy 保留
- 最近一次抓取：2026-08-16
- canonical 设计目标：`data/runtime/core.db`（public）+ `data/private/private.db`（private），R1B 实施

## Runtime Status

- 开发阶段，无生产监控，无自动交易

## Current Blockers

无阻塞性 blocker。待 Berlin 决策的设计开放问题（不阻塞 R1B 启动）：

1. sector/industry 是否 R1 就需要（否则 R2 建 entity_classifications）
2. positions 是否多账户（R1 按单账户 + account_ref 设计）
3. watchlist 是否需要 entity 级条目（R1 已留 entity_id 可选列）
4. market_prices_daily 的 upsert 策略（R1 受控 upsert；若需严格版本化则加 price_revisions）

## Key Decisions

- 2026-08-17：建立三层信息体系（Governance / Runtime / Application Data）
- 2026-08-17：Python 负责确定性流程，LLM 负责理解与判断
- 2026-08-17：运行数据库（`*.db`）不入 Git，本地保留
- 2026-08-17：Entity / Instrument 双层身份模型正式采用；identifiers 独立成表
- 2026-08-17：core.db + private.db 物理分库；跨库引用式关联 + ATTACH 只读 join
- 2026-08-17：SQLite 为 operational DB（R1 唯一实施）；Parquet/DuckDB 延后
- 2026-08-17：positions = snapshot state；transactions = 未来 canonical ledger（Deferred）
- 2026-08-17：financial facts 采用 long-form 基础模型（Deferred）
- 2026-08-17：events 与 event_analysis 严格分离（事实 vs LLM 判断）
- 2026-08-17：ID 统一 integer surrogate + 业务唯一键；schema migration 用手写 SQL + stdlib runner

## Next Authorized Step

- R1B — SQL DDL & Migration Specification（待 Berlin 授权后执行）
