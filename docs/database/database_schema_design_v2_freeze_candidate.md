# Database Schema Design v2 — Freeze Candidate

> Market Monitor 数据库逻辑结构设计 —— R1A.1 修订交付物
> 日期：2026-08-22 ｜ **Status: FREEZE CANDIDATE — NOT YET APPROVED**
> 本文件为设计候选，**尚未冻结**。基于 `database_schema_design_v1.md` 修订；v1 保留不覆盖。
> 落实 B1–B14；字段级字典见 `data_dictionary_v2_freeze_candidate.md`；物理分库见 `storage_architecture_v2_freeze_candidate.md`。

---

## 0. 全局约定（v2 更新）

| 项目 | 约定 |
|------|------|
| Local surrogate ID | 全表 `INTEGER PRIMARY KEY`（SQLite ROWID 别名），**仅单库内部使用** |
| Stable UID | 关键表 `*_uid TEXT UNIQUE NOT NULL`（UUIDv4）；**跨库引用必须用 UID，禁止用 INTEGER id / ROWID** |
| Instant | TEXT UTC ISO-8601：`2026-08-17T02:30:00Z` |
| Calendar date | TEXT `YYYY-MM-DD`（无时区，日历语义） |
| Currency | ISO 4217 大写（USD/HKD/CNY/JPY） |
| Country | ISO 3166-1 alpha-2（CN/HK/US） |
| Exchange | ISO 10383 MIC（XSHG/XSHE/XHKG/XNYS/XNAS），非交易所用 `NONE` |
| Enum | 稳定小枚举用 SQL CHECK + 应用层常量；不建冗余 lookup 表 |
| JSON | 仅 flexible metadata / LLM 结构化输出 / provider payload |
| 时区 | 凡"时刻"必 UTC；事件另存 `event_timezone`（IANA） |
| Hash | `content_hash` 一律 SHA-256 hex（64 字符小写） |

---

## 1. core.db —— Core 表（17 张，含 infra）

### 1.1 `entities` — 经济主体（PUBLIC）

- PK：`entity_id`；**UID：`entity_uid TEXT UNIQUE NOT NULL`**
- UNIQUE：**无 canonical_name 唯一约束（B2）**；`(entity_uid)` 唯一
- FK：无
- Mutability：可变（名称/状态可更新）
- 说明：canonical_name 仅展示/搜索名；sector/industry R1 不入表；身份由 entity_uid + entity_identifiers 承担。

### 1.2 `entity_identifiers` — Entity 级标识（PUBLIC，B1 新增）

- PK：`entity_identifier_id`
- FK：`entity_id` → entities
- UNIQUE：
  - `(provider, identifier_type, identifier, valid_to)`
  - partial unique：`UNIQUE(provider, identifier_type, identifier) WHERE valid_to IS NULL`
- CHECK：`identifier_type IN ('LEI','SEC_CIK','PROVIDER_COMPANY_ID','GLEIF','OTHER')`
- Mutability：append-only（错误用 valid_to 关闭 + 新行）
- 说明：**LEI / SEC CIK / provider 内部公司 ID 属 Entity**。ticker/ISIN/FIGI/CUSIP 属 Instrument（见 instrument_identifiers），二者严格分属（B1）。

### 1.3 `instruments` — 金融工具（PUBLIC）

- PK：`instrument_id`；**UID：`instrument_uid TEXT UNIQUE NOT NULL`**
- FK：`entity_id` → entities（NULL：指数/FX/无发行主体）
- UNIQUE：`(instrument_uid)`
- **无 `UNIQUE(instrument_type, primary_symbol, exchange_code)`（F1）**：ticker 可被历史重用（A 公司 ABC@XNAS 2020 delisted，B 公司 ABC@XNAS 2025 listed），符号组合不能是身份约束。`primary_symbol` 仅作当前展示/便利字段；**ticker is an attribute / identifier, not identity**；ticker 历史唯一性只由 `instrument_identifiers`（valid_from/valid_to + partial unique）控制。
- Mutability：可变
- 说明：provider 标识一律进 instrument_identifiers。

### 1.4 `instrument_identifiers` — Instrument 级标识（PUBLIC）

- PK：`identifier_id`
- FK：`instrument_id` → instruments
- UNIQUE：`(provider, identifier_type, identifier, valid_to)`；partial `UNIQUE(provider, identifier_type, identifier) WHERE valid_to IS NULL`
- CHECK：`identifier_type IN ('TICKER','EXCHANGE_SYMBOL','ISIN','CUSIP','SEDOL','FIGI','CURRENCY_PAIR')`
- Mutability：append-only

### 1.5 `data_sources` — 数据源（PUBLIC）

- PK：`source_id`
- UNIQUE：`(source_code)`
- Mutability：可变
- 说明：**`priority` 字段已从设计中删除（F3）**，不再存在；所有 source precedence 统一由 `dataset_sources`（role + priority_rank）定义，避免遗留强语义字段被未来应用误用。

### 1.6 `datasets` — 逻辑数据集（PUBLIC）

- PK：`dataset_id`
- **无 `primary_source_id`（F2）**：已从设计中删除——主源判定只有一个真源模型：`datasets` → `dataset_sources` → `data_sources`。任何 provider 是主源只能由 `dataset_sources`（role='PRIMARY'）决定，杜绝双 source-of-truth。
- UNIQUE：`(dataset_code)`
- Mutability：可变

### 1.7 `dataset_sources` — 数据集源优先级（PUBLIC，B9 新增，F4 修正）

- PK：`dataset_source_id`
- FK：`dataset_id` → datasets；`source_id` → data_sources
- UNIQUE：`(dataset_id, source_id)`；**`(dataset_id, priority_rank)`**（F4：同一数据集内排序唯一）
- **partial unique：`UNIQUE(dataset_id) WHERE role='PRIMARY' AND is_active=1`**（F4：每个 dataset 至多一个 active PRIMARY；历史/非活跃 PRIMARY 可共存）
- CHECK：`role IN ('PRIMARY','FALLBACK','ARCHIVE')`
- 字段：`priority_rank INTEGER NOT NULL`（数字越小优先级越高；PRIMARY=1，FALLBACK 依次 2、3…）、`is_active BOOLEAN NOT NULL DEFAULT 1`、`notes`、`created_at`、`updated_at`
- Mutability：可变
- 说明：示例——US_EQUITY_DAILY：FMP PRIMARY/rank1，Alpha Vantage FALLBACK/rank2，Yahoo FALLBACK/rank3；CN_EQUITY_DAILY：TUSHARE PRIMARY/1，FMP FALLBACK/2；US_FILINGS：SEC PRIMARY/1。

### 1.8 `ingest_runs` — 抓取运行审计（PUBLIC）

- PK：`run_id`
- FK：`dataset_id` → datasets；`source_id` → data_sources
- UNIQUE：`(dataset_id, source_id, started_at)`（防止重复审计）
- Mutability：append-only（status RUNNING→终态允许更新）
- 索引：`(dataset_id, started_at)`

### 1.9 `raw_artifacts` — 原始证据存档（PUBLIC，B12 提升 Core）

- PK：`artifact_id`；**UID：`artifact_uid TEXT UNIQUE NOT NULL`**
- FK：`dataset_id` → datasets；`source_id` → data_sources；`run_id` → ingest_runs（NULL=手工/非 ingest 产物）
- UNIQUE：`(artifact_uid)`；**partial `UNIQUE(run_id, content_hash) WHERE run_id IS NOT NULL`**（F5：同一次 run 内防重复 artifact）
- **INDEX：`(content_hash)`（普通索引，非 UNIQUE）**（F5：相同内容可在不同 run / 不同 provider / 不同时间重复登记——这些 provenance 都有意义；hash 用于内容身份与 dedup detection，不等于 provenance record identity）
- CHECK：`artifact_type IN ('FILE','URL','API_PAYLOAD','DB_SNAPSHOT','ARCHIVE','OTHER')`
- 字段：`local_path_or_reference TEXT`、`content_hash TEXT NOT NULL`（SHA-256）、`retrieved_at`、`metadata JSON`
- Mutability：append-only（raw 证据不覆盖）
- 说明：canonical 数据必须可追溯到下载/原始证据；legacy market.db 迁移时也注册为 raw_artifact（B14）。

### 1.10 `data_gaps` — 数据缺口登记（PUBLIC）

- PK：`gap_id`
- FK：`dataset_id` → datasets；`instrument_id` → instruments（NULL=非标的级）；`related_run_id` → ingest_runs（NULL=手工登记）
- Mutability：可变（status/resolution 更新）
- 索引：`(dataset_id, status)`

### 1.11 `market_prices_daily` — 标准化日线（PUBLIC，B13 血缘）

- PK：`bar_id`
- FK：`instrument_id` → instruments；`source_id` → data_sources；**`ingest_run_id` → ingest_runs**；**`raw_artifact_id` → raw_artifacts（NULL=无独立 artifact，如直接数据库导出）**
- UNIQUE：`(instrument_id, trade_date, adjustment_type, source_id)`
- Mutability：受控 upsert（同键覆盖 + `ingested_at` 更新；原始证据在 raw_artifacts）
- 索引：`(instrument_id, trade_date)`；`(trade_date)`；`(ingest_run_id)`
- 说明：volume/turnover 带显式 unit；adjustment_type 显式；多 provider 共存（source_id 区分）。**血缘：每行可回答"哪次 ingest、哪个 source、哪个 raw artifact"（B13）。**

### 1.12 `events` — 事件事实（PUBLIC）

- PK：`event_id`；**UID：`event_uid TEXT UNIQUE NOT NULL`**
- FK：**`discovered_by_source_id`** → data_sources（NULL=人工）
- UNIQUE：`(event_uid)`；`(fingerprint)`（去重）
- Mutability：append-only（status 可流转 NEW→CONFIRMED/SUPERSEDED/REJECTED）
- 说明：**不再设单一 entity_id / instrument_id 列（B10）**；主体关系全部在 event_entities / event_instruments。
- **`discovered_by_source_id` 语义（F7，Option B 采纳）**：表示**第一次让系统创建 normalized event 的 source（detection provenance）**——即“谁最先发现”。它**不是** primary evidence、**不是** canonical truth source；事件的全部真实来源由 `event_evidence` 表达。未来 dedupe 时可用它判断“谁先发现”。

### 1.13 `event_entities` — 事件主体（多 Entity）（PUBLIC，B10 新增）

- PK：`event_entity_id`
- FK：`event_id` → events；`entity_id` → entities
- UNIQUE：`(event_id, entity_id, role)`
- CHECK：`role IN ('PRIMARY','ACQUIRER','TARGET','ISSUER','AFFECTED','RELATED')`
- Mutability：append-only（纠错用 status/valid_to 或新行）
- 索引：`(entity_id, event_date 经 join)` → 索引 `(entity_id)`

### 1.14 `event_instruments` — 事件相关工具（多 Instrument）（PUBLIC，B10 新增）

- PK：`event_instrument_id`
- FK：`event_id` → events；`instrument_id` → instruments
- UNIQUE：`(event_id, instrument_id, role)`
- CHECK：`role IN ('PRIMARY','ACQUIRER','TARGET','ISSUER','AFFECTED','RELATED')`
- Mutability：append-only
- 索引：`(instrument_id)`

### 1.15 `event_evidence` — 多源事件证据（PUBLIC，B11 新增，F6 修正）

- PK：`evidence_id`；**UID：`evidence_uid TEXT UNIQUE NOT NULL`**
- FK：`event_id` → events；`source_id` → data_sources
- **UNIQUE：`(evidence_uid)`；`(event_id, source_id, source_reference)`**（F6：source-level evidence identity——同一事件、同一来源、同一引用只记一次）
- **INDEX：`(content_hash)`（普通索引）**（F6：用于判断多个 evidence 是否内容相同；不同 source 提供相同内容可以共存，不丢 provenance）
- partial `UNIQUE(event_id) WHERE is_primary=1`（每事件至多一条主证据）
- CHECK：`evidence_type IN ('HKEX_FILING','SEC_FILING','COMPANY_IR','NEWS','API_PAYLOAD','MANUAL','OTHER')`
- 字段：`source_reference TEXT`（URL/ref，**可 NULL**）、`published_at`、`detected_at`、`content_hash TEXT NOT NULL`、`is_primary BOOLEAN NOT NULL DEFAULT 0`、`metadata JSON`
- Mutability：append-only
- 索引：`(event_id)`；`(detected_at)`
- **NULL 行为（F6）**：SQLite UNIQUE 中 NULL 相互不冲突——若 `source_reference` 为 NULL 且同一 (event_id, source_id) 需多条证据，可用 `evidence_key`（deterministic normalized key，如 hash(source+ref) 或人工键）作为业务唯一键；R1B 若出现该需求再加，本轮不做过度设计。

### 1.16 `event_analysis` — Generic 事件分析（PUBLIC，B7 收敛，F8B 修正）

- PK：`analysis_id`；**UID：`analysis_uid TEXT UNIQUE NOT NULL`**（F8B：UUIDv4，跨库稳定身份，供 private.alerts 精确引用“哪一次 generic analysis 触发 alert”）
- FK：`event_id` → events
- UNIQUE：`(event_id, model_provider, model_id, prompt_version, analysis_version)`（**业务唯一防重复**，F8B 后保留）
- Mutability：append-only（rerun = 新 analysis_version 新行）
- 说明：**仅 generic market/event analysis**（importance_score 1–5、summary、bullish/bearish points、recommended_attention、raw_output、model 信息）。**禁止 thesis_id / portfolio relevance / 私人持仓（B7）**；私人 thesis 分析进 private.db `event_thesis_analysis`。
- **角色分工（F8B）**：`analysis_uid` 负责稳定跨库 identity；业务 UNIQUE 负责防重复。两个角色不混淆。

### 1.17 `schema_migrations` — 迁移记录（PUBLIC, infra）

- PK：`migration_id`（TEXT）
- Mutability：append-only

---

## 2. private.db —— Core 表（7 张）

### 2.1 `accounts` — 账户（PRIVATE，B5 提升 Core，F8A 修正）

- PK：`account_id`；**UID：`account_uid TEXT UNIQUE NOT NULL`**
- UNIQUE：`(account_uid)`；`(account_name)`
- CHECK：`account_type IN ('CASH','MARGIN','RETIREMENT','PAPER','OTHER')`；`status IN ('ACTIVE','CLOSED')`
- 字段：`account_name TEXT NOT NULL`、`broker TEXT`（券商名，如 IBKR/富途/券商 A）、`base_currency TEXT NOT NULL`（ISO 4217）
- **account_type 与 broker 分离（F8A）**：`account_type` 只描述账户性质（现金/保证金/退休/模拟/其他），**不含 broker 名**（IBKR/BROKER 不是 type）；券商由 `broker` 字段表达。例如 broker='IBKR' + account_type='MARGIN'。
- **不保存 password/token/credential（B5）**；凭据属外部系统，不入库。
- Mutability：可变

### 2.2 `positions` — 持仓快照（PRIVATE，B6 修正）

- PK：`position_id`
- FK：**`account_id` → accounts（同库，NOT NULL）**
- 跨库引用：**`instrument_uid TEXT NOT NULL` → core.instruments.instrument_uid（无 FK 约束，应用层校验）**
- UNIQUE（partial）：**`UNIQUE(account_id, instrument_uid) WHERE status='OPEN'`**（同一账户同一标的仅一条 OPEN 快照；CLOSED 历史行不受限）
- Mutability：**snapshot 语义**——一行=当前状态，同步/更新时覆盖；完整历史由未来 `transactions`（Deferred）解释
- 字段：`quantity REAL NOT NULL`、`avg_cost REAL`、`currency_code TEXT NOT NULL`（成本币种）、`as_of_date DATE NOT NULL`、`source TEXT`（MANUAL/BROKER_IMPORT/…）、`status CHECK('OPEN','CLOSED')`

### 2.3 `watchlists` — 自选列表（PRIVATE）

- PK：`watchlist_id`
- UNIQUE：`(name)`
- Mutability：可变

### 2.4 `watchlist_items` — 自选条目（PRIVATE，B4 XOR）

- PK：`item_id`
- FK：`watchlist_id` → watchlists（同库）
- 跨库引用：`entity_uid TEXT NULL`、`instrument_uid TEXT NULL` → core（无 FK，应用层校验）
- **CHECK（XOR，B4）**：`(entity_uid IS NOT NULL AND instrument_uid IS NULL) OR (entity_uid IS NULL AND instrument_uid IS NOT NULL)`
- UNIQUE（分别防重复，B4）：
  - partial：`UNIQUE(watchlist_id, entity_uid) WHERE entity_uid IS NOT NULL`
  - partial：`UNIQUE(watchlist_id, instrument_uid) WHERE instrument_uid IS NOT NULL`
- Mutability：可变（priority/reason/status 更新）
- 说明：关注"公司"用 entity_uid；关注"具体工具"用 instrument_uid；两者互斥。

### 2.5 `investment_theses` — 投资逻辑（PRIVATE）

- PK：`thesis_id`
- 跨库引用：`entity_uid TEXT NOT NULL` → core.entities.entity_uid
- Mutability：可变（版本历史未来由 thesis_versions 提供）
- 说明：挂 entity 不挂 ticker；base/bull/bear/invalidate 用 Markdown；key_metrics/key_catalysts/key_risks JSON 数组。

### 2.6 `event_thesis_analysis` — 事件 ↔ 投资逻辑分析（PRIVATE，B7 新增）

- PK：`thesis_analysis_id`
- FK：`thesis_id` → investment_theses（同库）
- 跨库引用：`event_uid TEXT NOT NULL` → core.events.event_uid
- UNIQUE：`(event_uid, thesis_id, analysis_version)`
- CHECK：`impact_direction IN ('POSITIVE','NEGATIVE','NEUTRAL','MIXED')`；`impact_severity INTEGER 1..5`
- 字段：`reasoning_summary TEXT`、`invalidate_triggered BOOLEAN NOT NULL DEFAULT 0`、`recommended_attention TEXT`、`model_provider`、`model_id`、`prompt_version`、`analysis_version`、`raw_output TEXT`、`created_at`
- Mutability：append-only（rerun = 新 analysis_version）
- 索引：`(thesis_id)`

### 2.7 `alerts` — 告警（PRIVATE，B8 移入，F8B 扩展）

- PK：`alert_id`；UID：`alert_uid TEXT UNIQUE NOT NULL`
- UNIQUE：`(alert_key)`
- 跨库引用：`event_uid TEXT NULL` → core.events.event_uid；`instrument_uid TEXT NULL` → core.instruments.instrument_uid；**`generic_analysis_uid TEXT NULL` → core.event_analysis.analysis_uid**（F8B：按 alert 类型选择；非所有 alert 都需要）
- 同库引用：`thesis_analysis_id` → event_thesis_analysis（NULL=非 thesis 驱动）
- CHECK：`status IN ('PENDING','SENT','FAILED','ACKED','DISMISSED')`
- 字段：`alert_type TEXT`（R6 定义）、`channel TEXT`、`rule_ref TEXT`、`delivered_at`、`created_at`、`updated_at`
- Mutability：可变（状态流转）
- 说明：**PRIVATE / RUNTIME USER STATE**，不再属于 PUBLIC core（B8）。alert 可依据类型关联 event_uid / generic_analysis_uid / thesis_analysis_id 之一或多个。

---

## 3. Deferred 表（仅接口设计，R1 不实施）

| 表 | Domain | 说明 |
|----|--------|------|
| `transactions` | B | canonical ledger（BUY/SELL/DIVIDEND/FEE/CORP_ACTION）；建立后 positions 转 derived |
| `thesis_versions` | B | thesis 快照版本 |
| `financial_reports` | D | 报告头（GAAP/IFRS/non-GAAP / restatement） |
| `financial_facts` | D | long-form 财务事实（metric_key 受控字典） |

---

## 4. 关键架构决议（v2 增量，完整见 v1 §3 + storage v2）

1. **身份 = UID，surrogate = INTEGER**：跨库引用只用 `*_uid`；INTEGER PK 永不跨库（B3）。
2. **Entity/Instrument 标识分属**：entity_identifiers vs instrument_identifiers（B1）。
3. **事件多主体、多证据**：event_entities / event_instruments / event_evidence（B10/B11）。
4. **分析三层分离**：events（事实）→ event_analysis（generic，core）→ event_thesis_analysis（private，thesis 级）+ alerts（private，运行时状态）（B7/B8）。
5. **数据集源优先级**：dataset_sources（B9）；data_sources.priority 无 canonical 含义。
6. **原始证据 Core**：raw_artifacts 提升；行情带 ingest_run_id/raw_artifact_id 血缘（B12/B13）。
7. **legacy 溯源**：market.db 备份 + raw_artifact + SHA-256；normalized completeness + raw provenance completeness（B14）。
