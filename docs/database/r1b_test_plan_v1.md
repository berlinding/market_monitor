# R1B Test Plan v1

> Market Monitor R1B 测试计划 —— SQL DDL / migration runner / legacy migration / 隐私
> 日期：2026-08-22 ｜ **Status: PLAN — NOT EXECUTED**
> 依据：R1A v2 FROZEN + `core_schema_v1.sql` / `private_schema_v1.sql` + `migration_runner_spec_v1.md`
> 本轮只写计划，不执行测试（不建库）。

---

## 1. 测试层级总览

| 层级 | 覆盖 | 对应文件 |
|------|------|---------|
| T1 Schema tests | DDL 可加载、表/列/约束齐全 | core_schema_v1.sql, private_schema_v1.sql |
| T2 Constraint tests | 15 个业务约束案例（§4） | 两 schema |
| T3 Migration runner tests | 顺序/幂等/checksum/回滚/dry-run/分库 | migration_runner_spec_v1.md |
| T4 Cross-db UID tests | 跨库引用校验 | validators spec（§6） |
| T5 Legacy migration tests | M0–M9 迁移流程与验证 | legacy_daily_bars_migration_spec_v1.md |
| T6 Privacy tests | core/private 边界 | §6 本文 |

测试环境：**临时目录**（如 `tests/tmp_*`）内的 SQLite 内存/临时文件库；绝不在 `data/` 生产路径执行。

---

## 2. T1 — Schema Tests

1. `core_schema_v1.sql` 可在空临时库完整执行（`executescript`），无语法错误；
2. 执行后 `sqlite_master` 中 17 张 core 表全部存在；
3. `private_schema_v1.sql` 执行后 7 张业务表 + schema_migrations 存在；
4. 每张表的列集合与 data_dictionary_v2 一致（程序化对比列名）；
5. FK 全部指向已存在表（`PRAGMA foreign_key_check` 为空）；
6. 两文件作为 review snapshot 与 migrations/core/C0001、migrations/private/P0001 内容一致（diff 为空，除头注外）。

---

## 3. T2 — Schema Constraint Tests（15 个案例）

在临时库中逐项验证（每条：前置数据 → 操作 → 预期结果）：

| # | 案例 | 预期 |
|---|------|------|
| 1 | 插入重复 `entity_uid` | 拒绝（UNIQUE） |
| 2 | 同一 provider/type/identifier 当前有效（valid_to IS NULL）重复 | 拒绝（partial unique） |
| 3 | 同一 ticker 历史重用（valid_to 已关闭 + 新行 valid_to NULL） | 允许 |
| 4 | 同一 dataset 两条 active PRIMARY | 拒绝（partial unique ux_dataset_sources_active_primary） |
| 5 | fallback priority_rank 确定性：同 dataset 同 rank 重复 | 拒绝（UNIQUE(dataset_id, priority_rank)） |
| 6 | 相同 artifact hash、不同 run | 允许（INDEX(content_hash) 非唯一） |
| 7 | 相同 hash、同 run（run_id 非 NULL） | 拒绝（UNIQUE(run_id, content_hash) WHERE run_id IS NOT NULL） |
| 8 | event 多 entity（PRIMARY + TARGET） | 允许 |
| 9 | 同 event 同内容、不同 source（不同 evidence_key） | 允许（DB-D032） |
| 10 | watchlist_item entity_uid 与 instrument_uid 同时非 NULL / 同时 NULL | 拒绝（XOR CHECK） |
| 11 | 同 account + 同 instrument_uid 第二条 OPEN position | 拒绝（partial unique ux_positions_open） |
| 12 | 不同 account 同 instrument_uid 的 OPEN position | 允许 |
| 13 | private DB 可存 core uid 引用（TEXT 列） | 允许（无伪 FK） |
| 14 | 无效 core uid（不存在）经应用 validator | 拒绝（CrossDbReferenceError） |
| 15 | event_analysis 不含 thesis_id / portfolio 字段（schema 层面） | 通过（列集合断言） |

---

## 4. T3 — Migration Runner Tests

1. **顺序执行**：C0001 → C0002 按序应用；
2. **幂等**：重复运行不重复执行（SKIP，schema_migrations 记录不变）；
3. **checksum 保护**：修改已应用 migration 文件内容 → 报错（checksum mismatch），不重放；
4. **失败回滚**：注入失败 SQL 的 C000X → 事务回滚，schema_migrations 无该记录，schema 无部分变更；
5. **dry-run / plan**：`--plan` 不产生任何数据库写入；
6. **core/private 分库**：core 迁移不影响 private history（独立 schema_migrations，DB-D030）；
7. **backup gate**：无有效备份时拒绝执行；
8. **迁移目录命名**：非法文件名（缺前缀/序号非数字）→ 报错。

---

## 5. T4 — Cross-db UID Tests

用 `ensure_entity_uid / ensure_instrument_uid / ensure_event_uid / ensure_analysis_uid`：

1. 存在性命中 → True；
2. 不存在 uid → 抛 `CrossDbReferenceError`（不静默写孤儿）；
3. 格式非法（长度 ≠ 36 / 非 UUID 格式）→ 应用层拒绝；
4. 重建 core.db（导出 → 重建 → 导入）后，同一 uid 仍可命中（UID 稳定）；
5. private 侧写入前校验调用顺序（先 ensure 后 insert）。

---

## 6. T5 — Legacy Migration Tests

基于 M0–M9 规格，用**测试夹具**（构造小型 legacy market.db 副本，含已知 3 天数据）：

1. M0 preflight 全项通过（含 sha256 记录）；
2. M1 备份生成 + raw_artifact 登记 + hash 一致；
3. M2 bootstrap 幂等；
4. M3 entity/instrument 建立、uid 为随机 UUIDv4（断言非 hash(ts_code)）；
5. M4 映射完整性：无未映射 ts_code；
6. M5 3 个 ingest_run 与 fetch_log 一一对应；无对应 run 的 trade_date → ABORT；
7. M6 字段映射正确（vol→LOTS、amount→THOUSAND_CNY、RAW、CNY、ingest_run_id、raw_artifact_id）；
8. M7 V1–V12 全 PASS（含 V12 聚合 tolerance）；
9. Abort 条件逐一触发验证（mapping 缺失 / 行数不符 / 重复键 / hash 不符 / 缺 run / FK 违例）；
10. M8 观察期政策存在（≥20 trading days 且 ≥30 calendar days 取较晚者）；
11. M9 退休门 6 条件 + Berlin 批准才可停止 legacy write；market.db 删除须另行授权；
12. 迁移可逆：按 ingest_run_id 删除 canonical 行 + 重放演练（rollback tested）。

---

## 7. T6 — Privacy Tests

### 7.1 core.db export inspection

导出 core.db 全量内容（模拟未来公开导出）后断言**不存在**：

- account / position / avg_cost / cost basis / quantity
- watchlist reason / watchlist 内容
- investment thesis（title/base/bull/bear/invalidate）
- thesis impact（impact_direction/severity）
- alert routing（channel/rule_ref/delivered_at）
- private raw LLM output（event_thesis_analysis.raw_output）
- API token / password / credential 任何字符串

实现方式：导出全部表 → 扫描表名/列名/采样行 → 断言上述模式零命中。

### 7.2 private.db 安全检查

断言 private.db **不包含**：

- API token / password / credential 字段（schema 层面无此类列）
- 任何 core-only 数据（不复制 core 表，只存 uid 引用）

### 7.3 命名与字段白名单

- core 表名白名单 == FROZEN 17 张；private 表名白名单 == 7 张业务表 + schema_migrations；
- 字段级：`accounts` 无 credential 列；`event_analysis` 无 thesis 列；`events` 无 entity_id 单列（B10）。

---

## 8. 测试执行方式（未来）

- Python stdlib `unittest` + 临时 SQLite 文件（`tempfile.mkdtemp`）；
- 每个测试独立临时库，互不污染；
- 全部测试可 `python3 -m unittest discover tests` 运行；
- CI 前（若引入）先跑 T1/T2/T6 快速集。

---

## 9. Not Done（本轮）

- ❌ 未执行任何测试（未建库）
- ❌ 未编写测试代码
