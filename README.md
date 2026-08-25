# Market Monitor

Berlin 的私人市场监控与投研基础设施。当前处于 **development** 阶段。

## 是什么

- 长期保存市场数据
- 管理持仓与自选
- 监控财报与重大公司事件
- 识别投资逻辑相关的重要变化
- Telegram Alerts + Daily / Weekly Brief
- 长期可检索的市场事件数据库
- 后期支持历史事件分析、回测与量化研究

## 当前状态

- R0 Governance — COMPLETE
- R1 Core Data Model — COMPLETE（canonical schema + migration runner + 真实数据 staging rehearsal 验证通过）
- R2 Minimal Portfolio & Watchlist — FOUNDATION COMPLETE（production canonical identity DB + private portfolio DB 已初始化；能力就绪，真实持仓数据等待 Berlin 录入）
- Next: R3 Minimal Canonical Data Pipeline + vertical-slice continuation
- Production Monitoring：NOT ENABLED
- 自动真实交易：DISABLED（当前不执行）

## What works today

- canonical SQLite schema（core 17 表 / private 8 表，R1A v2 FROZEN）
- real A-share identity mapping（5,548 instruments，1:1 严格映射）
- real Tushare stock_basic ingestion artifact（CSV + provenance + SHA-256）
- reproducible migration runner（checksum 校验 / 事务原子 / 幂等）
- real-data staging validation（38,789 bars 全量迁移，V1–V18 + 100% row reconciliation）
- **production canonical identity DB initialized**（data/runtime/core.db，5,548 instruments / 38,789 bars）
- **private portfolio DB initialized**（data/private/private.db，P0001 schema）
- **minimal account/position/watchlist service**（scripts/portfolio/ + CLI）
- **identifier resolution**（ts_code / bare ticker / uid → stable instrument_uid / entity_uid）
- **monitoring universe query**（OPEN positions ∪ watchlist targets，POSITION/WATCHLIST/BOTH）

## Not yet implemented

- automatic broker sync
- canonical daily production ingestion
- real portfolio data（等待 Berlin 录入）
- event monitoring
- intelligence
- Telegram
- Daily Brief

## 高层 Roadmap

R0 Governance → R1 Core Data Model → R2 Portfolio & Watchlist → R3 Data Pipeline → R4 Event Engine → R5 Event Intelligence → R6 Alert → R7 Daily Briefing → R8 Historical Intelligence → R9 Quant Layer

## 项目治理入口

- `PROJECT_RULES.md` — 最高层级长期规则
- `PROJECT_STATUS.md` — 当前状态快照
- `PROJECT_PROGRESS_LOG.md` — append-only 开发日志

> 本仓库为代码仓库，不含 secrets 或私密 portfolio 数据。
