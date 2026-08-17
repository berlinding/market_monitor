# Database Schema Design v1

> Market Monitor 数据库逻辑结构设计 —— R1A 设计交付物
> 日期：2026-08-17 ｜ 状态：Design (not implemented) ｜ 配套：`core_domain_model_v1.md` / `data_dictionary_v1.md`
> 物理存储与分库见 `storage_architecture_v1.md`；迁移方案见 `daily_bars_migration_plan_v1.md`

---

## 0. 全局约定

| 项目 | 约定 |
|------|------|
| ID | 全表 `INTEGER PRIMARY KEY`（SQLite ROWID 别名），业务唯一性用显式 UNIQUE |
| Instant | TEXT UTC ISO-8601：`2026-08-17T02:30:00Z` |
| Calendar date | TEXT `YYYY-MM-DD`（无时区，日历语义） |
| Currency | ISO 4217 大写（USD/HKD/CNY/JPY） |
| Country | ISO 3166-1 alpha-2（CN/HK/US） |
| Exchange | ISO 10383 MIC（XSHG/XSHE/XHKG/XNYS/XNAS），非交易所用 `NONE` |
| Enum | 稳定小枚举用 SQL CHECK + 应用层常量；不建冗余 lookup 表 |
| JSON | 仅 flexible metadata / LLM 结构化输出 / provider payload |
| 时区 | 凡"时刻"必 UTC；事件另存 `event_timezone`（IANA） |

---

## 1. Core 表（R1 冻结设计）

### 1.1 `entities` — 经济主体（core.db, PUBLIC）

- 用途：现实经济主体的 canonical 身份（Tencent Holdings / NVIDIA / Apple…）。公司事件与 thesis 的挂载点。
- PK：`entity_id`
- UNIQUE：`(canonical_name)`
- FK：无
- Mutability：可变（名称/状态可更新，`updated_at` 记录）
- 说明：sector/industry 属 mutable classification，R1 不入表（未来 `entity_classifications`，见 Open Questions）。

### 1.2 `instruments` — 金融工具（core.db, PUBLIC）

- 用途：可交易/可报价工具的 canonical 身份（0700.HK / TCEHY / NVDA / SOXX / SPY / S&P 500 Index…）。
- PK：`instrument_id`
- FK：`entity_id` → entities（NULL：指数/FX/无发行主体）
- UNIQUE：`(instrument_type, primary_symbol, exchange_code)`
- Mutability：可变（status/名称可更新）
- 说明：`primary_symbol` 为交易所内符号（不带交易所后缀），交易所用 `exchange_code` 列；provider 标识一律进 `instrument_identifiers`。

### 1.3 `instrument_identifiers` — provider 中立标识（core.db, PUBLIC）

- 用途：provider 标识 ↔ instrument 映射；支持 ticker 变更、重用、delisted、跨 provider。
- PK：`identifier_id`
- FK：`instrument_id` → instruments
- UNIQUE：
  - `(provider, identifier_type, identifier, valid_to)` —— 同一标识的历史区间唯一（valid_to 非空部分）
  - Partial unique index：`UNIQUE(provider, identifier_type, identifier) WHERE valid_to IS NULL` —— 同一标识同时只允许一条"当前有效"映射（SQLite partial index 支持）
- Mutability：append-only（历史标识不删除；错误用 valid_to 关闭 + 新行纠正）

### 1.4 `data_sources` — 数据源（core.db, PUBLIC）

- 用途：provider 定义（Tushare / FMP / FRED / SEC / EIA…）。
- PK：`source_id`
- UNIQUE：`(source_code)`
- Mutability：可变（status/priority/notes）
- 说明：与 dataset 分离（provider ≠ 数据集）。`priority` 数值小者 canonical 优先。

### 1.5 `datasets` — 逻辑数据集（core.db, PUBLIC）

- 用途：逻辑数据集定义（CN_EQUITY_DAILY / US_EQUITY_DAILY / SEC_FILINGS / FRED_SERIES…），可跨 provider。
- PK：`dataset_id`
- FK：`primary_source_id` → data_sources（NULL = canonical 多源数据集，如 market_prices_daily 类）
- UNIQUE：`(dataset_code)`
- Mutability：可变

### 1.6 `ingest_runs` — 抓取运行审计（core.db, PUBLIC）

- 用途：回答"2026-08-17 的数据为什么没更新？"——每次抓取一条记录。
- PK：`run_id`
- FK：`dataset_id` → datasets；`source_id` → data_sources
- Mutability：append-only（运行结束后 status 从 RUNNING 更新为终态，允许）
- 索引：`(dataset_id, started_at)`

### 1.7 `data_gaps` — 数据缺口登记（core.db, PUBLIC）

- 用途：显式登记缺口（缺日期/缺标的/空响应/API 错误/部分数据），含状态与解决记录。
- PK：`gap_id`
- FK：`dataset_id` → datasets；`instrument_id` → instruments（NULL=非标的级）；`related_run_id` → ingest_runs（NULL=手工登记）
- Mutability：可变（status/resolution 更新）
- 索引：`(dataset_id, status)`

### 1.8 `market_prices_daily` — 标准化日线（core.db, PUBLIC）

- 用途：跨市场日线 canonical 存储，取代 legacy `daily_bars`。
- PK：`bar_id`
- FK：`instrument_id` → instruments；`source_id` → data_sources
- UNIQUE：`(instrument_id, trade_date, adjustment_type, source_id)`
- Mutability：**受控 upsert**（provider 重新发布可覆盖同键行，`ingested_at` 更新；原始证据存档 raw_artifacts 为 Deferred）—— 决议见 `r1a_schema_review_v1.md` Finding 10
- 索引：`(instrument_id, trade_date)`；`(trade_date)`
- 说明：volume/turnover 带显式 unit；adjustment_type 显式（RAW/FWD/BWD/NONE）；同一 instrument/date 多 provider 共存（source_id 区分），canonical 由查询层按 source priority 选择，不做 R1 内 reconciliation engine。

### 1.9 `events` — 事件事实（core.db, PUBLIC）

- 用途：统一事件事实存储（财报/并购/回购/高管变动…），**不含 LLM 判断**。
- PK：`event_id`
- FK：`entity_id` → entities（NULL=宏观/市场级）；`instrument_id` → instruments（NULL=非个股）；`source_id` → data_sources（NULL=人工）
- UNIQUE：`(fingerprint)`（去重）
- Mutability：append-only（status 可流转 NEW→CONFIRMED/SUPERSEDED/REJECTED）
- 索引：`(entity_id, event_date)`；`(event_type, event_date)`

### 1.10 `event_analysis` — LLM 分析（core.db, PUBLIC）

- 用途：模型对事件的判断，与事实严格分离；可复现（model_id/prompt_version/analysis_version）。
- PK：`analysis_id`
- FK：`event_id` → events
- UNIQUE：`(event_id, model_provider, model_id, prompt_version, analysis_version)`
- Mutability：append-only（rerun = 新 analysis_version 新行，不覆盖旧分析）
- 说明：多模型可对同一 event 并存多条；`importance_score`（1–5）与 `recommended_attention` 属 LLM 判断，只在此表。

### 1.11 `watchlists` — 自选列表（private.db, PRIVATE）

- PK：`watchlist_id`
- UNIQUE：`(name)`
- Mutability：可变

### 1.12 `watchlist_items` — 自选条目（private.db, PRIVATE）

- PK：`item_id`
- FK：`watchlist_id` → watchlists（同库）；`instrument_id`/`entity_id` 为跨库引用（core.db，无 FK 约束，应用层校验）
- UNIQUE：`(watchlist_id, instrument_id)`
- Mutability：可变（priority/reason/status 更新）

### 1.13 `positions` — 持仓快照（private.db, PRIVATE）

- PK：`position_id`
- FK：`instrument_id` 跨库引用（无 FK）；`account_id` 指向未来 accounts（Deferred，R1 不建 FK，用 `account_ref` 文本）
- UNIQUE（partial）：`(instrument_id, account_id) WHERE status='OPEN'` —— 同一账户同一标的仅一条 OPEN 快照
- Mutability：**snapshot 语义**——一行 = 某标的当前状态，同步/更新时覆盖；完整交易历史由未来 `transactions`（canonical ledger）解释，positions 届时转为 derived state（决议见 §3 与 review Finding 8）

### 1.14 `investment_theses` — 投资逻辑（private.db, PRIVATE）

- PK：`thesis_id`
- FK：`entity_id` 跨库引用（core.entities，无 FK）
- Mutability：可变（内容迭代，`updated_at`；版本历史未来由 `thesis_versions` 提供）
- 说明：挂 entity 不挂 ticker；base/bull/bear/invalidate 用 Markdown 文本；key_metrics/key_catalysts/key_risks 用 JSON 数组（机器可读）；status 结构化。

### 1.15 `schema_migrations` — 迁移记录（core.db, PUBLIC, infra）

- PK：`migration_id`（TEXT，如 `0001_identity`）
- Mutability：append-only
- 用途：轻量 schema versioning，R1B 手写 SQL + stdlib runner 应用。

---

## 2. Deferred 表（仅接口设计，R1 不实施）

| 表 | Domain | PK | 关键 FK / UNIQUE | 说明 |
|----|--------|----|------------------|------|
| `accounts` | B | account_id | UNIQUE(account_name) | 券商/账户（IBKR、券商 A） |
| `transactions` | B | tx_id | FK account_id, instrument_id；UNIQUE(tx_external_ref) | canonical ledger；BUY/SELL/DIVIDEND/FEE/CORP_ACTION |
| `thesis_versions` | B | version_id | FK thesis_id；UNIQUE(thesis_id, version_no) | thesis 快照版本 |
| `financial_reports` | D | report_id | FK entity_id；UNIQUE(entity_id, fiscal_period_key, report_type, source_id) | 报告头（fiscal period / GAAP·IFRS·non-GAAP / restatement） |
| `financial_facts` | D | fact_id | FK report_id；UNIQUE(report_id, metric_key, source_id) | long-form 事实（metric_key 受控字典 + original_metric_name） |
| `alerts` | E | alert_id | FK event_id / analysis_id；UNIQUE(alert_key) | R6 实施；channel/rule/delivered_at |
| `raw_artifacts` | F | artifact_id | FK dataset_id, source_id, run_id | 原始证据（URL/文件/hash），R1 用 source_reference 暂代 |

---

## 3. 关键架构决议（详见 storage_architecture_v1.md 与 r1a_schema_review_v1.md）

1. **positions 是 snapshot state**（当前 canonical state，直接反映 Berlin 持仓现状）；`transactions` 是未来 canonical ledger，二者共存方式：transactions 建立后，positions 由 ledger 重放或定期同步推导，成为 derived state；R1 阶段 positions 独立工作（手动/券商导入）。
2. **core.db + private.db 物理分库**：持仓/成本/账户/自选/研究逻辑与公开 schema 物理隔离；跨库用**引用式关联**（private 存 id，不存冗余 identity）+ 查询时 ATTACH 只读 join；instrument_id/entity_id 唯一真源在 core.db。
3. **Financial facts 采用 long-form 基础模型**（financial_reports 头 + financial_facts 行），不建三张 provider-specific 宽表；GAAP/IFRS/non-GAAP 并存、restatement、多 provider 全部可表达。
4. **events / event_analysis 严格分离**：确定性字段（event_type/entity/instrument/event_time/title/summary/fingerprint/source）在 events；模型判断（importance_score/thesis_impact/bullish·bearish_points/raw_output）只在 event_analysis。Event 无任何 LLM 分析也可独立存在。
5. **storage**：SQLite = operational DB（R1 唯一实施）；Parquet = 未来 bulk historical（Deferred）；DuckDB = 未来 analytical layer（Deferred）。
