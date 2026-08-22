# Database Design Decisions v1

> Market Monitor 数据库设计决策登记表（Decision Register）
> 日期：2026-08-22 ｜ **Status: FREEZE CANDIDATE — NOT YET APPROVED**
> 记录 R1A + R1A.1 的数据库设计决策；后续决策追加登记，历史不改写。

---

## DB-D001 — Entity / Instrument split

- **Status**: Adopted（R1A v1 → v2 延续）
- **Decision**: Entity（现实经济主体）与 Instrument（可交易工具）双层身份模型；ticker 不是身份；thesis/watchlist 挂 entity/instrument 不挂 ticker。
- **Rationale**: 一个公司多个工具（0700.HK + TCEHY）；公司事件与投资逻辑针对 Entity；价格/持仓针对 Instrument。
- **Files**: `core_domain_model_v1.md` §2.1/2.2；`core_domain_model_v2_freeze_candidate.md` §3.1/3.2

## DB-D002 — Entity identifiers

- **Status**: Adopted（R1A.1 新增，B1）
- **Decision**: 新增 `entity_identifiers` 表；**LEI、SEC CIK 属 Entity**；ticker/ISIN/FIGI/CUSIP/SEDOL 属 Instrument（instrument_identifiers）。支持 SEC_CIK / LEI / provider_company_id。
- **Rationale**: v1 曾把 LEI 放在 instrument_identifiers，身份归属错误；法人标识必须挂 Entity。
- **Files**: `database_schema_design_v2_freeze_candidate.md` §1.2；`data_dictionary_v2_freeze_candidate.md` §1.2

## DB-D003 — Stable UID + local integer PK

- **Status**: Adopted（R1A.1 新增，B3；**修订 v1 决策 8**）
- **Decision**: 保留 `entity_id/instrument_id/event_id INTEGER PRIMARY KEY` 作单库内部 surrogate；**新增 `entity_uid/instrument_uid/event_uid/account_uid/artifact_uid/evidence_uid TEXT UNIQUE NOT NULL`（UUIDv4）**。跨库引用必须用 UID，禁止用 ROWID/INTEGER id。
- **Rationale**: v1 决策 8（全 integer surrogate）无法保证 core.db 重建/合并后跨库引用稳定；UUIDv4 由 Python stdlib 生成，零依赖、离线可靠、重建不变。
- **Files**: `core_domain_model_v2_freeze_candidate.md` §5；`storage_architecture_v2_freeze_candidate.md` §2.2

## DB-D004 — core.db / private.db

- **Status**: Adopted（R1A v1 → v2 延续）
- **Decision**: 物理分库；公开 schema（identity/market data/events/ops）入 core.db；持仓/成本/账户/自选/投资逻辑/私人分析/告警入 private.db；跨库引用式关联（UID）+ ATTACH 只读 join。
- **Rationale**: 隐私物理隔离；core 可整体导出。
- **Files**: `storage_architecture_v1.md` §2；`storage_architecture_v2_freeze_candidate.md` §2

## DB-D005 — Watchlist XOR

- **Status**: Adopted（R1A.1 新增，B4）
- **Decision**: `watchlist_items` 支持 `entity_uid` 或 `instrument_uid`，**恰好一个非 NULL**（CHECK XOR）；分别用 partial unique 防 entity duplicate / instrument duplicate。
- **Rationale**: 关注"公司" vs 关注"工具"语义互斥，避免重复与歧义。
- **Files**: `database_schema_design_v2_freeze_candidate.md` §2.4

## DB-D006 — Accounts as Core

- **Status**: Adopted（R1A.1 新增，B5；v1 为 Deferred）
- **Decision**: `accounts` 从 Deferred 提升为 private.db Core：account_id/account_uid/account_name/broker/account_type/base_currency/status/created_at/updated_at。**不保存 password/token。**
- **Rationale**: positions 需要账户级约束（多账户）；凭据属外部系统。
- **Files**: `database_schema_design_v2_freeze_candidate.md` §2.1

## DB-D007 — Position snapshot

- **Status**: Adopted（R1A v1 → v2 延续 + 修正）
- **Decision**: positions = SNAPSHOT（一行=当前状态）；`account_id NOT NULL FK` + `instrument_uid NOT NULL`；OPEN unique 重设计为 `UNIQUE(account_id, instrument_uid) WHERE status='OPEN'`；transactions 仍 Deferred。
- **Rationale**: 多账户下 OPEN 唯一性需要账户级约束；snapshot 语义不变。
- **Files**: `database_schema_design_v2_freeze_candidate.md` §2.2

## DB-D008 — Generic vs private analysis

- **Status**: Adopted（R1A.1 新增，B7）
- **Decision**: core.db `event_analysis` 仅 generic market/event analysis（**不得含 thesis_id/私人持仓/portfolio relevance**）；private.db 新增 `event_thesis_analysis`（event↔thesis：impact_direction/severity/reasoning/invalidate_triggered/recommended_attention/model+prompt+analysis version/raw_output）。
- **Rationale**: 私人投资逻辑不得进入 public schema；事实、通用判断、私人判断三层分离。
- **Files**: `database_schema_design_v2_freeze_candidate.md` §1.16/§2.6

## DB-D009 — Dataset-specific source priority

- **Status**: Adopted（R1A.1 新增，B9）
- **Decision**: 新增 `dataset_sources`（dataset_id + source_id + priority_role=PRIMARY/FALLBACK/ARCHIVE）；**删除 data_sources.priority 的 canonical 含义**。示例：CN_EQUITY_DAILY→TUSHARE PRIMARY/FMP FALLBACK；US_EQUITY_DAILY→FMP PRIMARY/ALPHA_VANTAGE FALLBACK；US_FILINGS→SEC PRIMARY。
- **Rationale**: 优先级必须按数据集定义，全局数值优先级语义模糊。
- **Files**: `database_schema_design_v2_freeze_candidate.md` §1.7
- **Extended by**: DB-D018（单真源：datasets.primary_source_id 移除）、DB-D019（priority_rank 顺序）——原决策文字不改写。

## DB-D010 — Multi-entity events

- **Status**: Adopted（R1A.1 新增，B10）
- **Decision**: 新增 `event_entities` / `event_instruments`（role ∈ PRIMARY/ACQUIRER/TARGET/ISSUER/AFFECTED/RELATED）；`events` 不再设单一 entity_id/instrument_id 列。
- **Rationale**: 并购、回购、监管等事件天然多主体；单一主体列是错误假设。
- **Files**: `database_schema_design_v2_freeze_candidate.md` §1.12–1.14

## DB-D011 — Event evidence

- **Status**: Adopted（R1A.1 新增，B11）
- **Decision**: 新增 `event_evidence`：evidence_uid、event_uid、source_id、evidence_type（HKEX_FILING/SEC_FILING/COMPANY_IR/NEWS/API_PAYLOAD/MANUAL/OTHER）、source_reference、published_at、detected_at、content_hash、is_primary、metadata；`UNIQUE(event_id, content_hash)` 去重 + partial unique 单主证据。
- **Rationale**: 一个 normalized event 对应多源原始证据；证据可追溯、可去重。
- **Files**: `database_schema_design_v2_freeze_candidate.md` §1.15

## DB-D012 — Raw artifact lineage

- **Status**: Adopted（R1A.1 新增，B12/B13）
- **Decision**: `raw_artifacts` 从 Deferred 提升为 R1 Core（artifact_id/artifact_uid/dataset_id/source_id/run_id/artifact_type/local_path_or_reference/content_hash/retrieved_at/metadata）；`market_prices_daily` 增加 `ingest_run_id`（必填）+ `raw_artifact_id`（可选）。
- **Rationale**: canonical 数据必须可追溯到下载/原始证据；每行行情可回答"哪次 ingest、哪个 source、哪个 artifact"。
- **Files**: `database_schema_design_v2_freeze_candidate.md` §1.9/§1.11

## DB-D013 — SQLite / Parquet / DuckDB

- **Status**: Adopted（R1A v1 → v2 延续）
- **Decision**: SQLite = R1 唯一 operational 实施层；Parquet = 未来 bulk 归档（Deferred）；DuckDB = 未来分析层（Deferred）；单向归档、单一真源。
- **Rationale**: 单机个人负载 SQLite 足够；Parquet/DuckDB 无当前驱动。
- **Files**: `storage_architecture_v1.md` §1；`storage_architecture_v2_freeze_candidate.md` §1

## DB-D014 — Financial facts long-form

- **Status**: Adopted（R1A v1 → v2 延续；Deferred）
- **Decision**: financial_reports 头 + financial_facts 行（metric_key 受控字典 + original_metric_name），支持 GAAP/IFRS/non-GAAP、restatement、多 provider。R1 不实施。
- **Rationale**: 避免 provider 专属宽表；等 FMP/SEC 接入后升级。
- **Files**: `core_domain_model_v1.md` §3.2；`database_schema_design_v1.md` §2

## DB-D015 — Dividend Dashboard prototype status

- **Status**: Recorded（R1A.1 收编，不决定归属）
- **Decision**: 根目录存在 Dividend / Quality Screener Dashboard Prototype（`index.html` + `chart.umd.min.js` + `data/dashboard_data.js` + `Test1`）：**当前存在、尚未接入 canonical DB、不属于 R1 Core implementation**；本轮不删除、不扩展、不迁移；后续另开任务决定正式归属（候选：R8 Historical Intelligence 或 R9 Quant / Analytics Layer）。
- **Rationale**: 该 prototype 未经治理进入 main；本轮只识别、记录、收编，避免 Recovery 任务变成 frontend refactor。
- **Files**: `docs/prototypes/dividend_dashboard_status_v1.md`；`PROJECT_STATUS.md`

## DB-D016 — Dashboard prototype relocation & Test1 cleanup（2026-08-22 执行）

- **Status**: Executed（Berlin 授权 cleanup）
- **Decision**: `Test1`（测试残留）删除；dashboard 三文件（`index.html` / `chart.umd.min.js` / `data/dashboard_data.js`）从根目录迁移至 `prototypes/dividend_dashboard/`（git mv 保留历史；`data/dashboard_data.js` 随 index.html 进入 `prototypes/dividend_dashboard/data/`，相对引用不变）。
- **Rationale**: R1A.1 后 Berlin 批准独立 cleanup；与 `docs/prototypes/` 治理归类一致；不扩展、不重构 dashboard 功能。
- **Files**: `docs/prototypes/dividend_dashboard_status_v1.md`（已同步更新）

## DB-D017 — Instrument symbol is not identity（R1A.2，F1）

- **Status**: Adopted（2026-08-22）
- **Decision**: 取消 `UNIQUE(instrument_type, primary_symbol, exchange_code)`；`primary_symbol` 仅为当前展示/便利字段；真正身份由 `instrument_uid` 承担；ticker 历史唯一性只由 `instrument_identifiers`（valid_from/valid_to + partial unique）控制。
- **Rationale**: ticker 可被历史重用（Company A ABC@XNAS 2020 delisted → Company B ABC@XNAS 2025 listed）；符号组合不能是身份约束。
- **Consequences**: instruments 表允许多行同 symbol 不同 instrument_uid；查询须经 instrument_identifiers 或 uid，不得用 symbol 当唯一键。
- **Files**: `database_schema_design_v2_freeze_candidate.md` §1.3；`data_dictionary_v2_freeze_candidate.md` §1.3
- **Date**: 2026-08-22

## DB-D018 — Dataset source single source of truth（R1A.2，F2）

- **Status**: Adopted（2026-08-22）
- **Decision**: 从 v2 设计删除 `datasets.primary_source_id`；哪个 provider 是主源，只能由 `dataset_sources` 决定（datasets → dataset_sources → data_sources）。
- **Rationale**: `datasets.primary_source_id` 与 `dataset_sources.role='PRIMARY'` 并存构成双 source-of-truth，数据库无法判断听谁的。
- **Consequences**: 任何“主源”查询必须走 dataset_sources；datasets 不再承载主源字段。
- **Files**: `database_schema_design_v2_freeze_candidate.md` §1.6；`data_dictionary_v2_freeze_candidate.md` §1.6
- **Date**: 2026-08-22

## DB-D019 — Dataset source ordering（R1A.2，F4）

- **Status**: Adopted（2026-08-22）
- **Decision**: `dataset_sources` 增加 `priority_rank INTEGER NOT NULL`（数字越小越优先）；`UNIQUE(dataset_id, priority_rank)`；保留 `UNIQUE(dataset_id, source_id)`；额外 partial unique `UNIQUE(dataset_id) WHERE role='PRIMARY' AND is_active=1`（每个 dataset 至多一个 active PRIMARY）。
- **Rationale**: 仅 role 无法表达多个 FALLBACK 的顺序（FMP/AlphaVantage/Yahoo 谁先）。
- **Consequences**: 优先级由 role + priority_rank 联合决定；写入层负责 rank 维护。
- **Files**: `database_schema_design_v2_freeze_candidate.md` §1.7；`data_dictionary_v2_freeze_candidate.md` §1.7
- **Date**: 2026-08-22

## DB-D020 — Artifact hash vs provenance identity（R1A.2，F5）

- **Status**: Adopted（2026-08-22）
- **Decision**: `raw_artifacts` 取消 `UNIQUE(content_hash)`，改普通 `INDEX(content_hash)`；防同 run 内重复用 `UNIQUE(run_id, content_hash) WHERE run_id IS NOT NULL`。
- **Rationale**: 同一文件可能在不同时间/不同 provider/不同 run 重复抓取，这些 provenance 都有意义；hash 是内容身份/dedup detection，不等于 provenance record identity。
- **Consequences**: 相同 hash 可多次登记（不同 run/source）；内容去重在查询层判断。
- **Files**: `database_schema_design_v2_freeze_candidate.md` §1.9；`data_dictionary_v2_freeze_candidate.md` §1.9
- **Date**: 2026-08-22

## DB-D021 — Event evidence provenance uniqueness（R1A.2，F6）

- **Status**: Adopted（2026-08-22）
- **Decision**: `event_evidence` 唯一性改为 `UNIQUE(event_id, source_id, source_reference)`（source-level evidence identity）+ `INDEX(content_hash)`；保留 partial `UNIQUE(event_id) WHERE is_primary=1`。source_reference 可 NULL；若需同 (event_id, source_id) 多条 NULL ref 证据，R1B 可加 `evidence_key`。
- **Rationale**: 不同 source 提供相同内容（Tencent IR PDF vs HKEX PDF）本身就是 provenance，不得用 event_id+content_hash 丢弃。
- **Consequences**: 同内容多源证据可共存；内容相同性检测走 content_hash 索引。
- **Files**: `database_schema_design_v2_freeze_candidate.md` §1.15；`data_dictionary_v2_freeze_candidate.md` §1.15
- **Date**: 2026-08-22

## DB-D022 — Event discovery source semantics（R1A.2，F7）

- **Status**: Adopted（2026-08-22，Option B）
- **Decision**: `events.source_id` 更名为 `discovered_by_source_id`，语义 = **第一次让系统创建 normalized event 的 source（detection provenance）**；不是 primary evidence、不是 canonical truth source；事件真实来源由 `event_evidence` 表达。
- **Rationale**: future event dedupe 时知道“谁最先发现”有价值；消除 primary/first/canonical/ingest 语义歧义。
- **Consequences**: events 表只记录发现来源；证据链统一走 event_evidence。
- **Files**: `database_schema_design_v2_freeze_candidate.md` §1.12；`data_dictionary_v2_freeze_candidate.md` §1.12；`core_domain_model_v2_freeze_candidate.md` §3.4
- **Date**: 2026-08-22

## DB-D023 — Account type normalization（R1A.2，F8A）

- **Status**: Adopted（2026-08-22）
- **Decision**: `accounts.account_type IN ('CASH','MARGIN','RETIREMENT','PAPER','OTHER')`；broker 名（IBKR 等）只进 `broker` 字段。
- **Rationale**: IBKR/BROKER 不是 account type（是 broker），原枚举语义污染；不做全球全类型大枚举。
- **Consequences**: 示例 broker='IBKR' + account_type='MARGIN'；type 与 broker 解耦。
- **Files**: `database_schema_design_v2_freeze_candidate.md` §2.1；`data_dictionary_v2_freeze_candidate.md` §2.1
- **Date**: 2026-08-22

## DB-D024 — Stable generic analysis UID（R1A.2，F8B）

- **Status**: Adopted（2026-08-22）
- **Decision**: `event_analysis` 新增 `analysis_uid TEXT UNIQUE NOT NULL`（UUIDv4）；`alerts` 新增 `generic_analysis_uid TEXT NULL` 跨库引用 `core.event_analysis.analysis_uid`；业务 UNIQUE `(event_id, model_provider, model_id, prompt_version, analysis_version)` 保留防重复。
- **Rationale**: future private.alerts 需精确跨库引用“哪一次 generic analysis 触发了 alert”；analysis_uid 负责稳定跨库 identity，业务 unique 负责防重复，两角色不混淆。
- **Consequences**: alert 可按类型关联 event_uid / generic_analysis_uid / thesis_analysis_id 之一或多个；非所有 alert 都需要 generic_analysis_uid。
- **Files**: `database_schema_design_v2_freeze_candidate.md` §1.16/§2.7；`data_dictionary_v2_freeze_candidate.md` §1.16/§2.7；`storage_architecture_v2_freeze_candidate.md` §2.2
- **Date**: 2026-08-22
