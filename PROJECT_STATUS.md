# PROJECT_STATUS.md

## Current Snapshot

Current Stage: R0 — Project Governance & Architecture: Completed
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

## Current

（无进行中的阶段）

## Next

- R1 — Core Data Model（不自动开始，待 Berlin 授权）

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

- `data/market.db`：A股日线（`daily_bars` 5540 条 + `fetch_log`）
- 最近一次抓取：2026-08-16

## Runtime Status

- 开发阶段，无生产监控，无自动交易

## Current Blockers

（暂无）

## Key Decisions

- 2026-08-17：建立三层信息体系（Governance / Runtime / Application Data）
- 2026-08-17：Python 负责确定性流程，LLM 负责理解与判断
- 2026-08-17：运行数据库（`*.db`）不入 Git，本地保留

## Next Authorized Step

- R1 — Core Data Model design（待 Berlin 授权后执行）
