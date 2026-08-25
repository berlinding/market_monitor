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
- Next: R2 Portfolio & Watchlist + vertical-slice MVP
- Production Monitoring：NOT ENABLED
- 自动真实交易：DISABLED（当前不执行）

## What works today

- canonical SQLite schema（core 17 表 / private 8 表，R1A v2 FROZEN）
- real A-share identity mapping（5,548 instruments，1:1 严格映射）
- real Tushare stock_basic ingestion artifact（CSV + provenance + SHA-256）
- reproducible migration runner（checksum 校验 / 事务原子 / 幂等）
- real-data staging validation（38,789 bars 全量迁移，V1–V18 + 100% row reconciliation）

## Not yet implemented

- real portfolio workflow
- production canonical daily ingestion
- event monitoring
- LLM event intelligence
- Telegram alert
- Daily Brief

## 高层 Roadmap

R0 Governance → R1 Core Data Model → R2 Portfolio & Watchlist → R3 Data Pipeline → R4 Event Engine → R5 Event Intelligence → R6 Alert → R7 Daily Briefing → R8 Historical Intelligence → R9 Quant Layer

## 项目治理入口

- `PROJECT_RULES.md` — 最高层级长期规则
- `PROJECT_STATUS.md` — 当前状态快照
- `PROJECT_PROGRESS_LOG.md` — append-only 开发日志

> 本仓库为代码仓库，不含 secrets 或私密 portfolio 数据。
