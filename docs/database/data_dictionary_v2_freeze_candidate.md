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
| `data_sources.priority` | **已删除（F3）**：Freeze Candidate 中不再存在该字段；优先级统一由 `dataset_sources`（role + priority_rank）定义 |

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

其余与 v1 一致，除：**`primary_symbol` 不再参与唯一约束（F1）**——`UNIQUE(instrument_type, primary_symbol, exchange_code)` 已移除；primary_symbol 仅作展示/便利字段；ticker 历史唯一性由 `instrument_identifiers`（valid_from/valid_to + partial unique）控制。

### 1.4 instrument_identifiers（C）— 不变（v1）

provider 中立 Instrument 标识（TICKER/EXCHANGE_SYMBOL/ISIN/CUSIP/SEDOL/FIGI/CURRENCY_PAIR）。**与 entity_identifiers 严格分属（B1）。**

### 1.5 data_sources（C）— v2 变更

| field | 变更 |
|-------|------|
| priority | **已删除（F3）**：不再存在；所有 source precedence 统一由 `dataset_sources` 定义 |

其余与 v1 一致。

### 1.6 datasets（C）— v2 变更（F2）

| field | 变更 |
|-------|------|
| primary_source_id | **已移除（F2）**：主源判定单真源，统一由 `dataset_sources` 决定 |

其余与 v1 一致。

### 1.7 dataset_sources（C）— **新增（B9）**

| field | type | nullable | key | description |
|-------|------|----------|-----|-------------|
| dataset_source_id | integer | NO | PK | |
| dataset_id | integer | NO | FK→datasets | 数据集 |
| source_id | integer | NO | FK→data_sources | 数据源 |
| priority_role | text | NO | CHECK | `PRIMARY / FALLBACK / ARCHIVE` |
| **priority_rank** | integer | NO | UNIQUE(dataset_id, priority_rank) | 排序：数字越小优先级越高（PRIMARY=1，FALLBACK 依次 2、3…）（F4） |
| is_active | boolean | NO | | 是否启用 |
| notes | text | YES | | 备注（限额、切换条件） |
| created_at / updated_at | datetime(UTC) | NO | | |

UNIQUE：`(dataset_id, source_id)`；`(dataset_id, priority_rank)`
partial unique：`UNIQUE(dataset_id) WHERE role='PRIMARY' AND is_active=1`（每个 dataset 至多一个 active PRIMARY；历史/非活跃 PRIMARY 可共存，F4）
示例：US_EQUITY_DAILY→(FMP,PRIMARY,1),(ALPHA_VANTAGE,FALLBACK,2),(YAHOO,FALLBACK,3)；CN_EQUITY_DAILY→(TUSHARE,PRIMARY,1),(FMP,FALLBACK,2)；US_FILINGS→(SEC,PRIMARY,1)。

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
| content_hash | text | NO | INDEX + partial UNIQUE(run_id, content_hash) WHERE run_id IS NOT NULL | SHA-256 hex；内容身份/dedup detection；相同内容可在不同 run / source 重复登记（F5） |
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
| source_id | **更名 `discovered_by_source_id`（F7，Option B）**：第一次创建 normalized event 的 source（detection provenance）；非 primary evidence、非 canonical truth；事件真实来源由 event_evidence 表达 |

其余（fingerprint 去重、event_type/time/timezone/title/summary/status）与 v1 一致。

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
| content_hash | text | NO | INDEX | SHA-256（内容身份/dedup detection；不同 source 相同内容可共存，F6） |
| is_primary | boolean | NO | partial UNIQUE(event_id) WHERE is_primary=1 | 主证据标记（每事件至多一条） |
| metadata | json | YES | | 原始元数据 |
| created_at | datetime(UTC) | NO | | |

UNIQUE：`(evidence_uid)`；`(event_id, source_id, source_reference)`（source-level evidence identity，F6）；partial `UNIQUE(event_id) WHERE is_primary=1`
INDEX：`(content_hash)`（F6：判断多个 evidence 是否内容相同）
source_reference 可 NULL：SQLite UNIQUE 中 NULL 互不冲突——若需同一 (event_id, source_id) 多条 NULL ref 证据，R1B 可加 `evidence_key`（deterministic normalized key），本轮不过度设计。

Mutability：append-only。

### 1.16 event_analysis（C）— v2 变更（B7）

| field | 变更 |
|-------|------|
| thesis_impact / thesis 相关字段 | **移除**（v1 曾有 thesis_impact 映射）——generic 分析不得含 thesis/portfolio 内容（B7） |
| **analysis_uid** | **新增（F8B）**：UUIDv4，TEXT UNIQUE NOT NULL；跨库稳定身份，供 private.alerts.generic_analysis_uid 引用 |

保留：importance_score、summary、bullish_points、bearish_points、recommended_attention、model_provider/model_id/prompt_version/analysis_version、raw_output。
业务 UNIQUE 不变：`(event_id, model_provider, model_id, prompt_version, analysis_version)`（防重复；analysis_uid 负责稳定跨库 identity，两角色不混淆，F8B）。

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
| account_type | text | NO | CHECK | `CASH / MARGIN / RETIREMENT / PAPER / OTHER`（F8A：不含 broker 名；券商由 broker 字段表达） |
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
| **generic_analysis_uid** | text | YES | 跨库引用 | → core.event_analysis.analysis_uid（F8B：哪次 generic analysis 触发；按 alert 类型选择，非必需） |
| thesis_analysis_id | integer | YES | FK→event_thesis_analysis | 同库（可选） |
| alert_type | text | NO | | R6 定义（THESIS_IMPACT/EVENT/PRICE/…） |
| channel | text | YES | | telegram/email/… |
| rule_ref | text | YES | | 触发规则引用 |
| status | text | NO | CHECK | `PENDING / SENT / FAILED / ACKED / DISMISSED` |
| delivered_at | datetime(UTC) | YES | | |
| created_at / updated_at | datetime(UTC) | NO | | |

说明：PRIVATE / RUNTIME USER STATE，属 private.db（B8）；不属 PUBLIC core。alert 可依据类型关联 event_uid / generic_analysis_uid / thesis_analysis_id 之一或多个（F8B）。

---

## 3. Deferred 表（v1 定义不变）

`transactions` / `thesis_versions` / `financial_reports` / `financial_facts` —— 仅接口设计，R1 不实施。

---

## 4. v1→v2 字段变更汇总

| 表 | 变更类型 | 内容 |
|----|---------|------|
| entities | 改 | +entity_uid；canonical_name 去 UNIQUE |
| entity_identifiers | 新 | B1 |
| instruments | 改 | +instrument_uid；去 symbol 复合 UNIQUE（F1） |
| data_sources | 改 | priority 删除（F3） |
| ingest_runs | 改 | +UNIQUE(dataset_id, source_id, started_at) |
| datasets | 改 | primary_source_id 移除（F2） |
| dataset_sources | 新 | B9；+priority_rank 排序（F4） |
| raw_artifacts | 升 | Deferred→Core（B12）；hash 语义修正（F5） |
| market_prices_daily | 改 | +ingest_run_id / raw_artifact_id（B13） |
| events | 改 | +event_uid；移除单一 entity_id/instrument_id（B10）；source_id→discovered_by_source_id（F7） |
| event_entities / event_instruments | 新 | B10 |
| event_evidence | 新 | B11；唯一性→source-level（F6） |
| event_analysis | 改 | 移除 thesis 相关字段（B7）；+analysis_uid（F8B） |
| accounts | 升 | Deferred→Core（B5）；account_type 规范化（F8A） |
| positions | 改 | account_id NOT NULL FK + instrument_uid（B6） |
| watchlist_items | 改 | entity_uid/instrument_uid XOR + 双 partial unique（B4） |
| investment_theses | 改 | entity_id → entity_uid |
| event_thesis_analysis | 新 | B7 |
| alerts | 移 | core → private（B8）；+generic_analysis_uid（F8B） |
