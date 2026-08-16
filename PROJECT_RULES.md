# PROJECT_RULES.md — Market Monitor 项目规则

> 本文件是项目最高层级的长期规则文件。每次重要开发任务原则上都应先读取本文件。

## 0. 三层信息体系

本项目严格区分三类信息，职责不得混淆：

| 层级 | 文件 | 职责 |
|------|------|------|
| A. Project Governance | `PROJECT_RULES.md` `PROJECT_STATUS.md` `PROJECT_PROGRESS_LOG.md` | "如何开发 Market Monitor 这个项目" |
| B. OpenClaw Runtime | `AGENTS.md` `HEARTBEAT.md` `IDENTITY.md` `SOUL.md` `USER.md` `TOOLS.md` `memory/` | "系统每天运行时发生什么" |
| C. Application / Runtime Data | `data/` `scripts/` `skills/` `config/` `tests/` `logs/` `docs/` | 实际代码、数据库、日志和运行产物 |

### 三类日志严格区分

- **`PROJECT_PROGRESS_LOG.md`**：记录"我们如何开发这个系统"。例：建立 security_master、修改数据库架构、增加 FMP provider、建立 Event Engine、修改 OpenClaw Skill、改变技术路线。
- **`memory/YYYY-MM-DD.md`**：记录"系统今天运行时发生了什么"。例：Tushare 今日下载成功、某 API timeout、某股票发布财报、某公告触发事件、某数据源缺口。**不得把项目开发过程长期记录在 memory/ 中。**
- **`logs/`**：程序级原始运行日志。例：HTTP status、timestamp、rows fetched、exception、retry、database commit。**不承担项目管理功能。**

## 1. 项目定位

Market Monitor 是 Berlin 的私人市场监控与投研基础设施。

目标：
- 长期保存市场数据
- 管理持仓与自选
- 监控财报和重大公司事件
- 识别与投资逻辑有关的重要变化
- 提供 Telegram Alerts
- 生成 Daily / Weekly Brief
- 形成长期可检索的市场事件数据库
- 后期支持历史事件分析、回测和量化研究

**当前阶段：不执行真实证券自动交易。**

## 2. AI 与确定性程序的职责边界

### Python / deterministic code 负责（事实与确定性流程）

- API 请求
- 数据下载
- 数据库读写
- 去重
- 数据校验
- 时间处理
- 交易日判断
- fingerprint
- schema validation
- retry
- 数据完整性检查

### OpenClaw / LLM 负责（理解与判断）

- 判断事件重要性
- 阅读财报和公告
- 信息归纳
- 投资逻辑影响判断
- 跨信息源关联
- 生成 briefing
- 解释异常
- 决定是否值得提醒 Berlin

**原则：Python 负责事实和确定性流程，LLM 负责理解与判断。**

## 3. 数据规则

- 不编造数据
- raw data 原则上不可覆盖
- 历史数据不能无记录删除
- 使用 append 或受控 upsert
- 所有数据源应可追溯
- 记录 source、timestamp、timezone、currency、unit
- API 失败不能把空结果当作真实 0
- 数据缺口必须显式记录
- schema 修改必须有迁移意识
- 重要数据库结构变化必须进入 `PROJECT_PROGRESS_LOG.md`

## 4. 隐私和安全规则

当前 GitHub repository 是**代码仓库**。禁止将以下内容提交到公开 Git：

- API token
- password
- Telegram token
- IBKR credential
- 真实账户凭证
- 私密 portfolio 数据
- 持仓成本
- 账户资产规模
- 私密交易记录
- 包含上述数据的 SQLite / DuckDB 文件
- `.env`
- secret files

如发现现有仓库存在风险，应在本轮修正 `.gitignore`。

## 5. 第三方 Skill / Package 安全规则

第三方（OpenClaw Skill、ClawHub Skill、Python package、GitHub repository）不能因为可以安装就直接进入生产环境。至少需要：

- 确认来源
- 阅读核心代码或 SKILL.md
- 检查读写权限
- 检查网络访问
- 检查是否能访问 secrets
- 在隔离或测试环境验证

核心投资数据尽量由本项目自己管理。

## 6. 外部动作规则

### 可以自主执行

- 下载公开数据
- 查询 API
- 更新本地数据库
- 运行数据校验
- 写 runtime log
- 写当天 memory
- 生成本地报告

### 需要用户明确授权

- 向第三方发送非预设消息
- 修改外部账户
- 删除重要数据
- 强制 Git push
- 修改远端历史
- 大规模数据迁移
- 安装高权限第三方 Skill

### 当前禁止自主执行

- 股票买卖
- 期货交易
- 期权交易
- 外汇交易
- 转账
- 真实账户下单

## 7. Git 规则

- 默认分支：`main`
- 正常流程：`git status` → 检查变更 → commit → push `origin/main`
- 不自行创建复杂 branch strategy
- 不 force push，除非用户明确授权

## 8. 项目日志规则

- `PROJECT_PROGRESS_LOG.md` 为 append-only
- 每次"有意义的项目开发任务"完成后追加
- 普通运行任务不写 Progress Log
- 历史记录原则上不得修改（有误则追加 correction，不覆盖）

## 9. PROJECT_STATUS 规则

`PROJECT_STATUS.md` 只反映当前系统状态，不保存完整历史。以下变化应更新：

- 当前 R 阶段
- 当前 active component
- 当前 blocker
- 数据源状态
- 数据库状态
- 当前 next step
- production/development 状态
