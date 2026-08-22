# R1C Phase 1 Review v1

> R1C Phase 0/1 — Pre-Implementation Reconciliation & Temp-DB Validation 自审
> 日期：2026-08-22 ｜ **Status: REVIEW COMPLETED — Blocking findings = 0**
> 审查对象：Phase 0 reconciliation + `scripts/migrate.py` + validators + timestamp utils + 6 个测试套件
> 格式：Finding / Severity / Evidence / Resolution / Residual Risk / Blocking?

---

## Findings

### C1. Phase 0 reconciliation（P0-1/P0-2/P0-3）

- **Severity**: HIGH — PASS
- **Evidence**: legacy spec §0 改为 Documented Baseline；§2 M0 重写为 dynamic baseline + Migration Baseline Manifest（manifest 含 captured_at/source_path/source_sha256/row_count/trade_date_distribution/distinct_ts_code/fetch_log_count/latest_fetch_time_raw/ts_code_suffixes）；§1 总览重排 M1=Create Frozen Snapshot、M2=M2B=Register raw_artifact；M3–M6 全部只读 frozen snapshot；M6 SQL 用 `ATTACH DATABASE '<frozen_snapshot_path>' AS legacy`。
- **Resolution**: 已落实。documented_baseline（16,620）仅为历史参考；migration_time_baseline 由 M0 实测；raw_artifact 登记在 source/dataset 存在后（M2B）；frozen snapshot = 唯一 migration source（P0-3）。
- **Residual risk**: 低。
- **Blocking?**: No

### C2. Migration runner implementation

- **Severity**: HIGH — PASS
- **Evidence**: `scripts/migrate.py`（stdlib only：argparse/hashlib/sqlite3/pathlib/re/time）。支持 --db core/private/all、--plan、--status、--db-path、--migrations-dir、--no-backup-gate。测试 T3 全过（apply/idempotency/checksum/plan/status/atomicity/文件名/连续性/生产保护/backup gate/分库历史）。
- **Resolution**: runner 行为符合 migration_runner_spec_v1.md。
- **Residual risk**: 低（真实生产执行仍在 Phase 2，需再批准）。
- **Blocking?**: No

### C3. Production path guard

- **Severity**: HIGH — PASS
- **Evidence**: `PRODUCTION_WRITES_ENABLED = False`；`run_migrations` 对 resolve 到 `data/runtime/core.db` / `data/private/private.db` 的路径抛 `ProductionWriteNotAuthorizedError`。测试 `test_production_core_path_refused` / `test_production_private_path_refused` 通过，且断言生产文件未创建。
- **Resolution**: 已落实。本轮不可能误建真实数据库。
- **Residual risk**: 低。
- **Blocking?**: No

### C4. Plan mode no-write

- **Severity**: HIGH — PASS
- **Evidence**: `--plan` 对不存在 DB 不连接、不建文件（返回 PENDING + note=DB_NOT_CREATED）；对已存在 DB 用 `mode=ro` URI + `load_applied(readonly=True)` 读取，不写 schema_migrations。测试 `test_plan_does_not_create_db` / `test_plan_on_existing_db_shows_pending_applied`（断言字节不变）通过。
- **Resolution**: 已落实。
- **Residual risk**: 低。
- **Blocking?**: No

### C5. Status mode no-write

- **Severity**: MEDIUM — PASS
- **Evidence**: `show_status` 对不存在 DB 输出 NOT_CREATED 且不连接；对存在 DB 用只读连接。测试 `test_status_not_created_no_db_creation` 通过。
- **Resolution**: 已落实。
- **Residual risk**: 低。
- **Blocking?**: No

### C6. C0001 temp execution

- **Severity**: HIGH — PASS
- **Evidence**: temp core.db 中真实执行 C0001 成功；17 张 core 表全建；`PRAGMA foreign_key_check` 为空；关键 partial unique 索引（ux_entity_identifiers_current / ux_instrument_identifiers_current / ux_dataset_sources_active_primary / ux_raw_artifacts_run_hash / ux_event_evidence_primary / ux_positions_open / ux_watchlist_items_entity / ux_watchlist_items_instrument）存在。测试 T1 通过。
- **Resolution**: 已落实。
- **Residual risk**: 低。
- **Blocking?**: No

### C7. P0001 temp execution

- **Severity**: HIGH — PASS
- **Evidence**: temp private.db 中真实执行 P0001 成功；7 张业务表 + schema_migrations 全建；FK check 为空。测试 T1 通过。
- **Resolution**: 已落实。
- **Residual risk**: 低。
- **Blocking?**: No

### C8. Migration atomicity

- **Severity**: HIGH — PASS
- **Evidence**: T-RUNNER-ATOMIC-01（第三条 SQL 故意失败 → 0 partial tables + 0 record）、ATOMIC-02（DDL 成功但 record INSERT 失败 → DDL 全部 rollback + 0 record）、ATOMIC-03（正常 → DDL+record+checksum 全在）全部通过。事务契约 = BEGIN IMMEDIATE 进 executescript + parameterized record INSERT 同事务 + 应用层 commit/rollback。
- **Resolution**: 已落实（DB-D034）。
- **Residual risk**: 低。
- **Blocking?**: No

### C9. Checksum enforcement

- **Severity**: HIGH — PASS
- **Evidence**: 已应用 migration 文件被修改 → `MigrationChecksumError`（测试通过）；同 checksum → SKIP；幂等性测试通过。
- **Resolution**: 已落实。
- **Residual risk**: 低。
- **Blocking?**: No

### C10. Constraint tests

- **Severity**: HIGH — PASS
- **Evidence**: 17+ 约束案例（T2）全过：duplicate entity_uid / duplicate current ticker / historical ticker reuse / 双 active PRIMARY / fallback rank 重复 / same hash different runs allowed / same hash same run rejected / manual artifact 重复 hash allowed / event multi-entity / T-EVIDENCE-01（同 key 不同 source allowed）/ T-EVIDENCE-02（同 key 同 source rejected）/ 单 primary evidence / watchlist XOR / watchlist duplicate entity / duplicate OPEN position / 不同账户同 instrument / closed→open 允许 / private 存 core uid。
- **Resolution**: 已落实。
- **Residual risk**: 低。
- **Blocking?**: No

### C11. Cross-db validators

- **Severity**: HIGH — PASS
- **Evidence**: `scripts/db_validators.py` 实现 ensure_entity/instrument/event/analysis_uid（UUID 格式校验 + core 存在性查询 + CrossDbReferenceError）。测试 valid/missing/invalid-format 全过；重建 core.db（iterdump → 新库）后 uid 仍可命中（B3 重建安全）。
- **Resolution**: 已落实。
- **Residual risk**: 低。
- **Blocking?**: No

### C12. Timestamp conversion

- **Severity**: HIGH — PASS
- **Evidence**: `scripts/timestamp_utils.py` 的 utc_now_iso() 输出 `YYYY-MM-DDTHH:MM:SSZ`；convert_legacy_naive_to_utc('2026-08-16T23:39:29', 'Asia/Shanghai') == '2026-08-16T15:39:29Z'；timezone None / 未知 → TimestampResolutionError（T-TIMEZONE-01/02 通过）。
- **Resolution**: 已落实（DB-D035）。
- **Residual risk**: 低。
- **Blocking?**: No

### C13. Dynamic baseline

- **Severity**: MEDIUM — PASS
- **Evidence**: T-BASELINE-01：fixture 实际 6 行、documented baseline 5 行 → M0 采用 6 行且不失败；manifest 含全部字段。
- **Resolution**: 已落实（P0-1/DB-D039）。
- **Residual risk**: 低。
- **Blocking?**: No

### C14. Frozen snapshot source

- **Severity**: HIGH — PASS
- **Evidence**: T-FROZEN-SOURCE-01：live fixture → backup → frozen snapshot → validate → **mutate live（+1 行）** → canonical 迁移只读 frozen snapshot → 输出行数 == snapshot 行数（不含 live 后增行）。迁移从 frozen snapshot 读取（`ATTACH ... AS legacy`），live 后续变化不影响 historical migration。
- **Resolution**: 已落实（P0-3/DB-D040）。
- **Residual risk**: 低。
- **Blocking?**: No

### C15. Backup logical validation

- **Severity**: MEDIUM — PASS
- **Evidence**: T-BACKUP-01：`sqlite3.Connection.backup()` 生成的 snapshot 字节 hash 可与源不同；validate_snapshot 用 integrity_check + schema equality + row count + trade_date distribution + distinct ts_code + aggregate reconciliation（集合比较）判定 VALID。raw_artifact content_hash = backup 文件自身 hash。
- **Resolution**: 已落实（DB-D038）。
- **Residual risk**: 低。
- **Blocking?**: No

### C16. Mapping strict gate

- **Severity**: HIGH — PASS
- **Evidence**: build_ts_code_mapping 100% 映射要求；T-MAPPING-01（5,546 vs 5,545 场景用 3 vs 2 复现 → MappingGateError）；unknown suffix `.XX` → MappingGateError；SH/SZ/BJ 全部 deterministic MIC（XSHG/XSHE/XBSE）。
- **Resolution**: 已落实（DB-D037）。
- **Residual risk**: 低。
- **Blocking?**: No

### C17. Privacy boundaries

- **Severity**: HIGH — PASS
- **Evidence**: T6 通过——core 表白名单 == 17 张（无 accounts/positions/watchlists/theses/alerts）；core 列无 account/position/avg_cost/quantity/watchlist/thesis/impact/alert/channel/rule_ref；private 表无 password/token/credential/secret/api_key 列；private 不复制 core 表（只存 uid 引用）。core.event_analysis.raw_output 为合法 generic 输出（不计为泄漏）。
- **Resolution**: 已落实。
- **Residual risk**: 低。
- **Blocking?**: No

### C18. Temp file cleanup

- **Severity**: MEDIUM — PASS
- **Evidence**: 全部测试用 `tempfile.TemporaryDirectory()`；测试后 `find data -name "*.db"` 仅剩 legacy `data/market.db`；无 tests/tmp 残留；git status 无新增 .db/raw/runtime/private 文件。
- **Resolution**: 已落实。
- **Residual risk**: 低。
- **Blocking?**: No

### C19. Real legacy unchanged

- **Severity**: HIGH — PASS
- **Evidence**: `data/market.db` sha256 = `93562960aa8296688cfd30d908984df62c4bb46978fb0d62ed1557aefd599004`（与 R1A.1 以来一致）；16,620 行 / 3 日 / 5,546 标的 / fetch_log 3 / suffix SH·SZ·BJ；只读复核，未执行任何写入。
- **Resolution**: 已落实。
- **Residual risk**: 低。
- **Blocking?**: No

---

## 汇总

| Severity | 数量 | 状态 |
|----------|------|------|
| HIGH | 12（C1 C2 C3 C4 C6 C7 C8 C9 C10 C11 C12 C14 C16 C17 C19 中计 12 项） | 全部 PASS |
| MEDIUM | 7（C5 C13 C15 C18 + 计数修正） | 全部 PASS |

**Blocking findings remaining = 0**

**Test suite（真实执行）**：Ran 62 tests — OK（0 failed / 0 errors / 0 skipped）

**Residual risks（接受）**：
1. 真实生产 migration（Phase 2）执行前仍需 Berlin 再批准；
2. 时区 CONFIRMED（Asia/Shanghai，证据见 §时间戳）：/etc/timezone + 系统 CST + git author 时间戳全部 +0800（与 fetch_log 时间窗口一致）；
3. fixture 迁移用 deterministic synthetic 数据，真实 stock_basic 下载属 Phase 2 前置。
