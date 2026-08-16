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
