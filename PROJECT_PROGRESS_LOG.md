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
