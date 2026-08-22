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

---

# R1C Phase 1.1 Final Pre-Production Hardening Addendum（2026-08-22）

> R1C Phase 1.1 对 Phase 1 的 4 个 implementation hardening 问题（H1–H4）复查。
> 格式：Severity / Problem / Code Change / Test Evidence / Residual Risk / Blocking?

### C20. Snapshot baseline race elimination（H1）

- **Severity**: HIGH — 已解决
- **Problem**: 旧 `capture_baseline(live)` 查询 live 后关连接再读 bytes 算 hash；`validate_snapshot` 还会 reopen `manifest["source_path"]`（live）比 aggregate —— row_count/hash/snapshot/aggregate 可能来自不同版本，存在并发竞态。
- **Code Change**: 拆分为 `inspect_live_source_health()`（只做 health preflight，`live_source_file_hash_observed` 仅审计）+ `capture_snapshot_baseline()`（从 frozen snapshot 生成 authoritative manifest）+ `validate_snapshot()`（只验证 snapshot 内部，**不再 reopen live**）。删除 `capture_baseline()`。
- **Test Evidence**: T-SNAPSHOT-BASELINE-01（live 后增行+增 fetch_log，migration 仍以 snapshot manifest 6 行为准）；`test_validate_snapshot_does_not_open_live`（删除 live 文件后 validate_snapshot 仍 PASS）。
- **Residual risk**: 低。
- **Blocking?**: No

### C21. Snapshot manifest authority（H1）

- **Severity**: HIGH — 已解决
- **Problem**: migration equality 校验引用 live baseline。
- **Code Change**: manifest 现在包含 `snapshot_path / snapshot_sha256 / row_count / trade_date_distribution / distinct_ts_code / fetch_log_count / latest_fetch_time_raw / ts_code_suffixes / aggregates`，全部从 snapshot 生成；M3–M7 只使用该 manifest。
- **Test Evidence**: T-SNAPSHOT-HASH-01（snapshot_sha256 == sha256(snapshot bytes)，且 != live hash）；T-BASELINE-01（实际 6 行，非 documented 5）。
- **Residual risk**: 低。
- **Blocking?**: No

### C22. stock_basic duplicate detection（H2）

- **Severity**: HIGH — 已解决
- **Problem**: `basic = {row["ts_code"]: row for row in stock_basic}` 静默 last-one-wins，违反 strict mapping gate。
- **Code Change**: 新增 `validate_stock_basic_input()` —— 构造 lookup 前显式扫描 duplicates（`MappingGateError` 含 offending ts_code）并校验每行含 ts_code/name/list_date（缺失/空 → `MappingGateError`）；`build_ts_code_mapping()` 首先调用它。
- **Test Evidence**: T-MAPPING-DUPLICATE-01（600519.SH ×2 → MappingGateError，错误含 "duplicate" 与 ts_code）；T-MAPPING-MISSING-FIELD-01（缺 ts_code/name/list_date 各 → ABORT）；empty ts_code → ABORT。
- **Residual risk**: 低。
- **Blocking?**: No

### C23. Migration checksum raw-byte consistency（H3）

- **Severity**: HIGH — 已解决
- **Problem**: `run_migrations` 用 `path.read_bytes()` 算 checksum，但 `apply_migration` 用 `sql.encode("utf-8")`（read_text 后再编码）—— Windows CRLF/newline normalization 下会不一致，导致已应用 migration 被误判 CHECKSUM_MISMATCH。
- **Code Change**: checksum = `sha256_bytes(path.read_bytes())` **只计算一次**；`sql = raw_bytes.decode("utf-8")` 仅用于执行；`apply_migration` 接收 `checksum` 参数，**不再自行重算**；comparison 与 schema_migrations INSERT 用同一变量。
- **Test Evidence**: T-CHECKSUM-CRLF-01（`\r\n` 字节 APPLIED → 二次 SKIP，无 mismatch；tamper 后 → MigrationChecksumError）；`test_checksum_insert_and_compare_same_value`。
- **Residual risk**: 低。
- **Blocking?**: No

### C24. CRLF checksum stability（H3）

- **Severity**: MEDIUM — 已解决
- **Problem**: CRLF 下 raw bytes 与 text-encoded 不一致。
- **Code Change**: 同上（raw bytes 契约）。
- **Test Evidence**: T-CHECKSUM-CRLF-01 PASS。
- **Residual risk**: 低。
- **Blocking?**: No

### C25. Invalid UTF-8 migration rejection（H3）

- **Severity**: MEDIUM — 已解决
- **Problem**: 非 UTF-8 migration 文件会裸抛 UnicodeDecodeError 或静默 replacement。
- **Code Change**: `raw_bytes.decode("utf-8")` 捕获 `UnicodeDecodeError` → `MigrationFileError`。
- **Test Evidence**: T-MIGRATION-ENCODING-01（`\xff\xfe` bytes → MigrationFileError）。
- **Residual risk**: 低。
- **Blocking?**: No

### C26. CLI all/db-path ambiguity（H4）

- **Severity**: HIGH — 已解决
- **Problem**: `--db all --db-path /tmp/x.db` 会让 C+P migrations 写入同一文件，错误配置。
- **Code Change**: `main()` 在解析参数后、任何迁移前 `parser.error("--db-path cannot be used with --db all; run --db core and --db private separately")`（SystemExit 2，不创建文件、不执行迁移）。
- **Test Evidence**: T-CLI-ALL-DBPATH-01（SystemExit 2，foo.db 不存在）；`--db all --plan --db-path` 同样拒绝；`--db core --db-path` 正常可用。
- **Residual risk**: 低。
- **Blocking?**: No

### C27. Regression suite（H1–H4）

- **Severity**: HIGH — 已解决
- **Problem**: 重构不得破坏既有 62 tests。
- **Code Change**: 仅修实现（H1/H2/H3/H4），未删旧测试；旧测试中引用已移除 `capture_baseline` 的用例改用 snapshot 流程。
- **Test Evidence**: **Ran 77 tests — OK（0 failed / 0 errors / 0 skipped）**。ATOMIC-01/02/03、plan/status no-write、production guard、constraint 17+、frozen source、timezone、privacy 全部继续 PASS。
- **Residual risk**: 低。
- **Blocking?**: No

### R1C Phase 1.1 汇总

| Severity | 数量 | 状态 |
|----------|------|------|
| HIGH | 5（C20 C21 C22 C23 C26 C27 中计 5 项） | 已解决 |
| MEDIUM | 3（C24 C25 + 计数修正） | 已解决 |

**Blocking findings remaining = 0**

**R1C PHASE 1.1 COMPLETE — READY FOR BERLIN APPROVAL OF PHASE 2**（仍不开始 Phase 2）

---

# R1C Phase 1.2 Canonical Date Contract Addendum（2026-08-22）

> R1C Phase 1.2 对 canonical date contract 的专项复查（D1–D5）。
> 格式：Severity / Problem / Code Change / Test Evidence / Residual Risk / Blocking?

### C28. Legacy trade_date canonical normalization（D1）

- **Severity**: HIGH — 已解决
- **Problem**: legacy daily_bars.trade_date 为 compact YYYYMMDD（20260814）；fixture migrator 原样写入 canonical，违反 canonical contract（YYYY-MM-DD），且 V2 测试用 raw==raw 错误 oracle 掩盖。
- **Code Change**: `migrate_bars_from_snapshot` 对 raw trade_date 调 `normalize_date()` 后写 canonical；`run_by_date` lookup 仍用 raw key（fetch_log 与 daily_bars 同为 YYYYMMDD）。新增 `scripts/date_utils.py`（normalize_date / DateNormalizationError / is_canonical_date）。
- **Test Evidence**: T-CANONICAL-TRADE-DATE-01（canonical dates == {2026-08-14, 2026-08-17, 2026-08-20}；`assertNotIn("20260814")`）。
- **Residual risk**: 低。
- **Blocking?**: No

### C29. stock_basic list_date normalization（D2）

- **Severity**: HIGH — 已解决
- **Problem**: Tushare stock_basic.list_date 常见 YYYYMMDD（19910403）；fixture 用 YYYY-MM-DD 太“干净”，未暴露 provider 格式问题。
- **Code Change**: `validate_stock_basic_input` 要求 list_date 可被 normalize_date() 解析（catch DateNormalizationError → MappingGateError）；`build_ts_code_mapping` 输出 `list_date`（canonical）+ `provider_list_date_raw`；`build_stock_basic_fixture` 默认 list_date 改为 `20100101`（provider raw 风格）。M3 写 instruments.listing_date 与 instrument_identifiers.valid_from 一律用 canonical list_date。
- **Test Evidence**: T-CANONICAL-LIST-DATE-01（20010827 → mapping/listing_date/valid_from == 2001-08-27）；T-STOCK-BASIC-DATE-INVALID-01/02（20260230 / abc → MappingGateError）；valid compact accepted。
- **Residual risk**: 低。
- **Blocking?**: No

### C30. Invalid calendar-date rejection（D3）

- **Severity**: HIGH — 已解决
- **Problem**: 字符串切片式格式化会把 20260230 当作合法日期。
- **Code Change**: `normalize_date` 用 `datetime.strptime` 严格解析（YYYYMMDD / YYYY-MM-DD），非法日历日期（20260230、20261340、20260229 非闰年、abcdefgh、2026/08/14、空/None/空白）→ DateNormalizationError（错误含原始输入）。
- **Test Evidence**: test_date_utils.py T-DATE-01/02/03 + T-DATE-INVALID-01/02/03/04（全过）。
- **Residual risk**: 低。
- **Blocking?**: No

### C31. V2 validation oracle correction（D4）

- **Severity**: HIGH — 已解决
- **Problem**: validate_migration V2 用 `canon_dates == legacy_dates`（raw==raw），错误格式互相匹配仍 PASS。
- **Code Change**: 改为 `canon_dates == {normalize_date(d) for d in legacy_dates}`（normalized expectation vs canonical actual）。
- **Test Evidence**: T-CANONICAL-TRADE-DATE-01（若 canonical 仍是 20260814 则 FAIL）。
- **Residual risk**: 低。
- **Blocking?**: No

### C32. V12 aggregate date normalization（D4）

- **Severity**: MEDIUM — 已解决
- **Problem**: V12 直接比较 legacy_agg（raw date key）与 canon_agg（canonical date key），日期格式不同则恒不匹配或掩盖。
- **Code Change**: `expected_legacy_agg = {(normalize_date(r[0]), r[1], r[2]) for r in legacy_agg}`，与 canon_agg 比较；manifest.aggregates 改为 JSON-safe dict（keyed by raw trade_date → {sum_volume, sum_turnover}），validate_snapshot 同步。
- **Test Evidence**: T-MANIFEST-JSON-01（json.dumps(manifest, sort_keys=True) 成功）；既有 V12 断言全过。
- **Residual risk**: 低。
- **Blocking?**: No

### C33. JSON-safe snapshot manifest（D4）

- **Severity**: MEDIUM — 已解决
- **Problem**: manifest["aggregates"] 原为 set[tuple]，Python 内存可用但无法 json.dumps。
- **Code Change**: aggregates → `{raw_trade_date: {"sum_volume": ..., "sum_turnover": ...}}`；validate_snapshot 的 aggregate_self_consistency 同步。
- **Test Evidence**: T-MANIFEST-JSON-01 PASS。
- **Residual risk**: 低。
- **Blocking?**: No

### C34. Regression suite（D1–D5）

- **Severity**: HIGH — 已解决
- **Problem**: 重构不得破坏既有 77 tests。
- **Code Change**: 仅修实现（normalize 边界），未删旧测试。
- **Test Evidence**: **Ran 99 tests — OK（0 failed / 0 errors / 0 skipped）**。H1–H4（snapshot baseline / duplicate stock_basic / CRLF checksum / CLI ambiguity / production guard）、ATOMIC、privacy、timezone 全部继续 PASS。
- **Residual risk**: 低。
- **Blocking?**: No

### R1C Phase 1.2 汇总

| Severity | 数量 | 状态 |
|----------|------|------|
| HIGH | 5（C28 C29 C30 C31 C34 中计 5 项） | 已解决 |
| MEDIUM | 2（C32 C33） | 已解决 |

**Blocking findings remaining = 0**

**R1C PHASE 1.2 COMPLETE — READY FOR BERLIN APPROVAL OF PHASE 2**（仍不开始 Phase 2）
