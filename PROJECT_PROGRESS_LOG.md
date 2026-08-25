# PROJECT_PROGRESS_LOG.md

## Purpose

记录 Market Monitor 的**项目开发过程**：

- 关键技术决策
- 文件变化
- 架构变化
- 当前任务结果
- 下一步建议

## Append-only Rule

- 历史内容不得改写。
- 若发现历史记录有误，应**追加 correction**，而不是覆盖。

## Reading Rule

- 新的开发任务开始时：默认只读取最后 **5 条**。
- 只有需要追踪历史决策时才搜索更早记录。

---

## 2026-08-17 00:53 — R00 Project Governance System Initialization

### Task

建立轻量、清晰、可长期扩展的项目治理系统：三层信息体系 + 治理三件套 + 入口协议 + 安全边界。

### Files Read

- `AGENTS.md` `HEARTBEAT.md` `IDENTITY.md` `SOUL.md` `USER.md` `TOOLS.md`
- `.gitignore` `scripts/README.md` `scripts/fetch_daily.py`
- 参考项目 `china_ai_risk_exposure`（本地未找到，依据详细规格执行）

### Files Created

- `PROJECT_RULES.md` — 最高层级长期规则
- `PROJECT_STATUS.md` — 当前状态快照
- `PROJECT_PROGRESS_LOG.md` — append-only 开发日志（本文件）
- `README.md` — 根目录人类入口
- `config/` `skills/` `tests/` `docs/` 目录（`.gitkeep` 占位）

### Files Modified

- `AGENTS.md` — 新增 Project Entry Protocol（开发/runtime/历史决策三类入口）
- `HEARTBEAT.md` — 明确为 runtime 监控清单，非开发任务清单
- `.gitignore` — 补充 secrets / 运行数据库 / 私密数据 / 大文件 / runtime 目录等规则

### Key Decisions

1. 建立三层信息体系：Project Governance（如何开发）／ OpenClaw Runtime（每天运行发生什么）／ Application Data（代码+数据库+日志）。
2. 三类日志严格区分：`PROJECT_PROGRESS_LOG.md`（开发过程，append-only）vs `memory/`（runtime 日记）vs `logs/`（程序原始日志）。
3. Python 负责事实与确定性流程（下载/入库/校验），LLM 负责理解与判断（事件重要性/简报/提醒）。
4. 运行数据库（`*.db`）不入 Git：`data/market.db` 由 git 跟踪转为本地保留（`git rm --cached`），本地文件未删除，数据可经 `fetch_daily.py` + Tushare 重新生成。
5. `main` 单分支，正常流程 status→commit→push，不 force push（除非用户明确授权）。
6. 当前阶段禁止真实证券自动交易；外部动作分三级（自主 / 需授权 / 禁止）。

### Outputs

- 治理三件套 + 入口协议 + 安全边界 + README 就位
- `.gitignore` 覆盖 secrets / 数据库 / 私密数据 / runtime

### Not Done

- 未进入 R1 — Core Data Model（及其后任何功能）
- 未做任何 schema 实现、database migration、第三方集成、监控/告警/量化等

### Next Step

- R1 — Core Data Model design（待 Berlin 授权后执行）

---

## 2026-08-17 — R1A Core Domain Model & Data Contract

### Task

R1A：为 Market Monitor 冻结核心领域模型、数据库逻辑结构与数据契约（设计阶段，不实施）。

### Files Read

- `PROJECT_RULES.md` `PROJECT_STATUS.md` `PROJECT_PROGRESS_LOG.md`（前 5 条）`AGENTS.md` `.gitignore`
- `scripts/fetch_daily.py` `scripts/README.md`
- `data/market.db`（只读检查 schema：daily_bars + fetch_log）
- git status/branch/remote/log（main @ 3276e0e，工作树 clean）

### Files Created

- `docs/database/core_domain_model_v1.md` — 六大 Domain + 对象定义 + Mermaid ER Diagram
- `docs/database/database_schema_design_v1.md` — 全部候选表（Core 15 张 + Deferred 7 张）PK/FK/UNIQUE/mutability/public-private
- `docs/database/data_dictionary_v1.md` — 逐表逐字段字典（type/nullable/key/description/example/provenance/privacy/mutability）
- `docs/database/storage_architecture_v1.md` — SQLite/Parquet/DuckDB 分工 + core.db/private.db 物理分库评估
- `docs/database/daily_bars_migration_plan_v1.md` — 5,540 条 daily_bars 未来迁移方案（copy+validate，不执行）
- `docs/database/r1a_schema_review_v1.md` — 设计自审（14 项 Finding）

### Files Modified

- `PROJECT_STATUS.md` — 状态更新为 R1 In Progress，记录 R1A 完成、Blockers 开放问题

### Key Decisions

1. **Entity / Instrument 双层身份模型正式采用**；ticker 不是身份；thesis/watchlist 挂 entity/instrument 不挂 ticker。
2. **identifiers 独立成表**（instrument_identifiers，provider 中立，validity 区间 + partial unique 保证当前映射唯一）。
3. **core.db + private.db 物理分库采纳**：持仓/成本/账户/自选/研究逻辑入 private.db；跨库引用式关联（private 只存 id）+ ATTACH 只读 join；id 唯一真源在 core。
4. **SQLite = operational DB**（R1 唯一实施）；Parquet = 未来 bulk historical 归档；DuckDB = 未来 analytical 查询层（均 Deferred，不迁移）。
5. **positions = snapshot state**（一行=当前状态，OPEN partial unique）；transactions = 未来 canonical ledger（Deferred），建立后 positions 转 derived。
6. **financial facts 采用 long-form 基础模型**（financial_reports 头 + financial_facts 行，Deferred），支持 GAAP/IFRS/non-GAAP、restatement、多 provider。
7. **events 与 event_analysis 严格分离**：events 只存确定性事实（fingerprint 去重），LLM 判断（importance/thesis_impact/points）只进 event_analysis，带 model_id/prompt_version/analysis_version 可复现。
8. **ID 统一 integer surrogate**（SQLite ROWID）+ 业务唯一键；不用 UUID/ULID。
9. **Schema migration 轻量方案**：schema_migrations 表 + 手写 SQL + 纯标准库 Python runner（R1B 实施），不引入 Alembic。
10. **行情单位显式化**：Tushare vol=手(LOTS)、amount=千元(THOUSAND_CNY)，存 provider raw 值不做隐式换算；adjustment_type 显式（RAW/FWD/BWD）。
11. **daily_bars 迁移原则**：copy + validate（V1–V7 清单）+ 30 天双写观察期 + 备份 + Berlin 批准后方可删旧表；不做 destructive rewrite。

### Outputs

- 六份设计文档 + ER Diagram；Core 表 15 张（含 schema_migrations），Deferred 表 7 张
- 自审 14 项 Finding（6 HIGH 全部解决；接受 3 项残余风险：受控 upsert 证据链、positions 过渡语义、跨库引用一致性）

### Not Done

- ❌ 未创建新生产数据库（core.db/private.db 未建）
- ❌ 未迁移/未修改现有 5,540 条 daily_bars，`data/market.db` 原样保留
- ❌ 未修改 `fetch_daily.py` 生产逻辑
- ❌ 未接入 FMP/SEC/OpenBB，未安装任何第三方 Skill
- ❌ 未进入 R1B

### Next Step

- R1B — SQL DDL & Migration Specification（待 Berlin 授权，不自动开始）

---

## 2026-08-17 — Credential Security Rule（API.txt 保密规则确立）

### Task

Berlin 在项目根新增 `API.txt`（含全部 API token，包括 GitHub token），要求更新项目规则确保该文件绝不公开上传。

### Files Read

- `PROJECT_RULES.md` `AGENTS.md` `TOOLS.md` `.gitignore`
- `git ls-files` / `git log --all --name-only` 全历史扫描

### Files Modified

- `PROJECT_RULES.md` — 新增 §4.1「API.txt —— 严格保密文件」铁律（不上传公开互联网、提交前检查、不写入脚本/命令行/日志、读取方式唯一、GitHub token 限用、泄漏立即轮换）
- `AGENTS.md` — 数据源密钥位置注明严格保密
- `TOOLS.md` — 密钥读取位置与保密说明同步

### Key Decisions

1. `API.txt`（`~/API.txt` 或项目根）为严格保密文件，禁止上传任何公开/私有远端仓库与外部服务；token 一旦进 git 历史极难清除。
2. GitHub token 不拼入 remote URL；git push 优先 SSH 密钥（本机 `id_ed25519`，本次 R1A 推送已验证可用）。
3. 提交前检查清单纳入规则：`git status` 无 `API.txt`、`git check-ignore` 生效。
4. 泄漏响应：停止 → 报告 → 轮换 token，不静默处理。

### Verified

- `API.txt` 已被 `.gitignore`（第 7 行 `API.txt` 模式）忽略，未被 git 跟踪；
- 全历史扫描无任何 `API.txt`/token/secret 文件；工作树 clean；
- 文件权限已收紧为 `600`（属主可读）。

### Not Done

- 未读取/未上传/未提交 `API.txt` 内容；未修改 token 本身。

### Next Step

- 后续所有 git 操作遵循新规则（SSH 推送 + 提交前敏感文件检查）。

---

## 2026-08-22 — R1A.1 Recovery, Repository Reconciliation & Schema Freeze Candidate

### Task

恢复项目治理一致性：确认 R1A.1 真实完成状态；处理未纳入治理的 dashboard prototype；完成 R1A v2 Freeze Candidate（7 份文档）。**禁止进入 R1B。**

### Recovery Findings

- **R1A.1 判定：Case C —— 本地与远端均无任何 R1A.1 成果**（无 v2_freeze_candidate / database_design_decisions_v1 / r1a1_schema_review_v2），需要重新生成，无"已完成未 push"或"部分完成"情形。
- R1A（6 份 v1 文档）与 Credential Security 此前已在 GitHub main 完成闭环（本地 73e1f65 为远端 afef354 的祖先，无本地未 push 提交）。

### Repository Drift（首次进入治理）

- `Test1`（21B 测试残留，内容 "This is a test file."）：commit `6b4a7ea`（2026-08-16，Berlin 本人）加入；未纳入任何治理。
- `chart.umd.min.js`（Chart.js UMD）`index.html`（面板前端）`data/dashboard_data.js`（筛选数据）：commit `65e03fb`（2026-08-16）首次加入，`4617a8e`（08-17）与 `afef354`（08-20）更新数据。
- dashboard 生成脚本 `sync_data.py`：**从未提交**（文件头声明存在，全历史 grep 无此文件）；dashboard_data.js 的 generated_at 与 commit 时间一致，说明为手工运行后提交；无定时任务（OpenClaw cron 仅有 daily-download）。
- 数据来源：公开市场数据（港股 ticker/股息率/估值等），**无私人数据**，可在 Git 保留。
- 归属判定：属于 Market Monitor 工作区的独立 prototype（Dividend / Quality Screener Dashboard），**未接入 canonical DB**，不属于 R1 Core implementation。
- 本轮未删除、未移动 dashboard 文件；记录：root-level dashboard prototype requires later structural cleanup（另开任务决定迁移 dashboard/ web/ prototypes/）。

### Schema Corrections（B1–B14 全部落实）

- **B1** Entity identifiers 新增（LEI/SEC_CIK/PROVIDER_COMPANY_ID 属 Entity）
- **B2** entities.canonical_name 去 UNIQUE
- **B3** Stable UID：UUIDv4（stdlib），entity/instrument/event/account/artifact/evidence uid；跨库引用只用 uid（修订 v1 决策 8）
- **B4** Watchlist XOR CHECK + 双 partial unique 防重复
- **B5** accounts 提升 private.db Core（无 password/token）
- **B6** positions：account_id NOT NULL FK + instrument_uid NOT NULL；OPEN unique 账户级重设计
- **B7** event_analysis 收敛 generic（core）+ 新增 event_thesis_analysis（private）
- **B8** alerts 移入 private.db（PRIVATE / RUNTIME USER STATE）
- **B9** 新增 dataset_sources（PRIMARY/FALLBACK/ARCHIVE）；data_sources.priority 弃用 canonical 含义
- **B10** 新增 event_entities / event_instruments（role 枚举）；events 去单一主体列
- **B11** 新增 event_evidence（多源证据，content_hash 去重，is_primary 单主）
- **B12** raw_artifacts 从 Deferred 提升 R1 Core
- **B13** market_prices_daily + ingest_run_id（必填）+ raw_artifact_id（可选）血缘
- **B14** legacy 双完整性：normalized canonical completeness + raw provenance completeness；备份注册 raw_artifact + SHA-256；pre_close/change/pct_chg 不迁移但 raw 可追溯

### Files Created

- `docs/database/core_domain_model_v2_freeze_candidate.md`
- `docs/database/database_schema_design_v2_freeze_candidate.md`
- `docs/database/data_dictionary_v2_freeze_candidate.md`
- `docs/database/storage_architecture_v2_freeze_candidate.md`
- `docs/database/daily_bars_migration_plan_v2_freeze_candidate.md`
- `docs/database/r1a1_schema_review_v2.md`（21 项审查，Blocking findings remaining = 0）
- `docs/database/database_design_decisions_v1.md`（DB-D001–D015）
- `docs/prototypes/dividend_dashboard_status_v1.md`

### Files Modified

- `PROJECT_STATUS.md` — 状态更新：R1A v2 Freeze Candidate 待审查；Existing Prototype 记录；Next = Berlin review；Not Authorized = R1B
- `PROJECT_PROGRESS_LOG.md` — 本记录（append-only）

### Not Done（明确）

- ❌ 未开始 R1B
- ❌ 未创建 core.db / private.db
- ❌ 未迁移 5,540 条 daily_bars
- ❌ 未修改生产行情 pipeline（fetch_daily.py）
- ❌ 未下载真实 stock_basic
- ❌ 未接 FMP / SEC / OpenBB，未安装任何第三方依赖/Skill
- ❌ 未删除 / 未移动 / 未扩展 dashboard prototype
- ❌ 未删除 Test1（建议后续独立 cleanup 任务处理）
- ❌ 未读取 / 未提交 API.txt（`git check-ignore` 确认忽略）

### Next Step

- **Berlin Review of R1A v2 Freeze Candidate**；批准后标记 Frozen 并授权 R1B — SQL DDL & Migration Specification（不自动开始）。

---

## 2026-08-22 — Dashboard Cleanup & Relocation（R1A.1 后续，Berlin 批准）

### Task

执行 R1A.1 报告提出的两项待定 cleanup（Berlin 2026-08-22 授权）：删除 `Test1` 测试残留；dashboard 从根目录迁移至子目录。

### Actions

1. **删除 `Test1`**（git rm，tracked file；内容 "This is a test file."，明确测试残留）。
2. **迁移 dashboard** 至 `prototypes/dividend_dashboard/`（git mv 保留历史）：
   - `index.html` → `prototypes/dividend_dashboard/index.html`
   - `chart.umd.min.js` → `prototypes/dividend_dashboard/chart.umd.min.js`
   - `data/dashboard_data.js` → `prototypes/dividend_dashboard/data/dashboard_data.js`
   - index.html 内相对引用（`src="chart.umd.min.js"` / `src="data/dashboard_data.js"`）保持有效，无需改前端代码。

### Files Modified

- `docs/prototypes/dividend_dashboard_status_v1.md` — 文件清单/风险/治理记录同步（Test1 已删、路径已更新）
- `PROJECT_STATUS.md` — Existing Prototype 位置更新
- `docs/database/database_design_decisions_v1.md` — 追加 DB-D016（relocation & cleanup 决策）
- `PROJECT_PROGRESS_LOG.md` — 本记录（append-only）

### Not Done

- ❌ 未扩展 / 未重构 dashboard 功能
- ❌ 未修改 sync_data.py（仍不在仓库）
- ❌ 未开始 R1B

### Next Step

- 保持 Berlin 审查 R1A v2 Freeze Candidate 的待办不变。

---

## 2026-08-22 — R1A.2 Final Freeze Corrections

### Task

冻结前最后修正：对 R1A v2 Freeze Candidate 做 8 项小范围结构修正（F1–F8），消除剩余歧义，产出 Freeze Readiness: READY FOR BERLIN APPROVAL。**不重新设计、不开始 R1B、不建库。**

### Issues Corrected（F1–F8）

- **F1 Instrument ticker uniqueness**：取消 `UNIQUE(instrument_type, primary_symbol, exchange_code)`；primary_symbol 仅展示/便利字段；ticker 历史唯一性归 instrument_identifiers；明确 ticker is attribute, not identity。
- **F2 Dataset source single source of truth**：删除 `datasets.primary_source_id`；主源只由 `dataset_sources` 决定。
- **F3 Remove global data source priority**：彻底删除 `data_sources.priority`（不再保留废弃字段）。
- **F4 Dataset source fallback ordering**：`dataset_sources` 增加 `priority_rank`（INTEGER，小者优先）+ `UNIQUE(dataset_id, priority_rank)` + partial unique `UNIQUE(dataset_id) WHERE role='PRIMARY' AND is_active=1`（单 active PRIMARY）。
- **F5 Raw artifact hash semantics**：`raw_artifacts` 取消 `UNIQUE(content_hash)` → `INDEX(content_hash)` + `UNIQUE(run_id, content_hash) WHERE run_id IS NOT NULL`；相同内容可在不同 run/source 重复登记。
- **F6 Event evidence provenance semantics**：`event_evidence` 唯一性改 `UNIQUE(event_id, source_id, source_reference)` + `INDEX(content_hash)`；不同 source 相同内容可共存。
- **F7 Event source semantics**：`events.source_id` → **`discovered_by_source_id`**（Option B：detection provenance，非 primary evidence / canonical truth）。
- **F8A Account type normalization**：`account_type IN ('CASH','MARGIN','RETIREMENT','PAPER','OTHER')`，broker 名只进 `broker` 字段。
- **F8B Analysis stable UID**：`event_analysis.analysis_uid TEXT UNIQUE NOT NULL`（UUIDv4）；`alerts.generic_analysis_uid TEXT NULL` 跨库引用；业务 UNIQUE 保留防重复。

### Key Changes

- instrument symbol uniqueness removed（F1）
- datasets.primary_source_id removed（F2）
- data_sources.priority removed（F3）
- dataset_sources priority_rank added（F4）
- artifact hash semantics corrected（F5）
- event evidence uniqueness corrected（F6）
- event source semantics clarified（F7）
- account type corrected（F8A）
- analysis_uid added（F8B）

### Files Modified（直接修改 v2 Freeze Candidate，未新建 v3）

- `docs/database/core_domain_model_v2_freeze_candidate.md`（F1/F2/F3/F4/F7/F8B uid 清单）
- `docs/database/database_schema_design_v2_freeze_candidate.md`（全部 F1–F8B）
- `docs/database/data_dictionary_v2_freeze_candidate.md`（全部 F1–F8B）
- `docs/database/storage_architecture_v2_freeze_candidate.md`（analysis_uid 跨库引用 + priority_rank 血缘链）
- `docs/database/daily_bars_migration_plan_v2_freeze_candidate.md`（V1 基准行数修正为 16,620 = 3 个交易日）
- `docs/database/r1a1_schema_review_v2.md`（追加 R1A.2 Final Freeze Review Addendum F22–F29 + Freeze Readiness Checklist）
- `docs/database/database_design_decisions_v1.md`（追加 DB-D017–D024；DB-D009 加 Extended-by 注释）
- `PROJECT_STATUS.md`（R1A.2 完成状态 + 数据事实修正）

### Not Done（明确）

- ❌ 未创建数据库 / 未写生产 DDL
- ❌ 未迁移 daily_bars（16,620 行 / 3 个交易日全部保留，sha256 未变）
- ❌ 未修改 fetch_daily.py / 生产行情 pipeline
- ❌ 未接 FMP / SEC / OpenBB，未安装 package / Skill
- ❌ 未执行 Parquet / DuckDB
- ❌ 未开始 R1B
- ❌ 未继续开发 dashboard
- ❌ 未读取 / 未提交 API.txt（check-ignore 确认忽略）
- ❌ 未写 FROZEN（保持 FREEZE CANDIDATE）

### Legacy Data 复核

- `data/market.db` 只读验证：daily_bars = **16,620 行**（08-14: 5,540 / 08-17: 5,539 / 08-20: 5,541；distinct ts_code 5,546），fetch_log 3 条，最近抓取 2026-08-20 21:55。早期文档“5,540 条”为 08-14 单日口径；sha256 = `93562960aa...d599004` 与 R1A.1 一致，**未执行任何写入**。

### Next

- **Berlin final review and freeze approval**：审查 R1A v2 Freeze Candidate（Freeze Readiness: READY FOR BERLIN APPROVAL）；批准后标记 FROZEN 并授权 R1B — SQL DDL & Migration Specification（不自动开始）。

---

## 2026-08-22 — R1B SQL DDL & Migration Specification

### Task

Berlin 批准 **R1A v2 = FROZEN**（2026-08-22）并授权 R1B：将冻结设计转换为可审计的 SQLite DDL 与迁移规格。**只写不执行**（不建库、不迁移、不改 legacy、不动 pipeline）。

### R1A Freeze Approval

- 7 份 v2 文档状态更新为 **FROZEN — Berlin Approved（2026-08-22）**，并加注后续 schema 变更需新 decision + 明确修订；文件名保留 freeze_candidate（历史命名，不 rename）。
- 顺手修正两处文档残留：schema design §4 摘要（data_sources.priority 表述 → dataset_sources 单真源）；event_entities/event_instruments mutability（→ CONTROLLED MUTABLE RELATION TABLE，DELETE+INSERT 纠错，无 status/valid_to）。

### Files Created

- `docs/database/sql/core_schema_v1.sql` — core.db 17 表完整 DDL（review snapshot）
- `docs/database/sql/private_schema_v1.sql` — private.db 7 业务表 + schema_migrations（review snapshot）
- `docs/database/sql/migrations/core/C0001_initial_core_schema.sql` — core canonical executable migration
- `docs/database/sql/migrations/private/P0001_initial_private_schema.sql` — private canonical executable migration
- `docs/database/migration_runner_spec_v1.md` — stdlib runner 规格（顺序/事务/checksum/dry-run/backup gate/回滚/core-private 分历史）
- `docs/database/legacy_daily_bars_migration_spec_v1.md` — M0–M9 分阶段迁移规格 + V1–V12 验证 + abort 条件
- `docs/database/r1b_test_plan_v1.md` — T1–T6 测试计划（含 15 个约束案例 + 隐私测试）
- `docs/database/r1b_ddl_review_v1.md` — 18 项自审，Blocking findings = 0

### DDL Summary

- core.db 17 表：entities/entity_identifiers/instruments/instrument_identifiers/data_sources/datasets/dataset_sources/ingest_runs/raw_artifacts/data_gaps/market_prices_daily/events/event_entities/event_instruments/event_evidence/event_analysis/schema_migrations
- private.db 8 表：accounts/positions/watchlists/watchlist_items/investment_theses/event_thesis_analysis/alerts/schema_migrations（独立 P0001... 历史）
- 关键实现决策：UID=application 生成 UUIDv4 + CHECK(length=36)；timestamp/JSON 校验在应用层；跨库引用无伪 FK + 4 个 validator；event_evidence 用 evidence_key（DB-D032 方案 B）；market price CONTROLLED UPSERT（DB-D031）；partial unique 全部实现（current identifier、单 active PRIMARY、run 内 artifact 去重、单 primary evidence、OPEN position、watchlist XOR 去重）。

### Migration Specification

- Runner：stdlib sqlite3，transaction 包裹，schema_migrations 记录，SHA-256 checksum（已执行文件被修改→报错），已执行不重复执行，core/private 分开运行（C0001.../P0001...），dry-run/plan，backup gate，failure rollback。
- Legacy：M0 Preflight → M1 Backup+raw_artifact(SHA-256) → M2 Source/Dataset bootstrap → M3 Entity/Instrument（stock_basic 快照作 input artifact；uid 随机 UUIDv4 非 hash(ts_code)）→ M4 Identifier mapping → M5 Ingest run backfill（fetch_log 3 行一一对应）→ M6 Bar copy（vol→LOTS、amount→THOUSAND_CNY、RAW、CNY；pre_close/change/pct_chg 不入 canonical）→ M7 V1–V12 → M8 dual-write（≥20 trading days 且 ≥30 calendar days 取较晚者）→ M9 retirement gate（6 条件 + Berlin 批准；market.db 删除须另行授权）。

### Test Plan

- T1 schema / T2 15 个约束案例 / T3 runner（顺序/幂等/checksum/回滚/dry-run/分库/backup gate）/ T4 cross-db uid / T5 legacy M0–M9 / T6 privacy（core 导出无持仓/thesis/alert；private 无 token/password）。

### Review Findings

- r1b_ddl_review_v1.md：HIGH 8 / MEDIUM 10 全部 PASS；**Blocking findings = 0**；残余：跨库一致性靠应用层（R2 自动化）、迁移纪律靠 R1C 实现、JSON 校验在应用层。

### Legacy Data Fact

- `data/market.db`：daily_bars = **16,620 行**（2026-08-14: 5,540 / 08-17: 5,539 / 08-20: 5,541），distinct ts_code = 5,546，fetch_log = 3，最近抓取 2026-08-20 21:55；sha256 = `93562960aa...d599004`（与 R1A.1 一致）
- **legacy unchanged = YES**（只读复核，未执行任何写入）

### Decision Register

- 追加 DB-D025（R1A v2 frozen）、DB-D026（relation mutability）、DB-D027（application timestamps）、DB-D028（JSON app 校验）、DB-D029（migration=canonical source）、DB-D030（core/private 分历史）、DB-D031（controlled upsert）、DB-D032（evidence_key 方案 B）、DB-D033（dual-write retirement gate）

### Not Done

- ❌ 未创建 core.db / private.db；未执行任何 SQL
- ❌ 未迁移 16,620 行 daily_bars；未修改 data/market.db
- ❌ 未下载 stock_basic；未接任何 provider
- ❌ 未修改 fetch_daily.py 生产行为；未启用 dual-write
- ❌ 未安装 SQLAlchemy/Alembic/DuckDB/Parquet 依赖
- ❌ 未继续开发 dashboard；无自动交易
- ❌ 未 force push

### Next

- **Berlin review of R1B SQL DDL and Migration Specification**；批准后 R1C — Database Implementation & Legacy Migration Dry Run（不自动开始）。

---

## 2026-08-22 — R1B.1 Implementation Safety Corrections

### Task

修正 R1C 前剩余的工程实施安全问题（S1–S6）。**只修实施安全，不扩大 scope，不执行任何 SQL。**

### Corrections（S1–S6）

- **S1 Migration transaction atomicity**：重写 runner 事务契约（migration_runner_spec §4.2.1）：`BEGIN IMMEDIATE;` 作为 executescript 脚本前缀；migration 文件不含 COMMIT（C0001/P0001 已复核）；record 用 parameterized execute() 同事务写；应用层 commit 唯一提交点；异常 rollback 后验证无 record、无部分 schema。（DB-D034）
- **S2 Legacy timestamp timezone**：确认 `fetch_daily.py:165` 用 `datetime.now().isoformat(timespec="seconds")` → fetched_at 是 **naive local time 非 UTC**；严禁直接加 Z。新规：原始值 legacy_fetched_at_raw 永久保留；R1C 前必须 CONFIRMED 时区；Asia/Shanghai 则正确转换（-8h）；UNRESOLVED → 暂停 ingest_run 转换等待 Berlin（abort/gate #10）。（DB-D035）
- **S3 Event evidence source-safe uniqueness**：`UNIQUE(event_id, evidence_key)` → **`UNIQUE(event_id, source_id, evidence_key)`**（HKEX native:12345 与 Reuters native:12345 可共存）；evidence_key 仅需 source namespace 内稳定；不强制 source_code 前缀；content_hash 保持 INDEX。（DB-D036，extends DB-D032）
- **S4 Strict mapping gate**：统一 M3/M4/Abort 矛盾规则 → **100% instrument mapping required**（legacy distinct ts_code 5,546 == mapped count）；data_gaps 仅诊断；缺失/重复/歧义/未知 exchange → ABORT BEFORE BAR COPY；**legacy 实际 suffix = SH/SZ/BJ（北交所）**，全部纳入 deterministic MIC mapping（XSHG/XSHE/XBSE）。（DB-D037）
- **S5 Backup validation**：区分 Type A（byte copy，hash 相等）与 Type B（logical backup，默认；integrity_check + schema/row/trade_date/distinct ts_code/aggregate equality）；raw_artifact content_hash = **backup 文件自身 hash**；migration report 记录 source_hash/backup_hash/method/validation_result；M1 backup gate 4 条件。（DB-D038）
- **S6 Governance reconciliation**：PROJECT_STATUS 清除已解决开放问题（upsert → DB-D031；evidence version → DB-D032/D036），新增时区确认开放项；R1B.1 完成后 Blocking findings = 0 → No R1C blocker。

### SQL Changes

- `docs/database/sql/migrations/core/C0001_initial_core_schema.sql`：event_evidence 唯一键改 `UNIQUE(event_id, source_id, evidence_key)`（**C0001 尚未实际执行，允许在 R1C 前修正 canonical initial migration**；一旦 applied 不得再改，之后 schema 变更必须 C0002）。
- `docs/database/sql/core_schema_v1.sql`：review snapshot 同步。

### Files Modified

- `docs/database/migration_runner_spec_v1.md`（S1：§4.2.1 事务契约 + §4.3 文件要求；小节编号 4.4–4.8 修正）
- `docs/database/legacy_daily_bars_migration_spec_v1.md`（S2 §7.1 时区策略；S4 §5/§6 strict gate + suffix；S5 §3 backup 语义；V1–V12/abort/retirement 同步）
- `docs/database/r1b_ddl_review_v1.md`（追加 R1B.1 Addendum B19–B24；Blocking findings = 0）
- `docs/database/r1b_test_plan_v1.md`（新增 T-RUNNER-ATOMIC-01/02/03、T-TIMEZONE-01/02、T-EVIDENCE-01/02、T-MAPPING-01、T-BACKUP-01）
- `docs/database/database_design_decisions_v1.md`（追加 DB-D034–D038）
- `docs/database/sql/migrations/core/C0001_initial_core_schema.sql`、`docs/database/sql/core_schema_v1.sql`（S3 unique 修正）
- `PROJECT_STATUS.md`（R1B.1 完成状态 + blockers 更新）

### Not Done

- ❌ 未建库（core.db/private.db 未创建）
- ❌ 未执行 migration（C0001/P0001 未运行）
- ❌ 未迁移 daily_bars（16,620 行保留）
- ❌ 未下载 stock_basic；未接 provider
- ❌ 未修改 fetch_daily.py 生产行为；未启用 dual-write
- ❌ 未实现/未运行 migration runner
- ❌ 未运行任何测试（测试规范已写入，执行属 R1C 第一阶段）
- ❌ 未 force push

### Next

- **Berlin final R1B/R1B.1 review**；批准后 R1C — Database Implementation & Legacy Migration Dry Run（第一阶段：temp DB → C0001/P0001 → constraint tests → runner tests → legacy dry run；不直接迁移生产数据）。

---

## 2026-08-22 — R1C Phase 0/1 Pre-Implementation Reconciliation & Temp-DB Validation

### Task

Berlin 批准 R1B/R1B.1，授权 R1C Phase 0（Pre-Implementation Reconciliation）+ Phase 1（Temp-DB Implementation & Automated Validation）。**第一次真实执行 SQL 只允许在 disposable temp database。**

### Phase 0（三个 mandatory reconciliation + 小清理）

- **P0-1 Dynamic baseline**：legacy spec §0 改为 Documented Baseline（16,620 仅历史参考）；§2 M0 重写为动态 migration-time baseline + Migration Baseline Manifest（captured_at/source_path/source_sha256/file_size/mtime/row_count/trade_date_distribution/distinct_ts_code/fetch_log_count/latest_fetch_time_raw/ts_code_suffixes）。删除 `COUNT(*)==16,620` 式硬编码 abort。
- **P0-2 M1/M2 排序**：重排 M0 Live Preflight → M1 Create & Validate Frozen Snapshot → M2 Bootstrap Source/Dataset → **M2B Register Frozen Snapshot as raw_artifact** → M3→M7；消除 raw_artifact 登记对 source/dataset 的循环依赖。
- **P0-3 Frozen snapshot = 唯一 migration source**：live market.db 只用于 M0/M1；M1 validation PASS 后 M2B–M7 只读 frozen snapshot（M6 SQL 用 `ATTACH <snapshot> AS legacy`）；live 迁移期间新增数据不影响 historical migration。
- 小清理：core_schema_v1.sql event_evidence 重复 evidence_key 注释删除（不改变 DDL）。

### Implementation（stdlib only）

- `scripts/migrate.py`：migration runner（--db core/private/all、--plan、--status、--db-path、--migrations-dir、--no-backup-gate）。DB-D034 事务契约（BEGIN IMMEDIATE 进 executescript + record 同事务 parameterized INSERT + 应用层 commit/rollback）；SHA-256 checksum（MigrationChecksumError）；文件预检（C/P+4位序号+snake 命名、连续性、SQL-token-aware 去注释检测文件内 BEGIN/COMMIT/ROLLBACK）；plan/status 只读不建库；backup gate；**生产路径保护**（PRODUCTION_WRITES_ENABLED=False，data/runtime/core.db 与 data/private/private.db 拒绝写入）。
- `scripts/db_validators.py`：ensure_entity/instrument/event/analysis_uid（UUID 格式校验 + core 存在性查询 + CrossDbReferenceError）。
- `scripts/timestamp_utils.py`：utc_now_iso()（Z 格式）+ convert_legacy_naive_to_utc（zoneinfo，时区未知 → TimestampResolutionError）。
- `scripts/legacy_migration_utils.py`：fixture 级 M0–M7 helpers（capture_baseline / create_frozen_snapshot / validate_snapshot / build_ts_code_mapping / backfill_runs / migrate_bars_from_snapshot / validate_migration）。
- `scripts/__init__.py`：package marker（供测试 import）。

### Tests（6 文件，真实执行于 temp DB）

`tests/test_schema.py`（C0001/P0001 执行、17+8 表、FK check、索引、canonical vs snapshot schema 等价）｜`tests/test_migration_runner.py`（plan/status 无写、幂等、checksum、ATOMIC-01/02/03、预检、生产保护、backup gate、分库历史）｜`tests/test_constraints.py`（17+ 约束案例）｜`tests/test_cross_db_refs.py`（uid validators + 重建安全）｜`tests/test_legacy_migration_fixture.py`（T-FROZEN-SOURCE-01/T-BASELINE-01/T-BACKUP-01/T-MAPPING-01/T-TIMEZONE-01/02）｜`tests/test_privacy_boundaries.py`（core 无 private 数据、private 无 credential）。

### Executed

- temp C0001 → temp core.db：17 表全建，FK check 空 ✅
- temp P0001 → temp private.db：7 业务表 + schema_migrations ✅
- unittest 套件：**Ran 62 tests — OK（0 failed / 0 errors / 0 skipped）** ✅

### Results / Safety

- real core.db = **NOT CREATED**；real private.db = **NOT CREATED**
- legacy market.db = **NOT MODIFIED**（sha256 `93562960aa...d599004` 不变；16,620 行 / 3 日 / 5,546 标的 / fetch_log 3 / suffix SH·SZ·BJ）
- real daily_bars migration = **NOT EXECUTED**；stock_basic 未下载；无联网；无 dashboard 改动
- 临时 DB 全部自动清理（find data -name "*.db" 仅剩 legacy market.db）
- 时区证据：`/etc/timezone=Asia/Shanghai` + 系统 CST + git author 时间戳全部 +0800 → **CONFIRMED**（Phase 2 gate 满足）

### Review

- `docs/database/r1c_phase1_review_v1.md`：C1–C19 全 PASS；**Blocking findings remaining = 0**
- Decision Register 追加 DB-D039–D044

### Next

- **Berlin review of R1C Phase 0/1**；批准后 R1C Phase 2 — Real DB Initialization / Real Legacy Migration Dry Run（不自动开始）。

---

## 2026-08-22 — R1C Phase 1.1 Final Pre-Production Hardening

### Task

进入 R1C Phase 2（真实 legacy + 真实 stock_basic）前，修正 Phase 1 剩余的 4 个实现级安全问题（H1–H4），并通过自动化测试验证。**只修 implementation hardening，不扩大 scope；不建真实 canonical DB。**

### Corrections（H1–H4）

- **H1 Frozen snapshot owns authoritative baseline**：live `data/market.db` 只做 health/readability preflight（`inspect_live_source_health`：file exists / readable / tables / columns / quick_check / observed hash，仅审计）；authoritative migration baseline 由 frozen snapshot 生成（`capture_snapshot_baseline`：snapshot_path / snapshot_sha256 / row_count / trade_date_distribution / distinct_ts_code / fetch_log_count / latest_fetch_time_raw / ts_code_suffixes / aggregates）；`validate_snapshot` **不再 reopen live DB**（只验证 snapshot 内部 + manifest 自洽 + hash）。删除 `capture_baseline()`。M3–M7 全部使用 snapshot manifest。（DB-D045/D049）
- **H2 stock_basic duplicate fail-fast**：新增 `validate_stock_basic_input()` —— 构造 lookup 前显式扫描 duplicate ts_code（→ MappingGateError，含 offending ts_code，绝不 last-one-wins）并校验每行含 ts_code/name/list_date（缺失/空/畸形 → MappingGateError，不创建半完整 identity）。（DB-D046）
- **H3 checksum raw-byte contract**：`migration checksum = SHA-256(exact raw migration file bytes)` 唯一；`raw_bytes = path.read_bytes()` → checksum 只算一次 → `sql = raw_bytes.decode("utf-8")`（UnicodeDecodeError → MigrationFileError）→ `apply_migration(..., checksum=checksum)`（apply 不再自行重算）；comparison 与 schema_migrations INSERT 同一变量。CRLF 下不再误判 CHECKSUM_MISMATCH。（DB-D047）
- **H4 CLI ambiguity**：`--db all` 与 `--db-path` 互斥，`parser.error()` 拒绝（SystemExit 2，不创建文件、不执行迁移）。（DB-D048）

### Tests Added（Phase 1 的 62 → 77）

- T-SNAPSHOT-BASELINE-01（live 后增行+增 fetch_log，migration 仍以 snapshot manifest 6 行为准）
- T-SNAPSHOT-HASH-01（snapshot_sha256 == sha256(snapshot bytes)，且 != live hash）
- T-MAPPING-DUPLICATE-01（duplicate stock_basic ts_code → MappingGateError）
- T-MAPPING-MISSING-FIELD-01（缺 ts_code/name/list_date → ABORT）
- T-CHECKSUM-CRLF-01（CRLF 字节 APPLIED→SKIP 无 mismatch；tamper → MigrationChecksumError）
- T-MIGRATION-ENCODING-01（非 UTF-8 → MigrationFileError）
- T-CLI-ALL-DBPATH-01（SystemExit 2 + foo.db 不存在）
- T-PROD-SYMLINK-01（symlink alias 生产路径 → ProductionWriteNotAuthorizedError）

### Regression Result

- **Ran 77 tests — OK（0 failed / 0 errors / 0 skipped）**
- ATOMIC-01/02/03、plan/status no-write、production guard、constraint 17+、frozen source、timezone、privacy 全部继续 PASS（未删旧测试，仅修实现）

### Files Modified

- `scripts/legacy_migration_utils.py`（H1：inspect_live_source_health/capture_snapshot_baseline/validate_snapshot 重构；H2：validate_stock_basic_input）
- `scripts/migrate.py`（H3：raw-byte checksum 单次计算 + apply 接收 checksum；H4：--db all+--db-path parser.error）
- `tests/test_legacy_migration_fixture.py`（新 snapshot-baseline 用例 + duplicate/missing-field 用例）
- `tests/test_migration_runner.py`（CRLF/encoding/CLI/symlink 用例）
- `tests/test_schema.py`（apply_migration 新签名适配）
- `docs/database/legacy_daily_bars_migration_spec_v1.md`（M0 health-only、M1B snapshot manifest、M1C internal validation、H2 输入校验）
- `docs/database/migration_runner_spec_v1.md`（§4.4 raw-byte checksum 契约、§5 H4 CLI 约束）
- `docs/database/r1c_phase1_review_v1.md`（Phase 1.1 Addendum C20–C27；Blocking findings = 0）
- `docs/database/database_design_decisions_v1.md`（DB-D045–D049）
- `PROJECT_STATUS.md`

### Safety

- real core.db = **NO**；real private.db = **NO**
- real snapshot created = **NO**；market.db modified = **NO**（sha256 不变）
- real stock_basic downloaded = **NO**；network/API calls = **NO**
- real migration executed = **NO**（16,620 行原样保留）

### Next

- **Berlin approval for Phase 2**（Full-Scale Real-Data Staging Rehearsal：real market.db → real frozen snapshot → real stock_basic snapshot → staging core/private.db → full V1–V12 → Berlin review；不直接写正式 canonical DB）。

---

## 2026-08-22 — R1C Phase 1.2 Canonical Date Contract Fix

### Problem

legacy/provider 日期是 compact `YYYYMMDD`（daily_bars.trade_date、Tushare stock_basic.list_date），而 canonical 契约要求 `YYYY-MM-DD`。旧 fixture migrator 原样写入 canonical（20260814），V2 校验又用 raw==raw 错误 oracle，导致错误格式互相匹配仍 PASS。

### Implementation

- 新增 `scripts/date_utils.py`：`normalize_date()`（严格 `datetime.strptime`，接受 YYYYMMDD / YYYY-MM-DD，输出 YYYY-MM-DD；非法日历日期 → `DateNormalizationError`，错误含原始输入）+ `is_canonical_date()`。
- `scripts/legacy_migration_utils.py`：
  - **trade_date 规范化（D1）**：`migrate_bars_from_snapshot` 写 canonical 前调 normalize_date；`run_by_date` lookup 仍用 raw key（fetch_log 与 daily_bars 同为 YYYYMMDD）；
  - **list_date 规范化（D2）**：`validate_stock_basic_input` 要求 list_date 可解析（catch DateNormalizationError → MappingGateError）；mapping 输出 `list_date`（canonical）+ `provider_list_date_raw`；`build_stock_basic_fixture` 默认改为 provider raw `20100101`；
  - **V2/V12 修正（D4）**：`validate_migration` 用 `{normalize_date(d) for d in legacy_dates}` 与 canonical 比较；aggregate 的 legacy 侧日期 key normalize 后比较；
  - **manifest JSON-safe（D4）**：aggregates → `{raw_trade_date: {"sum_volume", "sum_turnover"}}`；validate_snapshot 同步。

### Tests

- 新增 `tests/test_date_utils.py`（T-DATE-01/02/03、T-DATE-INVALID-01/02/03/04、is_canonical_date）
- fixture 测试新增：T-CANONICAL-TRADE-DATE-01（canonical dates == {2026-08-14, 2026-08-17, 2026-08-20}；assertNotIn "20260814"）、T-CANONICAL-LIST-DATE-01（20010827 → mapping/listing_date/valid_from == 2001-08-27）、T-STOCK-BASIC-DATE-INVALID-01/02（20260230/abc → MappingGateError）、T-MANIFEST-JSON-01（json.dumps 成功）、valid compact accepted
- 文档同步：legacy spec §5.2/§8（date semantics）、§3.2 H1 残留清理（snapshot-internal，不再与 live source 比较）

### Results

- **Ran 99 tests — OK（0 failed / 0 errors / 0 skipped）**（原 77 + 新增 22）
- Phase 1.1 H1–H4 与既有全部回归 PASS

### Safety

- real core.db = **NO**；real private.db = **NO**
- real snapshot = **NO**；real stock_basic download = **NO**；market.db modified = **NO**（sha256 不变）
- real migration = **NO**（16,620 行原样保留）；无联网调用

### Next

- **Berlin review for Phase 2**（不自动开始）。

---

## 2026-08-25 — R1C Phase 2 Real-Data Staging Rehearsal COMPLETE（FINAL RESULT: PASS）

### Task

完成 R1C Phase 2 — Full-Scale Real-Data Staging Rehearsal（Berlin 2026-08-22 #381–387 授权）：
real market.db（只读）→ frozen snapshot → 真实 Tushare stock_basic → staging core/private.db →
全量 daily_bars 迁移 → V1–V18 + 100% full-row reconciliation → migration_report.json。

### Background（8-23 首轮未完成）

- 8-23 首轮 rehearsal 在 M2 卡住：该 token 档位对 `stock_basic` 为**小时级滚动限频（40203）**，
  且失败调用也会刷新窗口（09:40Z/09:49Z/10:50Z/11:05Z 连续 40203）。后台进程 `nimble-crest`
  最终未产生任何产物（无 staging、无 report；exec session 清理后唤醒丢失）。
- 教训已记 memory/2026-08-23.md：低积分 token 上 stock_basic 需冷却 ≥75 分钟单次尝试。

### Implementation

- 新增 `scripts/phase2_staging_rehearsal.py`（stdlib only，M0–M7 + build_report）：
  - M2 限频修复：L 状态单查优先 + 覆盖率驱动补 D/P + 40203 等待 3660s 重试（最多 3 次）；
    精简字段去掉 `is_hs`；token 程序内从 env/~/API.txt 读取，绝不落盘/回显。
  - M3/M4 100% mapping gate（MappingGateError → diagnostics 落盘，bar 迁移不启动）。
  - M6 按 trade_date 逐批 `BEGIN IMMEDIATE` 原子迁移；失败即停。
  - M7 V1–V18 + full-row reconciliation；report JSON 含 reproducibility（git sha / checksums / snapshot hashes）。
  - 硬守卫：PRODUCTION_PATHS（data/runtime/core.db、data/private/private.db）resolve 冲突即拒绝；
    live market.db 全程只读，收尾校验 before==after hash。
- `scripts/legacy_migration_utils.py` / `scripts/timestamp_utils.py` 文件头描述更新至 Phase 1.2/Phase 2 semantics。
- `.gitignore` 增加 `data/staging/`（staging 产物不入库）。

### Run（2026-08-25 重跑，限频已冷却 >47h）

- run_id `20260825T030439Z`（03:04:39Z 启动，03:04:43Z 完成，git `be27e82`）
- M0 PASS：live market.db = **38,789 行 / 7 交易日（08-14→08-24）/ 5,548 标的**（SH·SZ·BJ，8-24 例行下载已回补缺口）
- M1 PASS：frozen snapshot `data/raw/legacy/market_20260825T030439Z.db`（sha256 `ac5b2acd…`，manifest 一致；8-23 旧快照保留）
- M2 PASS：stock_basic **L 单查一次成功**（5,550 条），覆盖率 5,548/5,548 = 100%，未触发 D/P 补查
- M3/M4 PASS：5,548 entities / 5,548 instruments / 11,096 identifiers，1:1 严格
- Staging PASS：core.db（17 tables，C0001）+ private.db（8 tables，P0001），FK check 全空
- M5 PASS：7 ingest_runs backfill（Asia/Shanghai 时区）
- M6 PASS：**38,789 行 bars 全量迁移**，7/7 批次原子成功，0 失败
- M7 PASS：**V1–V18 全部 PASS**；full-row reconciliation 38,789 行 checked，ohlc/volume/turnover/date/mapping mismatch 全 0
- report：`data/staging/r1c_phase2/20260825T030439Z/migration_report.json`（FINAL RESULT: PASS）
- live market.db 运行前后 sha256 一致（`7b435961…`）

### Tests

- **Ran 99 tests — OK（0 failed / 0 errors / 0 skipped）**（Phase 1.2 门槛复跑）

### Review

- `docs/database/r1c_phase2_review_v1.md`：P2-1…P2-10（8 HIGH PASS + 1 MEDIUM 已解决），**Blocking findings = 0**

### Safety

- 生产 DB：**NOT CREATED**（data/runtime/core.db、data/private/private.db 均不存在）
- 真实迁移：**NOT EXECUTED**（38,789 行 legacy 原样保留）
- live market.db：只读，sha256 before==after
- token：未出现在日志/report/CLI；`data/raw/`、`data/staging/` 均 gitignored

### Next

- **Berlin review Phase 2 artifacts**（migration_report.json + r1c_phase2_review_v1.md + 99 tests）
- 批准后决策：生产迁移授权 / R2 Portfolio & Watchlist / dual-write；不自动开始。

---

## 2026-08-25 — R1 Finalization Gate（R1 — Core Data Model: COMPLETE）

### Task

R1 Finalization Gate — Clean-Commit Reproducibility Rehearsal：在 clean、committed、可复现的 Git tree 上用已提交的 Phase 2 runner 再执行一次真实 staging rehearsal，验证可独立复现 PASS 后正式关闭 R1。

### Git State

- 起始：branch=main，HEAD==origin/main==`55888f9`，working tree clean（git status --porcelain 空）
- 新增 reproducibility gate 后 commit `a6007b3`（R1 finalization add reproducibility gate）→ push → 确认 HEAD==origin/main==`a6007b3`、clean
- Finalization run 在 clean committed tree 上执行；report 记录 git_dirty=false

### Implementation

- `scripts/phase2_staging_rehearsal.py`：
  - 新增 `get_git_reproducibility_state()`：git_commit / git_branch / git_dirty（`git status --porcelain`，fail-closed）/ runner_path / runner_sha256 / c0001_sha256 / p0001_sha256（raw-byte SHA-256，H3 契约扩展）
  - report 增加 `reproducibility` 块（含 git_dirty；git_dirty!=false → Finalization FAIL）与 `safety` 块（production core/private exists、live_db_writer_used、token_exposed、dual_write_enabled、fetch_daily 行为未改）
  - 支持 `--staging-root` / `--report-name`（Finalization workspace = `data/staging/r1_finalization/<run_id>/r1_finalization_report.json`）
- `tests/test_reproducibility.py`：T-REPRO-GIT-METADATA-01（helper + report schema）、T-REPRO-RUNNER-HASH-01（runner_sha256 == raw bytes）

### Regression

- **Ran 103 tests — OK（0 failed / 0 errors / 0 skipped）**（原 99 + 新增 4）

### Finalization Run（2026-08-25 run `20260825T043812Z`）

- **FINAL RESULT: PASS**（report：`data/staging/r1_finalization/20260825T043812Z/r1_finalization_report.json`）
- Git：commit `a6007b3`，branch main，dirty=false；runner 属 HEAD（HEAD runner sha256 `d429dae7…` == report runner_sha256）
- M0 PASS：live market.db 38,789 行 / 7 交易日 / 5,548 标的，sha256 `7b435961…`（前后一致）
- M1 PASS：frozen snapshot `market_20260825T043812Z.db`（sha256 `ac5b2acd…`）
- M2 PASS：stock_basic L 单查 5,550 条，覆盖 5,548/5,548 = 100%（未触发 D/P）
- M3/M4 PASS：5,548 entities / 5,548 instruments / 11,096 identifiers，1:1
- Staging PASS：core.db（17 tables，C0001）+ private.db（8 tables，P0001），FK 全空
- M5 PASS：7 ingest_runs（Asia/Shanghai）
- M6 PASS：38,789 行 bars 全量迁移，7/7 批次原子成功
- M7 PASS：V1–V18 全 PASS；full-row reconciliation 38,789 行，0 mismatch
- Safety：production core/private 不存在；live 只读；token 未暴露；dual-write off

### Review

- `docs/database/r1_finalization_review_v1.md`：**Decision: R1 COMPLETE**；Git Reproducibility / Real Inputs / Mapping / Migration / V1–V18 / Full Row Reconciliation / Safety / Governance Cleanup / Residual Risks；Blocking findings = 0

### Governance Cleanup

- README：Current Stage R0 → **R1 Core Data Model — COMPLETE** + What works today / Not yet implemented（§二十五）
- PROJECT_STATUS：stale Data Status（16,620 / 3 dates / 5,546）移除 → Current Live Legacy Snapshot（38,789 / 7 / 5,548）vs Last Validated Staging Snapshot（run `20260825T043812Z`）；Runtime Status 过期 cron 时间清理（§二十六/§二十七）
- Decision Register：DB-D054–D057 追加（§二十八）
- 明确：**No further R1.x design phases are planned**（§二十四）

### Safety

- 生产 DB：NOT CREATED；真实迁移：NOT EXECUTED；live market.db 只读（sha256 before==after）；token 未出现在日志/report/CLI；staging/raw gitignored

### R1 Decision

- **R1 — Core Data Model: COMPLETE**（design + implementation + real-data staging + reproducibility gate 全部 validated）

### Next

- **R2 Minimal Portfolio & Watchlist + Vertical Slice MVP**（等待 Berlin 批准，不自动开始）
- 生产迁移授权另议（PRODUCTION_WRITES_ENABLED 保持 False）
