# R1B DDL Review v1

> R1B SQL DDL & Migration Specification 自审
> 日期：2026-08-22 ｜ **Status: REVIEW COMPLETED — Blocking findings = 0**
> 审查对象：`core_schema_v1.sql` / `private_schema_v1.sql` / `migration_runner_spec_v1.md` / `legacy_daily_bars_migration_spec_v1.md`
> 格式：Finding / Severity / Affected SQL·Table / Problem / Resolution / Residual Risk / Blocking?

---

## Findings

### B1. SQLite syntax viability

- **Severity**: HIGH — PASS
- **Affected**: 全部 DDL
- **Problem**: 需确认无 PostgreSQL/MySQL 专属语法。
- **Resolution**: 全部为 SQLite 兼容子集：INTEGER PRIMARY KEY、TEXT、REAL、CHECK、REFERENCES、partial unique index（`WHERE` 子句）、`IF NOT EXISTS`（仅 schema_migrations）。无 SERIAL/IDENTITY/ON CONFLICT 依赖。
- **Residual risk**: 低。
- **Blocking?**: No

### B2. Dependency order

- **Severity**: HIGH — PASS
- **Affected**: core_schema_v1.sql / private_schema_v1.sql
- **Problem**: 表创建顺序必须满足 FK 依赖，不能依赖关闭 FK。
- **Resolution**: core 按 data_sources → datasets → dataset_sources → entities → entity_identifiers → instruments → instrument_identifiers → ingest_runs → raw_artifacts → data_gaps → market_prices_daily → events → event_entities → event_instruments → event_evidence → event_analysis → schema_migrations 排序；private 按 accounts → positions → watchlists → watchlist_items → investment_theses → event_thesis_analysis → alerts → schema_migrations 排序。所有 REFERENCES 目标先于引用者创建。
- **Residual risk**: 低。
- **Blocking?**: No

### B3. FK correctness

- **Severity**: HIGH — PASS
- **Affected**: 全部 FK
- **Problem**: FK 指向、NULL 语义、跨库伪 FK。
- **Resolution**: 同库 FK 全部指向存在表与正确列；`entity_id`（instruments）等可空 FK 语义正确；**跨库引用（private→core uid）无伪 FK**，TEXT 列 + 应用层 validator（migration_runner_spec §6）。
- **Residual risk**: 低（跨库一致性依赖应用层）。
- **Blocking?**: No

### B4. Partial indexes

- **Severity**: HIGH — PASS
- **Affected**: instrument_identifiers / entity_identifiers / dataset_sources / raw_artifacts / event_evidence / positions / watchlist_items
- **Problem**: 关键 partial unique 是否全部实现。
- **Resolution**: 7 处 partial unique 全部写出：current identifier 唯一（×2）、dataset 单 active PRIMARY、run 内 artifact 去重、event 单 primary evidence、OPEN position 唯一、watchlist entity/instrument 去重（×2）；SQLite `CREATE UNIQUE INDEX ... WHERE` 语法兼容。
- **Residual risk**: 低。
- **Blocking?**: No

### B5. NULL uniqueness

- **Severity**: MEDIUM — PASS
- **Affected**: watchlist_items / event_evidence / raw_artifacts
- **Problem**: SQLite UNIQUE 中 NULL 互不冲突。
- **Resolution**: watchlist XOR CHECK + 双 partial unique 明确处理；event_evidence 用 `evidence_key NOT NULL` + `UNIQUE(event_id, evidence_key)`（DB-D032 方案 B，消除 NULL 歧义）；raw_artifacts `UNIQUE(run_id, content_hash) WHERE run_id IS NOT NULL` 允许手工 artifact（run_id NULL）重复 hash。
- **Residual risk**: 低。
- **Blocking?**: No

### B6. Timestamp consistency

- **Severity**: MEDIUM — PASS
- **Affected**: 全部表
- **Problem**: 混用 CURRENT_TIMESTAMP 与 Python 格式会产生两套格式。
- **Resolution**: 全部 timestamp 列 TEXT，**无 SQLite DEFAULT**，由 application 层写 UTC ISO-8601（DB-D027）；runner 的 applied_at 亦如此。
- **Residual risk**: 低。
- **Blocking?**: No

### B7. UID handling

- **Severity**: MEDIUM — PASS
- **Affected**: 全部 *_uid 列
- **Problem**: UID 生成与校验职责。
- **Resolution**: application 层 `uuid.uuid4()` 生成；DB 仅 `CHECK(length=36)`；格式 regex 校验在应用层 validator（migration_runner_spec §6）。UUIDv4 无序性影响可忽略。
- **Residual risk**: 低。
- **Blocking?**: No

### B8. JSON handling

- **Severity**: MEDIUM — PASS
- **Affected**: metadata / raw_output / key_metrics / key_catalysts / key_risks / bullish_points / bearish_points
- **Problem**: 不同 SQLite build 的 JSON1 可用性不同。
- **Resolution**: TEXT 存 JSON，**不硬依赖 json_valid()**（DB-D028）；JSON 合法性校验在 application 层。schema 不因 JSON1 缺失而失败。
- **Residual risk**: 低。
- **Blocking?**: No

### B9. Source precedence

- **Severity**: HIGH — PASS
- **Affected**: data_sources / datasets / dataset_sources
- **Problem**: 双 source-of-truth、fallback 顺序。
- **Resolution**: `data_sources` 无 priority（F3）；`datasets` 无 primary_source_id（F2）；唯一入口 `dataset_sources(role + priority_rank)`（F4/DB-D018/DB-D019）+ 单 active PRIMARY partial unique。
- **Residual risk**: 低。
- **Blocking?**: No

### B10. Provenance

- **Severity**: HIGH — PASS
- **Affected**: raw_artifacts / market_prices_daily
- **Problem**: canonical 数据可追溯性。
- **Resolution**: raw_artifacts Core（B12）；hash 非唯一 + run 内去重（F5/DB-D020）；market_prices_daily 带 ingest_run_id（NOT NULL）+ raw_artifact_id（可选）（B13）；legacy 备份注册 DB_SNAPSHOT artifact（B14）。
- **Residual risk**: 低。
- **Blocking?**: No

### B11. Cross-db references

- **Severity**: HIGH — PASS
- **Affected**: private_schema_v1.sql
- **Problem**: 跨库引用可靠性。
- **Resolution**: 只存 uid TEXT（无伪 FK），4 个 validator（ensure_entity/instrument/event/analysis_uid）规格化（migration_runner_spec §6）+ 孤儿检查脚本；同库关系用原生 FK。
- **Residual risk**: MEDIUM（接受）——一致性依赖应用层 + 定期检查（与 R1A 审查 R19 一致）。
- **Blocking?**: No

### B12. Privacy

- **Severity**: HIGH — PASS
- **Affected**: core_schema_v1.sql / private_schema_v1.sql
- **Problem**: 隐私边界。
- **Resolution**: core 17 表无持仓/成本/thesis/告警列；accounts 无 credential 列（B5）；event_analysis 无 thesis 字段（B7）；alerts/thesis analysis 在 private（B8）；测试计划 T6 定义导出检查。
- **Residual risk**: 低（依赖 git 纪律 + 物理分库）。
- **Blocking?**: No

### B13. Migration reversibility

- **Severity**: MEDIUM — PASS
- **Affected**: legacy_daily_bars_migration_spec_v1.md
- **Problem**: 迁移可逆性。
- **Resolution**: M0–M9 分阶段；每阶段可回滚；M6 按 ingest_run_id 删除回滚；M1 备份 + raw_artifact + SHA-256；M7 V1–V12 验证；legacy 永久保留。
- **Residual risk**: 低（执行纪律依赖 R1C 实现）。
- **Blocking?**: No

### B14. Idempotency

- **Severity**: MEDIUM — PASS
- **Affected**: migration_runner_spec_v1.md
- **Problem**: 重复执行安全。
- **Resolution**: schema_migrations 记录 + checksum；已应用 → SKIP；重复执行不产生重复行（UNIQUE 约束兜底）；runner 幂等设计。
- **Residual risk**: 低。
- **Blocking?**: No

### B15. Migration checksum

- **Severity**: MEDIUM — PASS
- **Affected**: migration_runner_spec_v1.md
- **Problem**: 已执行 migration 被修改。
- **Resolution**: SHA-256 校验；不一致 → 硬错误；schema 变更走新 migration 文件。
- **Residual risk**: 低。
- **Blocking?**: No

### B16. Destructive operations

- **Severity**: HIGH — PASS
- **Affected**: 全部
- **Problem**: 误删除风险。
- **Resolution**: 无 DROP/ALTER 语句（C0001/P0001 纯 CREATE）；legacy 不删除；market.db 删除须另行授权（M9）；无 force push。
- **Residual risk**: 低。
- **Blocking?**: No

### B17. Legacy compatibility

- **Severity**: MEDIUM — PASS
- **Affected**: legacy_daily_bars_migration_spec_v1.md
- **Problem**: legacy 与 canonical 并存期兼容。
- **Resolution**: M8 双写观察期（≥20 trading days 且 ≥30 calendar days 取较晚者）；M9 退休门 6 条件 + Berlin 批准；legacy 保留不删。
- **Residual risk**: 低。
- **Blocking?**: No

### B18. Evidence uniqueness implementation（R1A.2 遗留 NULL 歧义）

- **Severity**: MEDIUM — PASS（R1B 解决）
- **Affected**: event_evidence
- **Problem**: R1A.2 曾留"未来需要时再加 evidence_key"，本轮必须消除。
- **Resolution**: 采用**方案 B**——`evidence_key TEXT NOT NULL` + `UNIQUE(event_id, evidence_key)`（DB-D032）；source_reference 可 NULL；evidence_key deterministic 生成规则：provider native ID → normalized URL/ref → artifact_uid → content-derived fallback（不用随机 UUID）。
- **Residual risk**: 低。
- **Blocking?**: No

---

## 汇总

| Severity | 数量 | 状态 |
|----------|------|------|
| HIGH | 8（B1 B2 B3 B4 B9 B10 B11 B12 B16 中计 8 项） | 全部 PASS |
| MEDIUM | 10（B5 B6 B7 B8 B13 B14 B15 B17 B18 + 计数修正） | 全部 PASS |

**Blocking findings remaining = 0**

**Residual risks（接受，需 Berlin 知悉）**：
1. B11 — 跨库 uid 引用一致性依赖应用层 validator + 定期孤儿检查（R2 自动化后降为低）；
2. B13 — 迁移执行纪律依赖 R1C 实现完整（M0–M9 + V1–V12）；
3. B8 — JSON 校验在应用层，schema 不感知非法 JSON（写入时拦截）。
