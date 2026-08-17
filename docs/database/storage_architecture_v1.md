# Storage Architecture v1

> Market Monitor 存储架构 —— R1A 设计交付物
> 日期：2026-08-17 ｜ 状态：Design (not implemented) ｜ 本轮**不实施** Parquet/DuckDB 迁移

---

## 1. 总览：三件套分工

| 层 | 技术 | 职责 | R1 状态 |
|----|------|------|---------|
| Operational | SQLite | metadata、entity identity、operational state、events、portfolio state、ingestion audit | **✅ 唯一实施层** |
| Bulk historical | Parquet | 大规模历史行情、minute bars、financial facts、macro observations、大体积数据集 | Deferred（未来归档层） |
| Analytical | DuckDB | 分析查询层：直接查 Parquet + 必要的 SQLite export | Deferred（未来分析层） |

### 1.1 判断

这个方向**合理，采纳**。理由：

- SQLite 单文件、零运维、事务完整，适合"个人自用、单机、每日几万行"的 operational 负载；A 股全市场日线约 5,500 行/交易日，年增长 ~130 万行，SQLite 单表可轻松支撑多年。
- Parquet 列式 + 压缩，适合未来分钟线/多年历史/财务事实这类"写入一次、反复扫描"的数据；与 SQLite 不冲突，是**单向归档**关系。
- DuckDB 直接查询 Parquet，无需二次导入，适合 R8/R9 的量化分析；**不迁移**，只作为未来查询层。

### 1.2 防 split-brain 原则（重要）

同一数据**单一真源**：

- 近期/operational 数据真源在 SQLite；
- 历史归档 = SQLite → Parquet **单向复制**（归档后 SQLite 可保留近期窗口或全量，但写入永远只发生在一处）；
- R1 阶段不存在双写。未来若启用归档，必须定义归档边界（如">2 年数据进 Parquet"）与回查路径，不得两处同时可写。

---

## 2. 物理分库：core.db + private.db

### 2.1 布局

```
data/
├── market.db            # legacy（现有 daily_bars + fetch_log，本轮不动）
├── runtime/
│   └── core.db          # PUBLIC：identity / market data / events / ops audit
└── private/
    └── private.db       # PRIVATE：positions / watchlists / theses / (未来 accounts/transactions)
```

（.gitignore 已覆盖 `*.db` 与 `data/private/`，两者均不入 Git。）

### 2.2 评估结论：**采用物理分库**（采纳 Berlin 倾向）

优点：
- 权限/备份/加密边界清晰：private.db 可单独加密、单独备份、单独误删保护；
- 杜绝"公开仓库混入持仓/成本数据"这一类 privacy leakage（即使有人误操作，物理文件也分离）；
- 未来同步/导出公开数据集（如 events 分享、研究用途）时，core.db 可整体导出而不触碰 private。

代价（可控）：
- 跨库关联无法用 SQLite 原生 FK（SQLite 不支持跨库 FK）→ 采用**引用式关联**：private.db 只存 `instrument_id` / `entity_id` 整数引用，不存冗余 identity 文本；存在性/唯一性由应用层在写入时校验（R1B 提供校验函数），查询时 `ATTACH 'core.db' AS core` 只读 join。
- 备份策略需双文件同时备份（同一事务窗口不一致风险低，因为 private 与 core 的写入点不同步——可接受）。

### 2.3 SQLite ATTACH 是否使用

**是，仅用于查询**。R1B 提供标准只读连接模式：

```sql
ATTACH DATABASE 'data/runtime/core.db' AS core;
SELECT i.primary_symbol, p.quantity, p.avg_cost
FROM private.positions p JOIN core.instruments i ON i.instrument_id = p.instrument_id;
```

写入始终只写各自文件（core 写 core.db，private 写 private.db），不跨库写。

### 2.4 一致性要点

- `instrument_id` / `entity_id` 的**分配唯一真源在 core.db**；private.db 永不自行分配 id；
- 应用层提供 `ensure_instrument(instrument_id)` 校验（写 private 前检查 core 存在）；
- 若未来需要强一致（如删除 instrument 时级联清理 private 引用），用定期一致性检查脚本（对比 core 不存在的孤儿引用），R1 阶段手工/脚本触发即可。

---

## 3. 为什么现在物理分库值得（而不是单库逻辑分区）

任务允许"单库 + 逻辑分区"备选。评估：

- 单库 + `is_private` 标志位/前缀表名：实现简单，但**没有物理边界**，任何 bug、任何导出、任何备份恢复都可能把 private 数据带出；且 `.gitignore` 无法区分文件内内容。
- 本项目 private 数据（持仓/成本/账户/交易/投资逻辑）是**最高敏感度**数据，且 PROJECT_RULES §4 明确禁止其进入公开 Git。物理分库把"防泄漏"从"纪律"升级为"物理隔离"，成本只有一次 ATTACH join 的复杂度。

**结论：物理分库（core.db + private.db）优于单库逻辑分区，采纳。**

---

## 4. 目录与文件建议（R1B 实施时）

```
data/
├── market.db                  # legacy（保留至迁移验证完成）
├── runtime/core.db            # canonical core
├── private/private.db         # private
├── raw/                       # 未来 raw artifacts / parquet 暂存（gitignore 已覆盖）
└── archive/                   # 未来 parquet 归档（gitignore 已覆盖）
```

- 备份：`sqlite3 core.db ".backup ..."` 每日快照 + private.db 单独加密备份（R2+ 实施）。
- 权限：`data/private/` 目录 `chmod 700`（R1B 建库时执行）。
