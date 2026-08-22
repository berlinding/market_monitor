# Database Design Decisions v1

> Market Monitor 数据库设计决策登记表（Decision Register）
> 日期：2026-08-22 ｜ **Status: FROZEN — Berlin Approved（2026-08-22）**
>
> R1A v2 was approved and frozen by Berlin on 2026-08-22.
> Subsequent schema changes require a new design decision and explicit schema revision.
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

## DB-D025 — R1A v2 frozen（R1B 启动批准）

- **Status**: Approved & Frozen（2026-08-22, Berlin）
- **Decision**: R1A v2 Freeze Candidate 正式冻结；7 份文档状态更新为 FROZEN — Berlin Approved（Freeze Date 2026-08-22）；文件名保留 freeze_candidate（历史命名，不 rename）。后续 schema 变更需新 design decision + 明确 schema revision。
- **Rationale**: Berlin 完成最终审查，批准进入 R1B。
- **Consequences**: 冻结后不静默改设计；发现实施冲突 → 标记 R1B Implementation Conflict + 最小 amendment，不自行突破 Freeze。
- **Files**: 7 份 v2 文档头部
- **Date**: 2026-08-22

## DB-D026 — Relation correction mutability（R1B）

- **Status**: Adopted（2026-08-22）
- **Decision**: `event_entities` / `event_instruments` 定为 **CONTROLLED MUTABLE RELATION TABLE**：纠错方式 = DELETE incorrect relation + INSERT corrected relation（或事务内 replace）；**不新增 status / valid_to 字段**。
- **Rationale**: R1 不需要为关系纠错引入 temporal relation history；表结构无 status/valid_to 字段，与文档措辞（append-only + status/valid_to）的残留矛盾消除。
- **Consequences**: 关系纠错走应用层 delete+insert；若未来需要 relation history，再升级 schema（新 decision）。
- **Files**: `database_schema_design_v2_freeze_candidate.md` §1.13/§1.14
- **Date**: 2026-08-22

## DB-D027 — Application-generated UTC timestamps（R1B）

- **Status**: Adopted（2026-08-22）
- **Decision**: 所有 canonical timestamps（created_at/updated_at/detected_at/retrieved_at/ingested_at/applied_at 等）由 **application layer 显式写 UTC ISO-8601**（如 `2026-08-22T02:30:00Z`）；SQLite DDL 中**不使用** `CURRENT_TIMESTAMP` DEFAULT。
- **Rationale**: 避免 `2026-08-22 02:30:00`（SQLite）与 `2026-08-22T02:30:00Z`（Python）两套格式混用；统一格式可审计。
- **Consequences**: DDL 无 timestamp DEFAULT；应用层负责生成；migration runner 的 applied_at 亦由 runner 写入。
- **Files**: `core_schema_v1.sql`；`migration_runner_spec_v1.md` §4.1
- **Date**: 2026-08-22

## DB-D028 — JSON validation at application layer（R1B）

- **Status**: Adopted（2026-08-22）
- **Decision**: JSON 字段（metadata/raw_output/key_metrics/key_catalysts/key_risks/bullish_points/bearish_points）以 TEXT 存储；**不硬依赖 SQLite JSON1 `json_valid()`** 做 schema 级 CHECK；JSON 合法性校验在 application layer。
- **Rationale**: 不同 SQLite build 的 JSON1 可用性不一致；不强依赖 extension 保证 schema 可移植。
- **Consequences**: schema 无 JSON CHECK；写入前应用层 json.loads 验证。
- **Files**: `core_schema_v1.sql`；`private_schema_v1.sql`；`r1b_ddl_review_v1.md` B8
- **Date**: 2026-08-22

## DB-D029 — Migration files as canonical executable schema source（R1B）

- **Status**: Adopted（2026-08-22）
- **Decision**: **Migration files are canonical executable source**（`docs/database/sql/migrations/core/C0001_*.sql` / `private/P0001_*.sql`）；consolidated schema（`core_schema_v1.sql` / `private_schema_v1.sql`）为 **review snapshot**，由 migration 生成/核对，不反向编辑。
- **Rationale**: 避免 duplicate maintenance 导致两处漂移；执行以 migration 为准。
- **Consequences**: 改 schema = 写新 migration；snapshot 需再生成/核对。
- **Files**: `migration_runner_spec_v1.md` §2；两个 SQL 文件头注
- **Date**: 2026-08-22

## DB-D030 — Separate core/private migration histories（R1B）

- **Status**: Adopted（2026-08-22）
- **Decision**: core.db 与 private.db 各自独立 `schema_migrations` 与独立 migration 序号（core=C0001...；private=P0001...），runner 分开运行。
- **Rationale**: 两库生命周期独立（private 可能加密/独立备份）；不共用一个隐式 migration state。
- **Consequences**: runner 支持 `--db core` / `--db private` / `--db all`；两库可不同步处于不同 version。
- **Files**: `migration_runner_spec_v1.md` §2/§4.7；两 schema 的 schema_migrations
- **Date**: 2026-08-22

## DB-D031 — Controlled market price upsert（R1B）

- **Status**: Adopted（2026-08-22）
- **Decision**: R1 采用 **CONTROLLED UPSERT**：更新 canonical bar 时保留稳定 `bar_id`，更新 OHLCV/turnover、`ingest_run_id`、`raw_artifact_id`、`ingested_at`。**不允许不同 source 相互覆盖**——不同 source 保留独立 row（UNIQUE(instrument_id, trade_date, adjustment_type, source_id) 已含 source_id）。
- **Rationale**: raw_artifacts 已保存原始输入，无需现在增加 price_revisions 表；upsert 覆盖条件 = same source + same instrument + same date + same adjustment_type 且新 run 通过 validation。
- **Consequences**: 同一 (instrument, date, adjustment, source) 仅一行；跨 source 并存；未来如需严格版本化再加 price_revisions（新 decision）。
- **Files**: `core_schema_v1.sql` §11；`legacy_daily_bars_migration_spec_v1.md` M6
- **Date**: 2026-08-22

## DB-D032 — Event evidence implementation key（R1B，方案 B）

- **Status**: Adopted（2026-08-22）
- **Decision**: `event_evidence` 增加 `evidence_key TEXT NOT NULL`，业务唯一 `UNIQUE(event_id, evidence_key)`（替代 R1A.2 F6 的 `UNIQUE(event_id, source_id, source_reference)` 因 source_reference 可 NULL 的歧义）；`source_reference` 保持可 NULL。
- **Rationale**: evidence 可来自 API payload / 手工 / 本地文件，不一定有天然 URL；evidence_key 提供确定性业务去重键。
- **Consequences**: evidence_key 生成规则 = provider native ID → normalized URL/ref → artifact_uid → content-derived fallback（**不用随机 UUID 做业务 dedup key**）；同内容不同 source 仍可共存（content_hash 索引判断内容相同性）。
- **Files**: `core_schema_v1.sql` §15；`r1b_ddl_review_v1.md` B18
- **Date**: 2026-08-22

## DB-D033 — Legacy dual-write retirement gate（R1B）

- **Status**: Adopted（2026-08-22，policy）
- **Decision**: Legacy daily_bars 双写观察期 = **至少 20 个交易日，且不少于 30 个 calendar days，取较晚者**；停止 legacy write 需满足 6 条件（validation 100% pass / dual-write pass / no unresolved gaps / raw backup verified / rollback tested / Berlin explicit approval）。
- **Rationale**: 日历天数不足以覆盖节假日聚集；交易日数保证跨市场结构验证。
- **Consequences**: 即使停止，legacy raw snapshot 永久保留；原 market.db 删除须另行授权。
- **Files**: `legacy_daily_bars_migration_spec_v1.md` §11/§12
- **Date**: 2026-08-22

## DB-D034 — Migration transaction atomicity（R1B.1，S1）

- **Status**: Adopted（2026-08-22）
- **Decision**: migration 事务契约——`BEGIN IMMEDIATE;` 作为 executescript 脚本前缀进入同一脚本；migration 文件本身**不含 COMMIT**（C0001/P0001 已复核）；DDL 成功后事务保持 open；schema_migrations record 用 parameterized `execute()` 在**同一事务**写入；应用层 `conn.commit()` 为唯一提交点；任何异常 `conn.rollback()`，回滚后验证无 record、无部分 schema。
- **Alternatives**: 简单 `conn.execute("BEGIN") + executescript` 不成立（executescript 自带隐式提交语义）；文件内写 COMMIT 会导致 DDL 中途提交、record 脱离事务。
- **Rationale**: Python stdlib sqlite3.executescript() 的事务行为必须被显式控制，不能假定自动原子。
- **Consequences**: runner 实现必须遵循 §4.2.1 契约；测试 T-RUNNER-ATOMIC-01/02/03 验证。
- **Affected Files**: `migration_runner_spec_v1.md` §4.2.1/§4.3
- **Date**: 2026-08-22

## DB-D035 — Legacy timestamp timezone conversion（R1B.1，S2）

- **Status**: Adopted（2026-08-22）
- **Decision**: legacy `fetch_log.fetched_at` 由 `fetch_daily.py` 的 `datetime.now().isoformat(timespec="seconds")` 生成 = **naive local time，非 UTC**；严禁直接加 Z。规则：原始值 `legacy_fetched_at_raw` 永久保留；R1C 前必须 CONFIRMED legacy host timezone（交叉验证系统配置/日志/Git-cron 时间/Berlin 已知时区）；确认 Asia/Shanghai 则 `2026-08-16T23:39:29` → `2026-08-16T15:39:29Z`；无法证明 → `timestamp_resolution_status=UNRESOLVED`，**暂停 ingest_run 转换并等待 Berlin 决定**（migration abort/gate 条件）。
- **Alternatives**: 直接把 naive 时间当 UTC（拒绝——伪造时区）；假定当前机器时区等于历史时区（拒绝——不可靠）。
- **Rationale**: 时区错误会导致 ingest_run 时间错位，破坏 lineage 审计。
- **Consequences**: M5/M7-V9 增加时区状态检查；abort 条件新增 #10。
- **Affected Files**: `legacy_daily_bars_migration_spec_v1.md` §7.1/§9/§10
- **Date**: 2026-08-22

## DB-D036 — Source-safe event evidence uniqueness（R1B.1，S3；extends DB-D032）

- **Status**: Adopted（2026-08-22）
- **Decision**: `event_evidence` 业务唯一键从 `UNIQUE(event_id, evidence_key)` 改为 **`UNIQUE(event_id, source_id, evidence_key)`**；`content_hash` 保持 INDEX（不 UNIQUE）。evidence_key 只需在**单个 source namespace 内**稳定确定（生成顺序不变：provider native ID → normalized URL/ref → artifact_uid → content-derived fallback）；不强制 `source_code:evidence_key` 前缀（source_id 已进入唯一键，避免 namespace 重复编码）。
- **Alternatives**: `UNIQUE(event_id, evidence_key)`（拒绝——不同 source 的相同 native ID 会 namespace collision）；`evidence_key = source_code:...` 拼接（拒绝——冗余编码）。
- **Rationale**: HKEX native:12345 与 Reuters native:12345 在同一 event 下必须共存；同 (event_id, source_id, evidence_key) 重复应拒绝。
- **Consequences**: C0001（canonical）+ core_schema_v1.sql（snapshot）同步修改；测试 T-EVIDENCE-01/02。
- **Affected Files**: `sql/migrations/core/C0001_initial_core_schema.sql`；`sql/core_schema_v1.sql`
- **Date**: 2026-08-22

## DB-D037 — Strict migration mapping gate（R1B.1，S4）

- **Status**: Adopted（2026-08-22）
- **Decision**: 第一次 canonical migration 要求 **100% instrument mapping**：legacy distinct ts_code（当前 5,546）== mapped instrument count 完全一致，才允许进入 M5/M6。stock_basic missing / duplicate mapping / ambiguous mapping / unknown exchange → **ABORT BEFORE BAR COPY**（data_gaps 只记录诊断，不代表可带未映射 instrument 继续）。交易所 suffix 支持：legacy 实际出现 `.SH/.SZ/.BJ`（北交所存在），M0 必须枚举实际 suffix 并校验 deterministic MIC mapping（XSHG/XSHE/XBSE），未知 suffix → ABORT。
- **Alternatives**: “缺失公司 → data_gaps，不阻塞迁移”（拒绝——与 abort 规则冲突，且 canonical 完整性要求 100% 映射）。
- **Rationale**: 统一 M3/M4/Abort 两套矛盾规则；首迁必须完整，缺失映射会在 canonical 留下孤儿/缺口。
- **Consequences**: M3/M4/M7-V3/abort #1/#9 更新；测试 T-MAPPING-01。
- **Affected Files**: `legacy_daily_bars_migration_spec_v1.md` §5/§6/§9/§10
- **Date**: 2026-08-22

## DB-D038 — Logical SQLite backup validation（R1B.1，S5）

- **Status**: Adopted（2026-08-22）
- **Decision**: 区分两种备份类型——**Type A（byte-for-byte frozen copy）**：仅当 legacy writer 已停止且 WAL 已安全处理才要求 `source_sha256 == backup_sha256`；**Type B（SQLite logical backup，`sqlite3.Connection.backup()`，默认采用）**：分别记录 `source_file_hash` 与 `backup_file_hash`，不要求相等；Type B 验证 = `PRAGMA integrity_check==ok` + schema equality + row count equality + trade_date distribution equality + distinct ts_code equality + SUM/aggregate reconciliation。raw_artifact 的 `content_hash` = **backup artifact 文件自己的 SHA-256**（不是 source file hash）；migration report 记录 legacy_source_hash / backup_artifact_hash / backup_method / backup_validation_result。M1 backup gate：backup created + integrity PASS + logical reconciliation PASS + hash recorded，否则 ABORT。
- **Alternatives**: 要求 logical backup 字节与源相同（拒绝——过强且错误，SQLite 逻辑备份字节不必相同）。
- **Rationale**: provenance 更清晰：备份产物自己的 hash 才是其永久身份。
- **Consequences**: M1 重写（Type A/B、gate）、M7-V10、M9 gate 更新；测试 T-BACKUP-01。
- **Affected Files**: `legacy_daily_bars_migration_spec_v1.md` §3/§9/§12
- **Date**: 2026-08-22

## DB-D039 — Dynamic migration-time baseline（R1C Phase 0，P0-1）

- **Status**: Adopted（2026-08-22）
- **Decision**: legacy 迁移区分 **documented_baseline**（2026-08-22 快照：16,620 行 / 3 日 / 5,546 标的）与 **migration_time_baseline**（M0 执行时实测）。M0 产出 Migration Baseline Manifest（captured_at/source_path/source_sha256/file_size/mtime/row_count/trade_date_distribution/distinct_ts_code/fetch_log_count/latest_fetch_time_raw/ts_code_suffixes）；后续 M1–M7 全部以 manifest 为准。**禁止** `COUNT(*) == 16,620` 式永久硬编码 abort 条件；数据增长不是错误。
- **Alternatives**: 把 16,620 写成固定 invariant（拒绝——未来 cron 新增交易日后迁移会假失败）。
- **Rationale**: 迁移正确性 = 一致性（manifest 与数据一致），不是与历史快照相等。
- **Consequences**: M0 重写；V1/V3 等校验引用 manifest；测试 T-BASELINE-01。
- **Affected Files**: `legacy_daily_bars_migration_spec_v1.md` §0/§2；`scripts/legacy_migration_utils.py` capture_baseline
- **Date**: 2026-08-22

## DB-D040 — Frozen snapshot as migration source of truth（R1C Phase 0，P0-3）

- **Status**: Adopted（2026-08-22）
- **Decision**: live `data/market.db` 只用于 M0 preflight + M1 创建 consistent logical backup；M1 validation PASS 后得到 `frozen_legacy_snapshot`，**M2B–M7 所有历史迁移读取只来自 frozen snapshot**（`migration_source_path` / `migration_source_hash` 固定）。禁止 M6 再从 live 读 daily_bars。live 在迁移期间的新增数据不影响本轮 historical migration（属后续 pipeline / dual-write）。
- **Alternatives**: 从 live 直接读（拒绝——迁移中途 live 变化会破坏 raw_artifact↔canonical 血缘一致性）。
- **Rationale**: 保证 raw_artifact → canonical data 血缘真实成立。
- **Consequences**: M6 SQL 用 `ATTACH <frozen_snapshot> AS legacy` 只读；测试 T-FROZEN-SOURCE-01（mutate live 后迁移仍只含 snapshot 数据）。
- **Affected Files**: `legacy_daily_bars_migration_spec_v1.md` §1/§3/§6/§8；`scripts/legacy_migration_utils.py`
- **Date**: 2026-08-22

## DB-D041 — Migration phase ordering / raw artifact registration（R1C Phase 0，P0-2）

- **Status**: Adopted（2026-08-22）
- **Decision**: 迁移阶段重排为 M0（Live Preflight）→ M1（Create & Validate Frozen Snapshot）→ M2（Bootstrap Source/Dataset）→ **M2B（Register Frozen Snapshot as raw_artifact）** → M3（Entity/Instrument）→ M4（Identifier Mapping）→ M5（Ingest Run Backfill）→ M6（Bar Copy from frozen）→ M7（Validation）→ M8/M9。不变量：backup creation/validation 不依赖 core metadata；raw_artifact 登记在 source/dataset 存在后。
- **Alternatives**: 原 M1 同时备份+登记 raw_artifact（拒绝——dataset/source 未建，循环依赖）。
- **Rationale**: 消除 raw_artifact registration 对 M2 元数据的循环依赖。
- **Consequences**: legacy spec §1 总览与 §3/§4/§4B 更新。
- **Affected Files**: `legacy_daily_bars_migration_spec_v1.md` §1–§4B
- **Date**: 2026-08-22

## DB-D042 — Temp-only R1C Phase 1 execution boundary（R1C Phase 1）

- **Status**: Adopted（2026-08-22）
- **Decision**: 第一次真实执行 SQL（C0001/P0001、constraint/runner/legacy fixture 测试）**只允许在 disposable temp database**（tempfile / tests tmp），测试结束自动删除。真实 core.db/private.db 创建、真实 legacy 迁移、stock_basic 下载均属 R1C Phase 2，需 Berlin 再批准。
- **Alternatives**: 直接在真实路径执行（拒绝——违反“第一次执行只能在 disposable temp DB”原则）。
- **Rationale**: 第一次失败不得污染任何真实数据。
- **Consequences**: 测试套件全部用 tempfile.TemporaryDirectory()；测试后清理验证。
- **Affected Files**: `tests/*.py`；`r1c_phase1_review_v1.md`
- **Date**: 2026-08-22

## DB-D043 — Production-path write guard（R1C Phase 1）

- **Status**: Adopted（2026-08-22）
- **Decision**: `scripts/migrate.py` 设 `PRODUCTION_WRITES_ENABLED = False`；若 db-path resolve 到 `<repo>/data/runtime/core.db` 或 `<repo>/data/private/private.db`，即使无 --plan 也抛 `ProductionWriteNotAuthorizedError`。本轮只允许 tempfile / 显式 non-production path。
- **Alternatives**: 提供 `--allow-production` 开关（拒绝——可被轻易误开，违背本轮安全目标）。
- **Rationale**: OpenClaw 本轮不可能误建真实数据库。
- **Consequences**: runner 生产路径保护 + 测试 test_production_core/private_path_refused。
- **Affected Files**: `scripts/migrate.py`；`tests/test_migration_runner.py`
- **Date**: 2026-08-22

## DB-D044 — Migration runner implementation contract（R1C Phase 1）

- **Status**: Adopted（2026-08-22）
- **Decision**: runner 实现遵循 DB-D034 事务契约 + DB-D029/D030（migration=canonical source；core/private 分历史）+ checksum 硬校验（MigrationChecksumError）+ 预检（文件名 C/P+4 位序号+snake、连续性、文件内禁 BEGIN/COMMIT/ROLLBACK，SQL-token-aware 去注释检测）+ schema_migrations bootstrap 单一 DDL（runner 与 C0001/P0001 一致，测试确认）+ plan/status 模式只读不建库 + backup gate。
- **Alternatives**: 引入 Alembic/SQLAlchemy（拒绝——项目零第三方依赖原则）。
- **Rationale**: 可审计、幂等、可回滚；与规格逐条对应。
- **Consequences**: `scripts/migrate.py` + 6 个测试套件；Ran 62 tests OK。
- **Affected Files**: `scripts/migrate.py`；`scripts/timestamp_utils.py`；`scripts/db_validators.py`；`scripts/legacy_migration_utils.py`；`tests/*`
- **Date**: 2026-08-22

## DB-D045 — Frozen snapshot owns authoritative migration baseline（R1C Phase 1.1，H1）

- **Status**: Adopted（2026-08-22）
- **Decision**: live `data/market.db` 只负责 health/readability preflight（`inspect_live_source_health`：file exists / readable / tables / columns / quick_check / observed hash，仅审计）与生成 snapshot；**authoritative migration baseline 由 frozen snapshot 生成**（`capture_snapshot_baseline`：snapshot_path / snapshot_sha256 / row_count / trade_date_distribution / distinct_ts_code / fetch_log_count / latest_fetch_time_raw / ts_code_suffixes / aggregates）；`validate_snapshot` **不得 reopen live DB**（只验证 snapshot 内部 + manifest 自洽 + hash）。M3–M7 全部使用 snapshot manifest。
- **Alternatives**: 以 live 查询为 baseline（拒绝——并发竞态：row_count/hash/snapshot/aggregate 可能来自不同版本）。
- **Rationale**: 消除 post-backup live 依赖；migration correctness 的 authoritative source 就是 snapshot 本身。
- **Consequences**: 删除 `capture_baseline()`；新增 inspect_live_source_health / capture_snapshot_baseline；T-SNAPSHOT-BASELINE-01 / T-SNAPSHOT-HASH-01；validate_snapshot 不再重开 live。
- **Affected Files**: `scripts/legacy_migration_utils.py`；`tests/test_legacy_migration_fixture.py`；`docs/database/legacy_daily_bars_migration_spec_v1.md` §2/§3.5/§3.6
- **Date**: 2026-08-22

## DB-D046 — stock_basic duplicate identity input is fatal（R1C Phase 1.1，H2）

- **Status**: Adopted（2026-08-22）
- **Decision**: stock_basic 输入在构造 lookup 前显式校验（`validate_stock_basic_input`）：duplicate ts_code → `MappingGateError`（含 offending ts_code，绝不 last/first-one-wins 或 drop_duplicates）；每行必须含 ts_code/name/list_date，缺失/空/畸形 → `MappingGateError`（不创建半完整 identity）。
- **Alternatives**: dict 覆盖（拒绝——静默丢身份）；dup 警告继续（拒绝——违反 strict gate）。
- **Rationale**: identity 输入必须确定性与完整性；否则 canonical 身份可能错误合并。
- **Consequences**: build_ts_code_mapping 首先调用 validate；T-MAPPING-DUPLICATE-01 / T-MAPPING-MISSING-FIELD-01。
- **Affected Files**: `scripts/legacy_migration_utils.py`；`tests/test_legacy_migration_fixture.py`；`docs/database/legacy_daily_bars_migration_spec_v1.md` §5.2
- **Date**: 2026-08-22

## DB-D047 — Migration checksum equals exact raw file SHA-256（R1C Phase 1.1，H3）

- **Status**: Adopted（2026-08-22）
- **Decision**: **migration checksum = SHA-256(exact raw migration file bytes)**，唯一；不对 normalized/decoded-re-encoded/trimmed text 计算。实现：`raw_bytes = path.read_bytes()` → `checksum = sha256_bytes(raw_bytes)`（只算一次）→ `sql = raw_bytes.decode("utf-8")`（仅执行；UnicodeDecodeError → `MigrationFileError`）→ `apply_migration(conn, mid, sql, checksum=checksum, ...)`（apply 不再自行重算）；comparison 与 schema_migrations INSERT 用同一变量。
- **Alternatives**: 对 read_text 后重新 encode 计算（拒绝——Windows CRLF/newline normalization 下与 raw bytes 不一致，导致误判 CHECKSUM_MISMATCH）。
- **Rationale**: checksum 必须反映磁盘上的确切文件；解码仅是执行步骤。
- **Consequences**: T-CHECKSUM-CRLF-01（CRLF APPLIED→SKIP 无 mismatch；tamper → MigrationChecksumError）；T-MIGRATION-ENCODING-01。
- **Affected Files**: `scripts/migrate.py`；`tests/test_migration_runner.py`；`docs/database/migration_runner_spec_v1.md` §4.4
- **Date**: 2026-08-22

## DB-D048 — Reject ambiguous multi-DB path override（R1C Phase 1.1，H4）

- **Status**: Adopted（2026-08-22）
- **Decision**: `--db all` 与 `--db-path` 互斥——`--db all` 同时操作 core/private，单一 db-path 会让两库指向同一文件。runner 在解析后、任何迁移前 `parser.error(...)` 拒绝（SystemExit 2，不创建文件、不执行 migration）。
- **Alternatives**: 引入 --core-db-path/--private-db-path（拒绝——本轮保持简单）；允许同文件（拒绝——C/P 迁移写入同一 DB 是错误配置）。
- **Rationale**: fail-fast 防错误配置。
- **Consequences**: T-CLI-ALL-DBPATH-01（SystemExit 2 + foo.db 不存在）；单库 --db-path 仍可用。
- **Affected Files**: `scripts/migrate.py`；`tests/test_migration_runner.py`；`docs/database/migration_runner_spec_v1.md` §5
- **Date**: 2026-08-22

## DB-D049 — Snapshot manifest contract（R1C Phase 1.1）

- **Status**: Adopted（2026-08-22）
- **Decision**: 定义 snapshot manifest 字段契约：captured_at / snapshot_path / snapshot_sha256 / file_size / row_count / distinct_trade_dates / trade_date_distribution / distinct_ts_code / fetch_log_count / latest_fetch_time_raw / ts_code_suffixes / aggregates。后续 M3–M7 与 V1–V12 全部以该 manifest 为 reconciliation 依据；raw_artifact.content_hash 将来必须使用 snapshot_sha256。
- **Alternatives**: 无固定 manifest 契约（拒绝——各阶段口径漂移）。
- **Rationale**: 单一权威数字来源，杜绝 live/snapshot 混用。
- **Consequences**: T-SNAPSHOT-HASH-01（snapshot_sha256 == sha256(snapshot bytes)）；测试断言 manifest 全字段。
- **Affected Files**: `scripts/legacy_migration_utils.py`；`docs/database/legacy_daily_bars_migration_spec_v1.md` §3.5
- **Date**: 2026-08-22
