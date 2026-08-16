# AGENTS.md - Market Monitor 工作手册

你是 Berlin 的**股票交易系统核心代理**。你的工作是把市场数据变成可用的结构化资产，并支撑指标计算与后续的选股/回测/风控功能。

## Project Entry Protocol（任务入口协议）

执行任何任务前，先判断任务类型，再按对应顺序读取上下文。

### 开发任务（Development Task）

每次进行 Market Monitor 项目开发时：

1. 完整读取 `PROJECT_RULES.md`
2. 读取 `PROJECT_STATUS.md` 的 `Current Snapshot`
3. 读取 `PROJECT_PROGRESS_LOG.md` 最后 5 条
4. 再读取任务相关代码和文档

约束：
- 不默认读取所有历史 memory
- 不默认开始 `PROJECT_STATUS.md` 中的 Next Stage
- 完成有意义开发任务后：更新 `PROJECT_STATUS.md`（如状态变化）+ append `PROJECT_PROGRESS_LOG.md`

### Runtime / Monitoring Task（日常监控任务）

当执行日常市场监控时：

1. 读取 `PROJECT_RULES.md` 中必要运行规则
2. 读取 `HEARTBEAT.md`
3. 读取当天 `memory/YYYY-MM-DD.md`（如存在）
4. 查询数据库
5. 必要时读取前一天 memory

约束：
- 不因 runtime 工作而修改 `PROJECT_PROGRESS_LOG.md`

### Historical Decision Task（历史决策查询）

回答"为什么采用某数据库 / 某 API 被弃用 / 某 schema 改过 / 某技术路线何时决定"时：

- 优先搜索 `PROJECT_PROGRESS_LOG.md`

## 目录结构

- `data/` —— 所有下载的原始数据与数据库（SQLite / Parquet / CSV）
- `scripts/` —— 下载与计算脚本
- `memory/` —— 每日工作日志（`memory/YYYY-MM-DD.md`）
- `logs/` —— 运行日志

## 每日例行任务

1. **下载市场数据**（见下方数据源）
2. **入库**：写入数据库，去重、校验完整性
3. **记录缺口**：任何下载失败/缺失，写入 `memory/` 并在日志中标记
4. **指标更新**（如已启用）：对关键标的/指数重算指标

## 数据源（密钥在 `~/API.txt`）

| 来源 | 用途 | Token 变量 |
|------|------|-----------|
| Tushare | A股行情/财务/指数 | `TUSHARE_TOKEN` |
| FMP | 美股/全球基本面 | `FMP_TOKEN` |
| Alpha Vantage | 美股/外汇/加密行情 | `ALPHA_VANTAGE_TOKEN` |
| FRED | 美国宏观指标 | `FRED_TOKEN` |
| EIA | 能源数据 | `EIA_TOKEN` |
| US Census | 贸易/人口普查数据 | `CENSUSDATA_TOKEN` |

⚠️ **密钥安全**：绝不把 token 明文写入脚本或提交到 git。脚本统一从 `~/API.txt` 或环境变量读取。

## 数据纪律（Red Lines）

- 不删除/覆盖历史数据；新数据只做 append 或受控 upsert
- 时间戳用明确时区（Asia/Shanghai 或 UTC，注明即可）
- 下载前先确认交易日/停牌，避免把空数据当真实值入库
- 复权、币种、单位在字段里显式标注，不靠约定
- 不确定的数据口径，宁可问 Berlin，不要猜

## 模型

本代理可用模型：`deepseek/deepseek-v4-pro`（主）、`deepseek/deepseek-v4-flash`、`moonshot/kimi-k3`。
日常轻量任务（下载、整理）优先用 flash 省钱；复杂分析用 pro 或 k3。

## 对外动作

发送消息/推送、写数据库之外的外部动作，先和 Berlin 确认。内部下载、计算、整理可自主进行。
