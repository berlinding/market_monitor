# Data Dictionary v1

> Market Monitor 字段级数据字典 —— R1A 设计交付物
> 日期：2026-08-17 ｜ 状态：Design (not implemented)
> type concept 为逻辑类型（R1B 映射到 SQLite 具体 SQL type）；tables 简称：`C`=core.db / `P`=private.db

---

## 0. 通用字段（重复出现，不再逐表解释）

| field | type concept | nullable | key | description | example | source/provenance | privacy | mutability |
|-------|--------------|----------|-----|-------------|---------|-------------------|---------|------------|
| created_at | datetime(UTC) | NO | | 行创建时刻 | `2026-08-17T02:30:00Z` | system | public/private 随表 | immutable |
| updated_at | datetime(UTC) | NO | | 行最后更新时刻 | `2026-08-17T02:30:00Z` | system | 随表 | mutable |
| status | enum(text) | NO | | 行状态（各表枚举不同） | `ACTIVE` | system | 随表 | mutable |

---

## 1. entities（C, PUBLIC）

| field | type concept | nullable | key | description | example | source/provenance | privacy | mutability |
|-------|--------------|----------|-----|-------------|---------|-------------------|---------|------------|
| entity_id | integer | NO | PK | 经济主体唯一 ID | `1` | system | public | immutable |
| canonical_name | text | NO | UNIQUE | 当前权威名称 | `Tencent Holdings Ltd` | provider/manual | public | mutable（改名时更新，历史名未来入 entity_names） |
| entity_type | enum(text) | NO | CHECK | 主体类型 | `COMPANY` | manual | public | mutable（罕见） |
| country_code | text | YES | | 主要所在地 ISO 3166-1 alpha-2 | `CN` | provider/manual | public | mutable |
| status | enum(text) | NO | CHECK | ACTIVE/INACTIVE/MERGED/DELISTED | `ACTIVE` | manual | public | mutable |
| created_at / updated_at | datetime(UTC) | NO | | 见通用 | | | | |

CHECK: `entity_type IN ('COMPANY','GOVERNMENT','INDEX_PROVIDER','ETF_ISSUER','FUND_MANAGER','SUPRA_NATIONAL','OTHER')`

> 设计判断：`canonical_name`/`entity_type`/`country_code` 是 canonical；sector/industry 是 mutable classification，R1 不入表。

---

## 2. instruments（C, PUBLIC）

| field | type concept | nullable | key | description | example | source/provenance | privacy | mutability |
|-------|--------------|----------|-----|-------------|---------|-------------------|---------|------------|
| instrument_id | integer | NO | PK | 金融工具唯一 ID | `1` | system | public | immutable |
| entity_id | integer | YES | FK→entities | 发行主体（指数/FX 可空） | `1` | manual | public | mutable（映射修正） |
| instrument_type | enum(text) | NO | CHECK | EQUITY/ADR/ETF/INDEX/FX/FUTURE/OPTION/BOND/COMMODITY/CRYPTO | `EQUITY` | manual | public | immutable（实质上是身份属性） |
| primary_symbol | text | NO | UNIQUE(复合) | 主交易所内符号（不带后缀） | `0700` | manual | public | mutable（极罕见） |
| exchange_code | text | NO | UNIQUE(复合) | ISO 10383 MIC；非交易所用 `NONE` | `XHKG` | manual | public | mutable（极罕见） |
| currency_code | text | NO | | 报价币种 ISO 4217 | `HKD` | manual | public | immutable |
| country_code | text | YES | | 市场国家 ISO 3166-1 alpha-2 | `HK` | manual | public | mutable |
| status | enum(text) | NO | CHECK | ACTIVE/SUSPENDED/DELISTED/PENDING | `ACTIVE` | manual/pipeline | public | mutable |
| listing_date | date | YES | | 上市日 | `2004-06-16` | provider | public | immutable |
| delisting_date | date | YES | | 退市日（status=DELISTED 时） | `NULL` | provider | public | mutable |
| created_at / updated_at | datetime(UTC) | NO | | 见通用 | | | | |

UNIQUE: `(instrument_type, primary_symbol, exchange_code)`

> provider 标识（ts_code/fmp_symbol/isin…）一律不进本表，见 instrument_identifiers。

---

## 3. instrument_identifiers（C, PUBLIC）

| field | type concept | nullable | key | description | example | source/provenance | privacy | mutability |
|-------|--------------|----------|-----|-------------|---------|-------------------|---------|------------|
| identifier_id | integer | NO | PK | 标识记录 ID | `1` | system | public | immutable |
| instrument_id | integer | NO | FK→instruments | 指向的金融工具 | `1` | pipeline/manual | public | mutable（映射纠错时） |
| provider | text | NO | UNIQUE(复合) | 标识命名空间：TUSHARE/FMP/YAHOO/IBKR/STANDARD… | `TUSHARE` | pipeline | public | immutable |
| identifier_type | enum(text) | NO | CHECK | TICKER/EXCHANGE_SYMBOL/ISIN/CUSIP/SEDOL/FIGI/LEI/CURRENCY_PAIR | `TICKER` | pipeline | public | immutable |
| identifier | text | NO | UNIQUE(复合) | 标识值 | `600519.SH` | pipeline | public | immutable |
| valid_from | date | NO | | 该标识生效日 | `2004-06-16` | pipeline/manual | public | mutable |
| valid_to | date | YES | | 失效日（NULL=当前有效） | `NULL` | pipeline/manual | public | mutable |
| is_primary | boolean | NO | | 该 provider 内首选标识 | `1` | manual | public | mutable |
| created_at | datetime(UTC) | NO | | 见通用 | | | | |

CHECK: `identifier_type IN ('TICKER','EXCHANGE_SYMBOL','ISIN','CUSIP','SEDOL','FIGI','LEI','CURRENCY_PAIR')`
UNIQUE: `(provider, identifier_type, identifier, valid_to)`；partial `UNIQUE(provider, identifier_type, identifier) WHERE valid_to IS NULL`

> provider 语义：`STANDARD` 用于 ISIN/CUSIP/LEI 等非 provider 专属标准标识。`TICKER`=provider 的报价符号（如 tushare `0700.HK`、fmp `TCEHY`）；`EXCHANGE_SYMBOL`=交易所原始符号（如 `0700`）。

---

## 4. data_sources（C, PUBLIC）

| field | type concept | nullable | key | description | example | source/provenance | privacy | mutability |
|-------|--------------|----------|-----|-------------|---------|-------------------|---------|------------|
| source_id | integer | NO | PK | 数据源 ID | `1` | system | public | immutable |
| source_code | text | NO | UNIQUE | 稳定代码 | `TUSHARE` | manual | public | immutable |
| source_name | text | NO | | 全名 | `Tushare Pro` | manual | public | mutable |
| source_type | enum(text) | NO | CHECK | MARKET_DATA/FUNDAMENTALS/MACRO/FILINGS/NEWS/MANUAL | `MARKET_DATA` | manual | public | mutable |
| priority | integer | NO | | canonical 优先级（小=优先） | `10` | manual | public | mutable |
| base_url | text | YES | | API 基址 | `http://api.tushare.pro` | manual | public | mutable |
| status | enum(text) | NO | CHECK | ACTIVE/DEGRADED/SUSPENDED | `ACTIVE` | manual/pipeline | public | mutable |
| notes | text | YES | | 备注（限额、认证方式等） | `daily 接口 5000 次/天` | manual | public | mutable |

---

## 5. datasets（C, PUBLIC）

| field | type concept | nullable | key | description | example | source/provenance | privacy | mutability |
|-------|--------------|----------|-----|-------------|---------|-------------------|---------|------------|
| dataset_id | integer | NO | PK | 数据集 ID | `1` | system | public | immutable |
| dataset_code | text | NO | UNIQUE | 稳定代码 | `CN_EQUITY_DAILY` | manual | public | immutable |
| dataset_name | text | NO | | 名称 | `A股日线` | manual | public | mutable |
| dataset_type | enum(text) | NO | CHECK | PRICE_DAILY/PRICE_MINUTE/FINANCIAL/MACRO/FILINGS/EVENTS | `PRICE_DAILY` | manual | public | mutable |
| granularity | enum(text) | NO | | DAILY/MINUTE/QUARTERLY/ANNUAL/EVENT | `DAILY` | manual | public | mutable |
| primary_source_id | integer | YES | FK→data_sources | 主源（NULL=canonical 多源） | `1` | manual | public | mutable |
| target_table | text | YES | | 写入的 canonical 表 | `market_prices_daily` | manual | public | mutable |
| write_mode | enum(text) | NO | CHECK | APPEND/UPSERT/SNAPSHOT | `UPSERT` | manual | public | mutable |
| status | enum(text) | NO | CHECK | ACTIVE/DEGRADED/SUSPENDED | `ACTIVE` | manual | public | mutable |
| notes | text | YES | | 备注（范围、口径） | `全 A 股日线，RAW` | manual | public | mutable |

---

## 6. ingest_runs（C, PUBLIC）

| field | type concept | nullable | key | description | example | source/provenance | privacy | mutability |
|-------|--------------|----------|-----|-------------|---------|-------------------|---------|------------|
| run_id | integer | NO | PK | 运行 ID | `1` | system | public | immutable |
| dataset_id | integer | NO | FK→datasets | 数据集 | `1` | pipeline | public | immutable |
| source_id | integer | NO | FK→data_sources | 实际数据源 | `1` | pipeline | public | immutable |
| trigger_type | enum(text) | NO | CHECK | SCHEDULED/MANUAL/BACKFILL | `SCHEDULED` | pipeline | public | immutable |
| started_at | datetime(UTC) | NO | | 开始时刻 | `2026-08-17T02:00:00Z` | pipeline | public | immutable |
| finished_at | datetime(UTC) | YES | | 结束时刻 | `2026-08-17T02:03:12Z` | pipeline | public | mutable（终态写入） |
| status | enum(text) | NO | CHECK | RUNNING/SUCCESS/PARTIAL/FAILED/SKIPPED | `SUCCESS` | pipeline | public | mutable |
| requested_count | integer | NO | | 请求数 | `5000` | pipeline | public | immutable |
| received_count | integer | NO | | 收到数 | `4982` | pipeline | public | immutable |
| inserted_count | integer | NO | | 新插入行数 | `0` | pipeline | public | immutable |
| updated_count | integer | NO | | 更新行数 | `4982` | pipeline | public | immutable |
| rejected_count | integer | NO | | 拒绝行数 | `18` | pipeline | public | immutable |
| error_code | text | YES | | 错误码 | `HTTP_429` | pipeline | public | mutable |
| error_message | text | YES | | 错误信息 | `rate limit` | pipeline | public | mutable |
| run_metadata | json | YES | | 运行元数据（参数/交易日） | `{"trade_date":"2026-08-17"}` | pipeline | public | immutable |

---

## 7. data_gaps（C, PUBLIC）

| field | type concept | nullable | key | description | example | source/provenance | privacy | mutability |
|-------|--------------|----------|-----|-------------|---------|-------------------|---------|------------|
| gap_id | integer | NO | PK | 缺口 ID | `1` | system | public | immutable |
| dataset_id | integer | NO | FK→datasets | 所属数据集 | `1` | pipeline/manual | public | immutable |
| instrument_id | integer | YES | FK→instruments | 缺失标的（NULL=非标的级） | `NULL` | pipeline/manual | public | immutable |
| date_from / date_to | date | YES | | 缺失日期/区间 | `2026-08-17` | pipeline/manual | public | mutable |
| gap_type | enum(text) | NO | CHECK | MISSING_DATE/MISSING_INSTRUMENT/EMPTY_RESPONSE/API_ERROR/ZERO_ROWS/PARTIAL/VALUE_CONFLICT | `API_ERROR` | pipeline | public | immutable |
| related_run_id | integer | YES | FK→ingest_runs | 关联运行 | `1` | pipeline | public | immutable |
| detected_at | datetime(UTC) | NO | | 发现时刻 | `2026-08-17T02:03:12Z` | pipeline | public | immutable |
| status | enum(text) | NO | CHECK | OPEN/RESOLVED/ACCEPTED | `OPEN` | pipeline/manual | public | mutable |
| resolution | text | YES | | 解决说明 | `2026-08-18 补抓成功` | manual/pipeline | public | mutable |
| resolved_at | datetime(UTC) | YES | | 解决时刻 | `2026-08-18T02:01:00Z` | pipeline | public | mutable |

---

## 8. market_prices_daily（C, PUBLIC）

| field | type concept | nullable | key | description | example | source/provenance | privacy | mutability |
|-------|--------------|----------|-----|-------------|---------|-------------------|---------|------------|
| bar_id | integer | NO | PK | 行情行 ID | `1` | system | public | immutable |
| instrument_id | integer | NO | FK→instruments | 金融工具 | `1` | pipeline | public | immutable |
| trade_date | date | NO | UNIQUE(复合) | 交易日（市场日历） | `2026-08-17` | pipeline | public | immutable |
| open / high / low / close | numeric | YES | | OHLC（close 通常非空） | `310.50` | provider | public | mutable（受控 upsert） |
| volume | numeric | YES | | 成交量（raw 数值） | `12345` | provider | public | mutable |
| volume_unit | enum(text) | NO | CHECK | SHARES/LOTS/CONTRACTS/UNITS/COINS/NONE | `LOTS` | 数据集约定 | public | immutable |
| turnover | numeric | YES | | 成交额（raw 数值） | `3832.5` | provider | public | mutable |
| turnover_unit | text | YES | | 成交额单位（ISO 4217 或 THOUSAND_CNY 等） | `THOUSAND_CNY` | 数据集约定 | public | immutable |
| currency_code | text | NO | | 报价币种 ISO 4217 | `CNY` | provider/约定 | public | immutable |
| adjustment_type | enum(text) | NO | CHECK | RAW/FWD/BWD/NONE | `RAW` | 数据集约定 | public | immutable |
| source_id | integer | NO | FK→data_sources | 数据源 | `1` | pipeline | public | immutable |
| ingested_at | datetime(UTC) | NO | | 入库时刻 | `2026-08-17T02:03:12Z` | pipeline | public | mutable（覆盖时更新） |

UNIQUE: `(instrument_id, trade_date, adjustment_type, source_id)`
CHECK: `volume_unit IN ('SHARES','LOTS','CONTRACTS','UNITS','COINS','NONE')`；`adjustment_type IN ('RAW','FWD','BWD','NONE')`；`low <= high`（可加）
索引：`(instrument_id, trade_date)`；`(trade_date)`

> ⚠️ Tushare 单位：`vol`=手（LOTS），`amount`=千元（THOUSAND_CNY）。canonical 存 provider raw 值 + 显式 unit，不做隐式换算。多 provider 共存：同 (instrument,date,adj) 不同 source 各占一行；canonical 选择在查询层按 `data_sources.priority`。

---

## 9. events（C, PUBLIC）

| field | type concept | nullable | key | description | example | source/provenance | privacy | mutability |
|-------|--------------|----------|-----|-------------|---------|-------------------|---------|------------|
| event_id | integer | NO | PK | 事件 ID | `1` | system | public | immutable |
| event_type | enum(text) | NO | CHECK | EARNINGS/GUIDANCE/M&A/DIVESTITURE/BUYBACK/DIVIDEND/EXECUTIVE_CHANGE/REGULATORY/LAWSUIT/PRODUCT/INDEX_CHANGE/MACRO/OTHER | `EARNINGS` | pipeline/manual | public | immutable |
| entity_id | integer | YES | FK→entities | 主体（宏观事件可空） | `1` | pipeline/manual | public | immutable |
| instrument_id | integer | YES | FK→instruments | 相关工具（可空） | `1` | pipeline/manual | public | immutable |
| event_date | date | YES | | 事件发生日（市场日历） | `2026-08-17` | pipeline/manual | public | immutable |
| event_time | datetime(UTC) | YES | | 事件发生时刻（已知时） | `2026-08-17T01:30:00Z` | pipeline/manual | public | immutable |
| event_timezone | text | YES | | 事件原始时区 IANA | `Asia/Shanghai` | pipeline/manual | public | immutable |
| detected_at | datetime(UTC) | NO | | 检测到时刻 | `2026-08-17T02:05:00Z` | pipeline | public | immutable |
| title | text | NO | | 事件标题 | `Tencent 发布 2026Q2 财报` | provider/manual | public | immutable |
| summary | text | YES | | 事实摘要（非 LLM 判断） | `营收同比 +8%…` | provider/manual | public | mutable |
| source_id | integer | YES | FK→data_sources | 来源 | `1` | pipeline/manual | public | immutable |
| source_reference | text | YES | | 原始引用（URL/文号） | `https://…/announcement.pdf` | provider | public | immutable |
| fingerprint | text | NO | UNIQUE | 去重指纹（SHA-256 规范化事实键） | `a3f9…` | pipeline | public | immutable |
| status | enum(text) | NO | CHECK | NEW/CONFIRMED/SUPERSEDED/REJECTED | `CONFIRMED` | pipeline/manual | public | mutable |
| created_at / updated_at | datetime(UTC) | NO | | 见通用 | | | | |

> **不含**：importance、LLM summary、thesis impact —— 全部在 event_analysis。raw event fact 可独立存在。

---

## 10. event_analysis（C, PUBLIC）

| field | type concept | nullable | key | description | example | source/provenance | privacy | mutability |
|-------|--------------|----------|-----|-------------|---------|-------------------|---------|------------|
| analysis_id | integer | NO | PK | 分析 ID | `1` | system | public | immutable |
| event_id | integer | NO | FK→events | 被分析事件 | `1` | pipeline | public | immutable |
| model_provider | text | NO | UNIQUE(复合) | 模型供应商 | `deepseek` | pipeline | public | immutable |
| model_id | text | NO | UNIQUE(复合) | 模型标识 | `deepseek/deepseek-v4-pro` | pipeline | public | immutable |
| prompt_version | text | NO | UNIQUE(复合) | prompt 版本 | `prompts/event_analysis_v3` | pipeline | public | immutable |
| analysis_version | integer | NO | UNIQUE(复合) | 同一事件同模型 rerun 版本 | `1` | pipeline | public | immutable |
| importance_score | integer | YES | CHECK 1..5 | 重要性评分（LLM） | `4` | LLM | public | immutable |
| thesis_impact | json | YES | | 对 thesis 影响映射 | `{"3":"HIGH"}` | LLM | public | immutable |
| summary | text | YES | | 分析摘要 | `财报超预期…` | LLM | public | immutable |
| key_changes | json | YES | | 关键变化数组 | `["capex 上调"]` | LLM | public | immutable |
| bullish_points | json | YES | | 看多要点数组 | `["现金流强"]` | LLM | public | immutable |
| bearish_points | json | YES | | 看空要点数组 | `["广告承压"]` | LLM | public | immutable |
| recommended_attention | enum(text) | YES | CHECK | ALERT/WATCH/IGNORE | `ALERT` | LLM | public | immutable |
| raw_output | json | YES | | 模型原始结构化输出（证据） | `{...}` | LLM | public | immutable |
| created_at | datetime(UTC) | NO | | 见通用 | | | | |

UNIQUE: `(event_id, model_provider, model_id, prompt_version, analysis_version)`

> JSON vs relational：importance/attention 列化（查询/排序）；bullish/bearish/key_changes 用 JSON 数组（可变长、机器可读）；raw_output 保留原始证据。rerun 不覆盖旧行（append-only）。

---

## 11. watchlists（P, PRIVATE）

| field | type concept | nullable | key | description | example | source/provenance | privacy | mutability |
|-------|--------------|----------|-----|-------------|---------|-------------------|---------|------------|
| watchlist_id | integer | NO | PK | 列表 ID | `1` | system | private | immutable |
| name | text | NO | UNIQUE | 列表名 | `AI 核心` | user | private | mutable |
| description | text | YES | | 说明 | `AI capex 主线` | user | private | mutable |
| status | enum(text) | NO | CHECK | ACTIVE/ARCHIVED | `ACTIVE` | user | private | mutable |
| created_at / updated_at | datetime(UTC) | NO | | 见通用 | | | | |

---

## 12. watchlist_items（P, PRIVATE）

| field | type concept | nullable | key | description | example | source/provenance | privacy | mutability |
|-------|--------------|----------|-----|-------------|---------|-------------------|---------|------------|
| item_id | integer | NO | PK | 条目 ID | `1` | system | private | immutable |
| watchlist_id | integer | NO | FK→watchlists | 所属列表 | `1` | user | private | immutable |
| instrument_id | integer | NO | （跨库引用） | 工具（core.instruments，无 FK） | `3` | user | private | immutable |
| entity_id | integer | YES | （跨库引用） | 主体（可选，公司级关注） | `1` | user | private | immutable |
| priority | enum(text) | NO | CHECK | CRITICAL/HIGH/MEDIUM/LOW | `CRITICAL` | user | private | mutable |
| reason | text | YES | | 为什么关注 | `AI capex leading indicator` | user | private | mutable |
| tags | json | YES | | 标签数组 | `["AI","semis"]` | user | private | mutable |
| status | enum(text) | NO | CHECK | ACTIVE/INACTIVE | `ACTIVE` | user | private | mutable |
| added_at | datetime(UTC) | NO | | 添加时刻 | `2026-08-17T03:00:00Z` | user | private | immutable |
| updated_at | datetime(UTC) | NO | | 见通用 | | | | |

UNIQUE: `(watchlist_id, instrument_id)`

---

## 13. positions（P, PRIVATE）

| field | type concept | nullable | key | description | example | source/provenance | privacy | mutability |
|-------|--------------|----------|-----|-------------|---------|-------------------|---------|------------|
| position_id | integer | NO | PK | 持仓 ID | `1` | system | private | immutable |
| instrument_id | integer | NO | （跨库引用） | 工具（core.instruments） | `3` | user/import | private | immutable |
| account_id | integer | YES | （未来 FK→accounts） | 账户（accounts Deferred） | `NULL` | user | private | mutable |
| account_ref | text | YES | | 账户人类可读标识 | `IBKR-U12345` | user | private | mutable |
| quantity | numeric | NO | | 数量（支持小数股/合约） | `100.0` | user/import | private | mutable |
| avg_cost | numeric | YES | | 平均成本 | `310.50` | user/import | private | mutable |
| currency_code | text | NO | | 成本币种 ISO 4217 | `HKD` | user/import | private | mutable |
| as_of_date | date | NO | | 快照有效日期 | `2026-08-17` | user/import | private | mutable |
| status | enum(text) | NO | CHECK | OPEN/CLOSED | `OPEN` | user/import | private | mutable |
| source | enum(text) | NO | CHECK | MANUAL/BROKER_IMPORT/DERIVED | `MANUAL` | user/import | private | immutable |
| notes | text | YES | | 备注 | `核心仓位` | user | private | mutable |
| updated_at | datetime(UTC) | NO | | 见通用 | | | | |

UNIQUE(partial): `(instrument_id, account_id) WHERE status='OPEN'`

> **语义：snapshot state**。一行 = 当前状态，同步时 upsert 覆盖；历史与交易明细由未来 `transactions` 解释，届时 positions 转为 derived。

---

## 14. investment_theses（P, PRIVATE）

| field | type concept | nullable | key | description | example | source/provenance | privacy | mutability |
|-------|--------------|----------|-----|-------------|---------|-------------------|---------|------------|
| thesis_id | integer | NO | PK | 逻辑 ID | `1` | system | private | immutable |
| entity_id | integer | NO | （跨库引用） | 主体（core.entities，不挂 ticker） | `1` | user | private | immutable |
| status | enum(text) | NO | CHECK | IDEA/ACTIVE/WATCH/INVALIDATED/ARCHIVED | `ACTIVE` | user | private | mutable |
| thesis_name | text | YES | | 短标签 | `腾讯 AI 变现` | user | private | mutable |
| base_case | text(Markdown) | NO | | 基准情形 | `游戏+广告+AI 云…` | user | private | mutable |
| bull_case | text(Markdown) | YES | | 乐观情形 | `AI 广告货币化超预期…` | user | private | mutable |
| bear_case | text(Markdown) | YES | | 悲观情形 | `监管+资本开支失控…` | user | private | mutable |
| key_metrics | json | YES | | 跟踪指标键数组 | `["revenue","capex","fcf"]` | user | private | mutable |
| key_catalysts | json | YES | | 催化剂数组 | `["2026Q3 财报"]` | user | private | mutable |
| key_risks | json | YES | | 风险数组 | `["监管处罚"]` | user | private | mutable |
| invalidate_conditions | text(Markdown) | YES | | 证伪条件 | `FCF 连续两季为负…` | user | private | mutable |
| created_at / updated_at | datetime(UTC) | NO | | 见通用 | | | | |

> 结构化 vs 文本：status/entity_id 结构化；base/bull/bear/invalidate 用 Markdown（叙述型）；key_metrics/catalysts/risks 用 JSON 数组（机器可读、可勾选）。版本系统未来由 `thesis_versions` 提供。

---

## 15. schema_migrations（C, PUBLIC, infra）

| field | type concept | nullable | key | description | example | source/provenance | privacy | mutability |
|-------|--------------|----------|-----|-------------|---------|-------------------|---------|------------|
| migration_id | text | NO | PK | 迁移编号 | `0001_identity` | migration runner | public | immutable |
| applied_at | datetime(UTC) | NO | | 应用时刻 | `2026-08-17T04:00:00Z` | migration runner | public | immutable |
| description | text | YES | | 描述 | `create identity tables` | migration runner | public | immutable |
| checksum | text | YES | | 文件校验和（防篡改/防重放） | `sha256:…` | migration runner | public | immutable |

---

## 16. Deferred 表字段速览（仅接口设计）

**accounts（P, PRIVATE）**：account_id PK, account_name UNIQUE, broker, account_type (CASH/MARGIN/IBKR…), currency_code, status, created_at, updated_at

**transactions（P, PRIVATE）**：tx_id PK, account_id FK, instrument_id 跨库引用, tx_type (BUY/SELL/DIVIDEND/FEE/CORP_ACTION/TRANSFER), quantity, price, amount, fee, currency_code, tx_time(datetime UTC), status, tx_external_ref UNIQUE, source, created_at

**thesis_versions（P, PRIVATE）**：version_id PK, thesis_id FK, version_no UNIQUE(thesis_id,version_no), content_json（全量快照）, change_summary, created_by, created_at

**financial_reports（C, PUBLIC）**：report_id PK, entity_id FK, fiscal_period_key (如 `2026Q2`), fiscal_year, fiscal_period, period_end(date), report_date(date), report_type (GAAP/IFRS/NON_GAAP), currency_code, status (ORIGINAL/RESTATED/SUPERSEDED), source_id FK, ingested_at —— UNIQUE(entity_id, fiscal_period_key, report_type, source_id)

**financial_facts（C, PUBLIC）**：fact_id PK, report_id FK, metric_key（受控字典：revenue/capex/operating_cash_flow/free_cash_flow/advertising_revenue…）, original_metric_name, value numeric, unit, value_type (MONEY/RATIO/PERCENT/COUNT/PER_SHARE), source_id FK, ingested_at —— UNIQUE(report_id, metric_key, source_id)

**alerts（C, PUBLIC）**：alert_id PK, alert_key UNIQUE, event_id FK / analysis_id FK, channel, rule, priority, content, delivered_at, status (PENDING/SENT/FAILED/SUPPRESSED), created_at

**raw_artifacts（C, PUBLIC）**：artifact_id PK, dataset_id FK, source_id FK, run_id FK, ref_type (URL/FILE/PAYLOAD), ref_value, content_hash, retrieved_at, metadata json
