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
