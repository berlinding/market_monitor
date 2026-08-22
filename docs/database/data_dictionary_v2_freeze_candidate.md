# Data Dictionary v2 — Freeze Candidate

> Market Monitor 字段级数据字典 —— R1A.1 修订交付物
> 日期：2026-08-22 ｜ **Status: FREEZE CANDIDATE — NOT YET APPROVED**
> 基于 `data_dictionary_v1.md` 修订；v1 保留不覆盖。只列 v2 变更/新增表；未列字段与 v1 一致。
> tables 简称：`C`=core.db / `P`=private.db

---

## 0. v2 通用变更

| 变更 | 说明 |
|------|------|
| `*_uid` | 关键表新增 `TEXT UNIQUE NOT NULL`（UUIDv4）；跨库引用只用 uid |
| `content_hash` | 一律 SHA-256 hex（64 字符小写） |
| `data_sources.priority` | **弃用 canonical 含义**（B9），R1B 不再使用；保留列作备注或移除 |

通用字段（created_at / updated_at / status）与 v1 一致，不再逐表重复。

---

## 1. core.db（C, PUBLIC）

### 1.1 entities（C）— v2 变更

| field | type | nullable | key | description | 变更 |
|-------|------|----------|-----|-------------|------|
| entity_id | integer | NO | PK | 单库 surrogate（禁止跨库引用） | |
| **entity_uid** | text | NO | **UNIQUE** | UUIDv4 稳定身份；跨库引用实体 | **新增（B3）** |
| canonical_name | text | NO | ~~UNIQUE~~ | 展示/搜索名 | **去 UNIQUE（B2）** |

其余字段（entity_type/country_code/status）与 v1 一致。

### 1.2 entity_identifiers（C）— **新增（B1）**

| field | type | nullable | key | description |
|-------|------|----------|-----|-------------|
| entity_identifier_id | integer | NO | PK | 记录 ID |
| entity_id | integer | NO | FK→entities | 指向主体 |
| provider | text | NO | UNIQUE 复合 | 命名空间：SEC/LEI_PROVIDER/FMP/TUSHARE/MANUAL… |
| identifier_type | text | NO | CHECK | `LEI / SEC_CIK / PROVIDER_COMPANY_ID / GLEIF / OTHER` |
| identifier | text | NO | UNIQUE 复合 | 标识值，如 LEI `549300T16QP6X4X6VW28`、SEC CIK `0001045810` |
| valid_from | date | NO | | 生效日 |
| valid_to | date | YES | | 失效日（NULL=当前有效） |
| is_primary | boolean | NO | | 该 provider 内首选 |
| created_at | datetime(UTC) | NO | | |

UNIQUE：`(provider, identifier_type, identifier, valid_to)`；partial `UNIQUE(provider, identifier_type, identifier) WHERE valid_to IS NULL`
CHECK：`identifier_type IN ('LEI','SEC_CIK','PROVIDER_COMPANY_ID','GLEIF','OTHER')`

### 1.3 instruments（C）— v2 变更

| field | type | nullable | key | 变更 |
|-------|------|----------|-----|------|
| instrument_id | integer | NO | PK | 单库 surrogate |
| **instrument_uid** | text | NO | **UNIQUE** | UUIDv4 稳定身份；跨库引用工具 | **新增（B3）** |

其余与 v1 一致。

### 1.4 instrument_identifiers（C）— 不变（v1）

provider 中立 Instrument 标识（TICKER/EXCHANGE_SYMBOL/ISIN/CUSIP/SEDOL/FIGI/CURRENCY_PAIR）。**与 entity_identifiers 严格分属（B1）。**

### 1.5 data_sources（C）— v2 变更

| field | 变更 |
|-------|------|
| priority | **弃用 canonical 含义（B9）**；保留列作一般备注，R1B 不再读取 |

其余与 v1 一致。

### 1.6 datasets（C）— 不变（v1）

### 1.7 dataset_sources（C）— **新增（B9）**

| field | type | nullable | key | description |
|-------|------|----------|-----|-------------|
| dataset_source_id | integer | NO | PK | |
| dataset_id | integer | NO | FK→datasets | 数据集 |
| source_id | integer | NO | FK→data_sources | 数据源 |
| priority_role | text | NO | CHECK | `PRIMARY / FALLBACK / ARCHIVE` |
| is_active | boolean | NO | | 是否启用 |
| notes | text | YES | | 备注（限额、切换条件） |
| created_at / updated_at | datetime(UTC) | NO | | |

UNIQUE：`(dataset_id, source_id)`
示例：CN_EQUITY_DAILY→(TUSHARE,PRIMARY),(FMP,FALLBACK)；US_EQUITY_DAILY→(FMP,PRIMARY),(ALPHA_VANTAGE,FALLBACK)；US_FILINGS→(SEC,PRIMARY)。

### 1.8 ingest_runs（C）— v2 变更

UNIQUE：`(dataset_id, source_id, started_at)` 新增（防重复审计）。其余与 v1 一致。

### 1.9 raw_artifacts（C）— **提升 Core（B12）**

| field | type | nullable | key | description |
|-------|------|----------|-----|-------------|
| artifact_id | integer | NO | PK | 单库 surrogate |
| **artifact_uid** | text | NO | **UNIQUE** | UUIDv4 稳定身份 |
| dataset_id | integer | NO | FK→datasets | 所属数据集 |
| source_id | integer | NO | FK→data_sources | 来源 |
| run_id | integer | YES | FK→ingest_runs | 产生它的 ingest（NULL=手工） |
| artifact_type | text | NO | CHECK | `FILE / URL / API_PAYLOAD / DB_SNAPSHOT / ARCHIVE / OTHER` |
| local_path_or_reference | text | YES | | 本地路径或 URL（不入 Git 的 data/raw/ 下） |
| content_hash | text | NO | UNIQUE | SHA-256 hex |
| retrieved_at | datetime(UTC) | NO | | 抓取/登记时刻 |
| metadata | json | YES | | provider payload 元数据 |
| created_at | datetime(UTC) | NO | | |

Mutability：append-only（raw 不覆盖）。

### 1.10 data_gaps（C）— 不变（v1）

### 1.11 market_prices_daily（C）— v2 变更（B13）

| field | type | nullable | key | description |
|-------|------|----------|-----|-------------|
| **ingest_run_id** | integer | NO | FK→ingest_runs | 该行的 ingest 来源（B13） |
| **raw_artifact_id** | integer | YES | FK→raw_artifacts | 原始证据（NULL=直接 DB 导出等） |

UNIQUE：`(instrument_id, trade_date, adjustment_type, source_id)`（不变）；索引 `(ingest_run_id)` 新增。
血缘：一行行情 → ingest_run → (source, dataset, time) → raw_artifact（可选）→ 完整追溯。

### 1.12 events（C）— v2 变更

| field | 变更 |
|-------|------|
| **event_uid** | **新增（B3）**：UUIDv4，UNIQUE |
| entity_id / instrument_id | **移除（B10）**：不再有单一主体列；多主体关系在 event_entities / event_instruments |

其余（fingerprint 去重、event_type/time/timezone/title/summary/source/status）与 v1 一致。

### 1.13 event_entities（C）— **新增（B10）**

| field | type | nullable | key | description |
|-------|------|----------|-----|-------------|
| event_entity_id | integer | NO | PK | |
| event_id | integer | NO | FK→events | |
| entity_id | integer | NO | FK→entities | 参与主体 |
| role | text | NO | CHECK | `PRIMARY / ACQUIRER / TARGET / ISSUER / AFFECTED / RELATED` |
| created_at | datetime(UTC) | NO | | |

UNIQUE：`(event_id, entity_id, role)`；索引 `(entity_id)`

### 1.14 event_instruments（C）— **新增（B10）**

同 event_entities 结构：`event_id`、`instrument_id`、`role`（同 CHECK）、`created_at`。
UNIQUE：`(event_id, instrument_id, role)`；索引 `(instrument_id)`

### 1.15 event_evidence（C）— **新增（B11）**

| field | type | nullable | key | description |
|-------|------|----------|-----|-------------|
| evidence_id | integer | NO | PK | 单库 surrogate |
| **evidence_uid** | text | NO | **UNIQUE** | UUIDv4 稳定身份 |
| event_id | integer | NO | FK→events | 对应 normalized event |
| source_id | integer | NO | FK→data_sources | 证据来源（SEC/HKEX/…） |
| evidence_type | text | NO | CHECK | `HKEX_FILING / SEC_FILING / COMPANY_IR / NEWS / API_PAYLOAD / MANUAL / OTHER` |
| source_reference | text | YES | | URL / filing ref / 文件路径 |
| published_at | datetime(UTC) | YES | | 证据发布时间 |
| detected_at | datetime(UTC) | NO | | 系统发现时刻 |
| content_hash | text | NO | UNIQUE(event_id,content_hash) | SHA-256（同事件同内容去重） |
| is_primary | boolean | NO | partial UNIQUE(event_id) WHERE is_primary=1 | 主证据标记（每事件至多一条） |
| metadata | json | YES | | 原始元数据 |
| created_at | datetime(UTC) | NO | | |

Mutability：append-only。

### 1.16 event_analysis（C）— v2 变更（B7）

| field | 变更 |
|-------|------|
| thesis_impact / thesis 相关字段 | **移除**（v1 曾有 thesis_impact 映射）——generic 分析不得含 thesis/portfolio 内容（B7） |

保留：importance_score、summary、bullish_points、bearish_points、recommended_attention、model_provider/model_id/prompt_version/analysis_version、raw_output。UNIQUE 不变。

### 1.17 schema_migrations（C, infra）— 不变（v1）

---

## 2. private.db（P, PRIVATE）

### 2.1 accounts（P）— **提升 Core（B5）**

| field | type | nullable | key | description |
|-------|------|----------|-----|-------------|
| account_id | integer | NO | PK | 单库 surrogate |
| **account_uid** | text | NO | **UNIQUE** | UUIDv4 稳定身份 |
| account_name | text | NO | UNIQUE | 账户名 |
| broker | text | YES | | 券商（IBKR/券商A…） |
| account_type | text | NO | CHECK | `CASH / MARGIN / IBKR / BROKER / OTHER` |
| base_currency | text | NO | | ISO 4217（USD/HKD/CNY） |
| status | text | NO | CHECK | `ACTIVE / CLOSED` |
| created_at / updated_at | datetime(UTC) | NO | | |

**不保存 password/token/credential（B5）**——凭据在外部系统，数据库只存身份与属性。

### 2.2 positions（P）— v2 修正（B6）

| field | type | nullable | key | description |
|-------|------|----------|-----|-------------|
| position_id | integer | NO | PK | |
| **account_id** | integer | NO | **FK→accounts** | 所属账户（原来 account_ref 文本） |
| **instrument_uid** | text | NO | 跨库引用 | → core.instruments.instrument_uid（无 FK，应用层校验） |
| quantity | real | NO | | 数量 |
| avg_cost | real | YES | | 平均成本 |
| currency_code | text | NO | | 成本币种 |
| as_of_date | date | NO | | 快照日期 |
| source | text | YES | | MANUAL/BROKER_IMPORT/… |
| status | text | NO | CHECK | `OPEN / CLOSED` |
| created_at / updated_at | datetime(UTC) | NO | | |

UNIQUE（partial）：`UNIQUE(account_id, instrument_uid) WHERE status='OPEN'`（B6 重设计：账户级唯一，支持多账户）。
SNAPSHOT 语义不变；transactions 仍 Deferred。

### 2.3 watchlists（P）— 不变（v1）

### 2.4 watchlist_items（P）— v2 变更（B4）

| field | type | nullable | key | description |
|-------|------|----------|-----|-------------|
| item_id | integer | NO | PK | |
| watchlist_id | integer | NO | FK→watchlists | |
| **entity_uid** | text | YES | XOR 之一 | → core.entities.entity_uid（关注公司） |
| **instrument_uid** | text | YES | XOR 之一 | → core.instruments.instrument_uid（关注工具） |
| reason | text | YES | | 关注理由 |
| priority | integer | YES | | |
| status | text | NO | | ACTIVE/ARCHIVED |
| created_at / updated_at | datetime(UTC) | NO | | |

CHECK（XOR）：`(entity_uid IS NOT NULL AND instrument_uid IS NULL) OR (entity_uid IS NULL AND instrument_uid IS NOT NULL)`
UNIQUE（防重复）：partial `UNIQUE(watchlist_id, entity_uid) WHERE entity_uid IS NOT NULL`；partial `UNIQUE(watchlist_id, instrument_uid) WHERE instrument_uid IS NOT NULL`

### 2.5 investment_theses（P）— v2 变更

| field | 变更 |
|-------|------|
| entity_id | **改为 `entity_uid`**（跨库引用 core.entities.entity_uid） |

其余（title/base/bull/bear/invalidate/key_metrics/key_catalysts/key_risks/status）与 v1 一致。

### 2.6 event_thesis_analysis（P）— **新增（B7）**

| field | type | nullable | key | description |
|-------|------|----------|-----|-------------|
| thesis_analysis_id | integer | NO | PK | |
| **event_uid** | text | NO | 跨库引用 | → core.events.event_uid |
| thesis_id | integer | NO | FK→investment_theses | 同库 FK |
| impact_direction | text | NO | CHECK | `POSITIVE / NEGATIVE / NEUTRAL / MIXED` |
| impact_severity | integer | NO | CHECK | 1–5 |
| reasoning_summary | text | YES | | 推理摘要 |
| invalidate_triggered | boolean | NO | | 是否触发 thesis 失效条件 |
| recommended_attention | text | YES | | 建议关注度 |
| model_provider / model_id | text | NO | | 模型信息 |
| prompt_version / analysis_version | text | NO | | 版本 |
| raw_output | text | YES | | 模型原始输出证据 |
| created_at | datetime(UTC) | NO | | |

UNIQUE：`(event_uid, thesis_id, analysis_version)`；索引 `(thesis_id)`
Mutability：append-only。

### 2.7 alerts（P）— **移入 private（B8）**

| field | type | nullable | key | description |
|-------|------|----------|-----|-------------|
| alert_id | integer | NO | PK | |
| **alert_uid** | text | NO | **UNIQUE** | UUIDv4 |
| alert_key | text | NO | UNIQUE | 业务去重键 |
| event_uid | text | YES | 跨库引用 | → core.events.event_uid（可选） |
| instrument_uid | text | YES | 跨库引用 | → core.instruments.instrument_uid（可选） |
| thesis_analysis_id | integer | YES | FK→event_thesis_analysis | 同库（可选） |
| alert_type | text | NO | | R6 定义（THESIS_IMPACT/EVENT/PRICE/…） |
| channel | text | YES | | telegram/email/… |
| rule_ref | text | YES | | 触发规则引用 |
| status | text | NO | CHECK | `PENDING / SENT / FAILED / ACKED / DISMISSED` |
| delivered_at | datetime(UTC) | YES | | |
| created_at / updated_at | datetime(UTC) | NO | | |

说明：PRIVATE / RUNTIME USER STATE，属 private.db（B8）；不属 PUBLIC core。

---

## 3. Deferred 表（v1 定义不变）

`transactions` / `thesis_versions` / `financial_reports` / `financial_facts` —— 仅接口设计，R1 不实施。

---

## 4. v1→v2 字段变更汇总

| 表 | 变更类型 | 内容 |
|----|---------|------|
| entities | 改 | +entity_uid；canonical_name 去 UNIQUE |
| entity_identifiers | 新 | B1 |
| instruments | 改 | +instrument_uid |
| data_sources | 改 | priority 弃用 canonical（B9） |
| ingest_runs | 改 | +UNIQUE(dataset_id, source_id, started_at) |
| dataset_sources | 新 | B9 |
| raw_artifacts | 升 | Deferred→Core（B12） |
| market_prices_daily | 改 | +ingest_run_id / raw_artifact_id（B13） |
| events | 改 | +event_uid；移除单一 entity_id/instrument_id（B10） |
| event_entities / event_instruments | 新 | B10 |
| event_evidence | 新 | B11 |
| event_analysis | 改 | 移除 thesis 相关字段（B7） |
| accounts | 升 | Deferred→Core（B5） |
| positions | 改 | account_id NOT NULL FK + instrument_uid（B6） |
| watchlist_items | 改 | entity_uid/instrument_uid XOR + 双 partial unique（B4） |
| investment_theses | 改 | entity_id → entity_uid |
| event_thesis_analysis | 新 | B7 |
| alerts | 移 | core → private（B8） |
