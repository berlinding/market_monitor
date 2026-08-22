# Storage Architecture v2 — Freeze Candidate

> Market Monitor 存储架构 —— R1A.1 修订交付物
> 日期：2026-08-22 ｜ **Status: FREEZE CANDIDATE — NOT YET APPROVED**
> 基于 `storage_architecture_v1.md` 修订；v1 保留不覆盖。本轮**不实施**任何建库/迁移。

---

## 1. 总览：三件套分工（不变）

| 层 | 技术 | 职责 | R1 状态 |
|----|------|------|---------|
| Operational | SQLite | metadata、identity、events、portfolio state、ingestion audit | **✅ 唯一实施层** |
| Bulk historical | Parquet | 大规模历史行情、minute bars、financial facts、macro observations | Deferred（未来归档层） |
| Analytical | DuckDB | 分析查询层：直接查 Parquet + SQLite export | Deferred（未来分析层） |

防 split-brain 原则不变：同一数据单一真源；SQLite → Parquet 单向复制；R1 阶段不存在双写。

---

## 2. 物理分库：core.db + private.db（布局不变，引用规则升级）

### 2.1 布局

```
data/
├── market.db            # legacy（现有 daily_bars + fetch_log，本轮不动）
├── runtime/
│   └── core.db          # PUBLIC：identity / market data / events / ops audit / raw evidence
└── private/
    └── private.db       # PRIVATE：accounts / positions / watchlists / theses / thesis analysis / alerts
```

（.gitignore 已覆盖 `*.db` 与 `data/private/`，两者均不入 Git。）

### 2.2 v2 核心变化：跨库引用用 **UID**，不再用 INTEGER id（B3）

v1 采用"private.db 只存 `instrument_id` / `entity_id` 整数引用"；v2 修正为：

> **跨库引用一律使用 `entity_uid` / `instrument_uid` / `event_uid` / `analysis_uid`（UUIDv4 TEXT），禁止引用 INTEGER surrogate 或 ROWID。**

（F8B 补充：`analysis_uid` 用于 private.alerts → core.event_analysis 的跨库精确引用。）

理由：

1. **重建安全**：core.db 重建（从备份/导出重建、ROWID 重排、导入导出）时，INTEGER id 可能变化；UUIDv4 作为列值随行保留，**跨库引用在重建后仍然有效**。
2. **合并/迁移安全**：多环境（本机/新机）合并数据时，UUID 全局唯一，不冲突；INTEGER 会撞号。
3. **审计可读**：引用本身可独立校验，不依赖分配顺序。

同库关系（private.db 内部，如 positions→accounts、event_thesis_analysis→investment_theses）**仍可用 INTEGER FK**（同库无重建漂移问题，且 SQLite 原生 FK 约束可用）。

### 2.3 ATTACH 只读 join（示例，R1B 实施）

```sql
ATTACH DATABASE 'data/runtime/core.db' AS core;
SELECT p.account_id, i.primary_symbol, p.quantity, p.avg_cost
FROM positions p
JOIN core.instruments i ON i.instrument_uid = p.instrument_uid;
```

写入始终只写各自文件，不跨库写。**ATTACH join 的 key 从 `instrument_id` 改为 `instrument_uid`**（v1→v2 差异）。

### 2.4 一致性要点（v2 更新）

- UID 分配唯一真源在 core.db 的 `*_uid` 列；private.db 永不自行生成 core 主体的 uid（只引用）。
- 应用层提供 `ensure_instrument_uid(uid)` / `ensure_entity_uid(uid)` / `ensure_event_uid(uid)` / `ensure_analysis_uid(uid)` 校验（写 private 前检查 core 存在）。
- 定期孤儿引用检查脚本（对比 core 不存在的 uid），R1 阶段手工/脚本触发。

---

## 3. 为什么物理分库仍然成立（v1 论证不变）

- private 数据（持仓/成本/账户/交易/投资逻辑/私人 thesis 分析/告警）是最高敏感度数据；
- 物理分库把"防泄漏"从纪律升级为物理隔离；core.db 可整体导出而不触碰 private；
- .gitignore 已覆盖 `*.db` 与 `data/private/`。

**v2 新增隐私边界（B7/B8）**：

| 内容 | 归属 |
|------|------|
| generic event analysis | core.db `event_analysis`（PUBLIC） |
| 私人 thesis 分析 | private.db `event_thesis_analysis`（PRIVATE） |
| alerts（运行时用户状态） | private.db `alerts`（PRIVATE，B8） |

---

## 4. Raw 证据与归档（v2：raw_artifacts 升 Core）

```
data/
├── raw/        # raw artifacts（API payload / 下载文件 / DB 快照），gitignore 已覆盖
└── archive/    # 未来 parquet 归档
```

- `raw_artifacts` 从 Deferred **提升为 R1 Core**（B12）：canonical 数据必须可追溯到下载/原始证据。
- 每件 artifact 记录 content_hash（SHA-256）、source、run、retrieved_at；**append-only，raw 不覆盖**。
- legacy `data/market.db` 在迁移前注册为 raw_artifact（B14）：备份副本 + SHA-256，canonical normalization 后仍可完整追溯。

### 4.1 Provenance Chain（B13/B14）

```
Data Source (data_sources)
   ↓
Dataset (datasets) + Dataset Source (dataset_sources: role + priority_rank 决定顺序)
   ↓
Ingest Run (ingest_runs)
   ↓
Raw Artifact (raw_artifacts, content_hash=SHA-256)
   ↓
Canonical Data (market_prices_daily 等, 带 ingest_run_id / raw_artifact_id)
```

每一行行情都能回答：**哪次 ingest、哪个 source、哪个 raw artifact**（B13）。legacy 数据经 B14 的备份 + artifact 注册后，同样满足"canonical completeness + raw provenance completeness"双完整性定义。

---

## 5. Parquet / DuckDB 兼容性（v2 审查项）

- UID 为 TEXT（UUIDv4 标准 36 字符），Parquet 可直接存储（BYTE_ARRAY/STRING）；content_hash 为 64 字符 hex TEXT，同样兼容。
- 布尔/数值/日期均为 Parquet 原生类型；JSON 列以 TEXT 存储（Parquet string），分析层按需解析。
- 未来归档：core.db → Parquet 单向复制；归档后查询走 DuckDB；写入只发生在 SQLite。

---

## 6. 备份策略（不变 + 补充）

- core.db / private.db 每日 `sqlite3 .backup` 快照（R1B 起）。
- private.db 单独加密备份（R2+ 实施）。
- `data/private/` 目录 `chmod 700`（R1B 建库时执行）。
- **UID 使备份恢复/重建后跨库引用不失效**（v2 关键收益）。
