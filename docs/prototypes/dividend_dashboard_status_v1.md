# Dividend / Quality Screener Dashboard — Prototype Status v1

> Dashboard Prototype 治理收编文档（轻量，非正式产品文档）
> 日期：2026-08-22 ｜ Status: Existing Prototype / Not Integrated with Canonical Database
> 目的：把已存在的 prototype 纳入项目治理，记录来源与风险，**不升级为正式产品文档**。

---

## Purpose

港股高股息 / 质量筛选监控面板（"港股稳健红利现金流 · 监控面板"）：对港股 universe 按股息率、派息连续性、现金流覆盖、质量与估值加权评分，输出分级（优秀/稳健/观察）列表与历史趋势图。

## Current Files（2026-08-22 迁移至 `prototypes/dividend_dashboard/`，随 index.html 相对引用保持一致）

| 文件 | 内容 | 大小 |
|------|------|------|
| `prototypes/dividend_dashboard/index.html` | 面板前端（HTML+CSS+JS，Chart.js 图表） | ~16 KB |
| `prototypes/dividend_dashboard/chart.umd.min.js` | Chart.js UMD bundle（第三方库） | ~205 KB |
| `prototypes/dividend_dashboard/data/dashboard_data.js` | 筛选结果数据（`window.DASHBOARD_DATA` + `window.HISTORY`） | ~33 KB |
| ~~Test1~~ | ~~测试残留~~（**2026-08-22 已删除**，独立 cleanup 动作） | — |

## Data Source

- 数据为**公开市场数据**：港股 ticker、名称、行业、价格、市值、TTM 股息率、派息比率、PE/PB/ROE、FCF 覆盖等。
- 数据内容不含：portfolio、账户、成本、个人备注、API token、非公开信息。
- 具体原始数据源未在仓库内记录（疑似来自本地脚本抓取的公开数据，需 Berlin 确认）。

## Generation Process

- `data/dashboard_data.js` 文件头注释声明：`// 由 sync_data.py 自动生成，勿手改`。
- **生成脚本 `sync_data.py` 未提交到仓库**（全历史 grep 无该文件）；当前本地工作区亦不存在。
- 数据生成逻辑（从字段推断）：固定 universe（63 只港股）→ 筛选条件（min_dividend_yield 3.5 / max 12.0、payout 0.1–0.9、连续派息 ≥5 年、市值 ≥100 亿 HKD、FCF 正年数 ≥2）→ 加权评分（yield 0.3 / consistency 0.25 / coverage 0.25 / quality 0.1 / valuation 0.1）→ 分级（优秀/稳健/观察）+ near_miss + errors。

## Known Scripts

- `sync_data.py`：生成 dashboard_data.js 的脚本——**存在于 `~/projects/invest-lab/data/hk-dividend/`（invest-lab 项目，不在本仓库）**；dashboard_data.js 的 generated_at 时间戳与 commit 时间一致（2026-08-16、08-17、08-20、08-24、08-25、08-26），说明是 cron/手动运行后提交。
- `deploy.sh`：**同目录**（`~/projects/invest-lab/data/hk-dividend/deploy.sh`）——把 `frontend/` 产物复制到 `deploy/`（market_monitor GitHub 仓库的独立 clone）并 commit/push 到 main。**2026-08-27 修复**：目标路径从 repo root 改为 `prototypes/dividend_dashboard/`，新增与 origin/main 自同步、root 残留自动清除、防回归断言（root 出现 dashboard 文件则中止提交）。

## Automation Status

- **自动任务：有**——invest agent 的 cron `dbece3dc`（港股红利现金流每日监控，每日 17:30 CST）执行 `pipeline.py && sync_data.py && deploy.sh`，即 `update: ... 17:32` 提交的来源（2026-08-17/08-24/08-25/08-26 均为该任务）。OpenClaw market_monitor agent 的 cron 仅 `market-monitor-daily-download`（A 股行情下载），与 dashboard 无关；系统 crontab 为空。
- **路径治理（2026-08-27）**：deploy.sh 目标已固定在 `prototypes/dividend_dashboard/`；GitHub main 上的 root 副本已删除（cleanup commit `9885170`）；`.gitignore` 增加 root 锚定 ignore（`/index.html` `/chart.umd.min.js` `/data/dashboard_data.js`）；回归测试 `tests/test_dashboard_governance.py`（T-DASH-ROOT-01/02 + T-DASH-PROTO-01）。

## Privacy Classification

- **PUBLIC-SAFE**：仅含公开市场筛选结果；无私人数据。
- 可在 Git 中保留跟踪。
- ⚠️ 未来若 sync_data.py 接入私人账户/持仓数据，必须改为输出到 private/ 并停止提交。

## Integration Status

- **Not Integrated with Canonical Database**：数据不来自 core.db/private.db；未使用 canonical schema；与本项目数据库完全独立。
- 不属于 R1 Core implementation；不影响 R1A v2 Freeze Candidate。
- 未来归属候选（未决定）：R8 Historical Intelligence 或 R9 Quant / Analytics Layer。

## Known Risks

1. **生成脚本缺失**：sync_data.py 未入库 → 数据不可复现（目前是"结果已提交、过程不可见"）。
2. **数据源无记录**：无法审计数据来自哪个 API/来源。
3. ~~根目录结构~~（**2026-08-22 已解决**：迁移至 `prototypes/dividend_dashboard/`）。
4. ~~Test1 残留~~（**2026-08-22 已删除**）。
5. **陈旧风险**：若依赖第三方库（Chart.js UMD）的固定快照，未来安全更新需手动。

## Future Options（未决定，不自动执行）

1. 将 sync_data.py 收编入库（先确认其数据源与隐私合规）。
2. 未来正式归属 R8/R9，或作为 R1 之后的分析层参考实现。
3. 保持原型状态不动，仅治理记录。

## Governance Notes

- R1A.1（2026-08-22）：识别、记录、收编；不删除、不扩展、不重构。
- 后续 cleanup（2026-08-22，Berlin 授权）：删除 `Test1`；dashboard 迁移至 `prototypes/dividend_dashboard/`（git mv 保留历史；`data/dashboard_data.js` 随 index.html 进入 `prototypes/dividend_dashboard/data/`，相对引用不变）。
- 决策登记见 `docs/database/database_design_decisions_v1.md` DB-D015。
