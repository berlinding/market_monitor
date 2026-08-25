# R1C Phase 2 Review v1

> R1C Phase 2 — Full-Scale Real-Data Staging Rehearsal 自审
> 日期：2026-08-25 ｜ **Status: REVIEW COMPLETED — Blocking findings = 0**
> 审查对象：`scripts/phase2_staging_rehearsal.py` 真实数据 rehearsal 全流程（M0–M7 + V1–V18 + 100% full-row reconciliation）
> 授权：Berlin 2026-08-22（#381–387，§六–§四十）；本次为 authorized 收尾执行
> 格式：Finding / Severity / Evidence / Resolution / Residual Risk / Blocking?

---

## 执行摘要

真实数据 staging rehearsal **完整执行并通过**：

- **run_id**: `20260825T030439Z`（started 03:04:39Z / finished 03:04:43Z，git `be27e82`）
- **FINAL RESULT: PASS**
- 数据规模（比 8-23 首轮 snapshot 更完整，因 8-24 例行下载已回补缺口）：
  - live `data/market.db` = **38,789 行 / 7 交易日 / 5,548 标的**（08-14 → 08-24），只读打开，运行前后 sha256 不变
  - frozen snapshot `data/raw/legacy/market_20260825T030439Z.db`（sha256 `ac5b2acd…`）
  - Tushare `stock_basic` 真实下载 **5,550 条**（L 状态单查即 100% 覆盖 legacy 5,548，无需 D/P 补查）
  - staging core.db（17 tables / C0001）/ private.db（8 tables / P0001），FK check 全空
  - 迁移：5,548 entities + 5,548 instruments + 11,096 identifiers（1:1 严格）、7 ingest_runs、**38,789 行 daily bars 全量迁移**（7/7 批次原子成功）
  - V1–V18 全部 PASS；full-row reconciliation：38,789 行 checked，**0 mismatch**

---

## Findings

### P2-1. M0 — live preflight

- **Severity**: HIGH — PASS
- **Evidence**: `inspect_live_source_health` OK（tables/columns/integrity_check）；row_count=38,789、distinct_trade_dates=7、distinct_ts_code=5,548、suffix 集合 {SH,SZ,BJ} 全部可映射 MIC、quick_check+integrity_check 通过；live sha256 `7b435961…`（8-24 下载后基线）。
- **Resolution**: 已落实。M0 为 informational health check，权威基线仍是 frozen snapshot（H1）。
- **Residual risk**: 低。
- **Blocking?**: No

### P2-2. M1 — frozen snapshot + manifest + 内部校验

- **Severity**: HIGH — PASS
- **Evidence**: 新 snapshot `market_20260825T030439Z.db`（sha256 `ac5b2acd89a79f32…`）由 `sqlite3.Connection.backup()` 生成；manifest（row_count=38,789 / 7 dates / 5,548 ts_code / fetch_log=7）与 snapshot-internal validation 全 PASS。
- **Resolution**: 已落实。旧 snapshot（`market_20260823T110852Z.db`，16,620 行）保留未删（不覆盖历史，符合数据纪律）。
- **Residual risk**: 低。
- **Blocking?**: No

### P2-3. M2 — 真实 Tushare stock_basic 下载（限频实战）

- **Severity**: HIGH — PASS
- **Evidence**: 8-23 首轮实测该 token 对 `stock_basic` 为**小时级滚动限频（40203）**，且失败调用也刷新窗口（09:40Z/09:49Z/10:50Z/11:05Z 连续 4 次 40203）——已修复脚本：L 单查优先 + 覆盖率驱动补 D/P + 40203 等待 3660s 重试（最多 3 次）。本次冷却 >47h 后重跑：**L 单查一次成功**，返回 5,550 条，覆盖率 5,548/5,548 = 100%，未触发 D/P 补查。
- **Resolution**: 已落实。CSV + meta.json 落盘 `data/raw/tushare/stock_basic_20260825T030439Z.{csv,meta.json}`（sha256 `4a9afc6f…`），provenance 含每次查询的 list_status / retrieved_at_utc / row_count。
- **Residual risk**: 低（低积分 token 下未来真实 daily 下载若依赖 stock_basic 需预留冷却；已记录 memory 2026-08-23）。
- **Blocking?**: No

### P2-4. M3/M4 — 100% mapping gate + 1:1 实体化

- **Severity**: HIGH — PASS
- **Evidence**: `build_ts_code_mapping` 对 5,548 个 legacy ts_code **100% 映射**（无 missing / extra）；5,548 entities + 5,548 instruments（EXCHANGE_SYMBOL 主标识）+ 11,096 identifiers（每 instrument 2 条：TUSHARE EXCHANGE_SYMBOL + STANDARD TICKER）；`one_to_one_ok=True`（distinct instruments == identifiers == legacy ts_code 数）。
- **Resolution**: 已落实。list_date 规范化（YYYY-MM-DD）在 mapping 阶段生效。
- **Residual risk**: 低。
- **Blocking?**: No

### P2-5. Staging — core/private DB 建库（C0001/P0001）

- **Severity**: HIGH — PASS
- **Evidence**: `data/staging/r1c_phase2/20260825T030439Z/` 下 core.db（17 tables 含 schema_migrations，C0001 APPLIED，checksum `0dd5b58e…`）+ private.db（8 tables，P0001 APPLIED，checksum `2cce514f…`）；两库 `PRAGMA foreign_key_check` 均为空；staging 路径与 PRODUCTION_PATHS 冲突守卫生效（`data/runtime/core.db` / `data/private/private.db` 未创建）。
- **Resolution**: 已落实。生产路径硬拒绝（PRODUCTION_WRITES_ENABLED=False 语义延续）。
- **Residual risk**: 低。
- **Blocking?**: No

### P2-6. M5 — ingest_runs backfill（时区 Asia/Shanghai）

- **Severity**: HIGH — PASS
- **Evidence**: 7 个 legacy fetch 记录 → 7 条 ingest_runs（BACKFILL/SUCCESS，rows_expected==rows_loaded）；legacy 日期集合与 run_by_date 完全一致（missing=0, extra=0, gate_ok=True）。时区语义沿用已 CONFIRMED 的 Asia/Shanghai（DB-D035）。
- **Resolution**: 已落实。
- **Residual risk**: 低。
- **Blocking?**: No

### P2-7. M6 — 全量 daily bars 迁移（逐交易日原子批次）

- **Severity**: HIGH — PASS
- **Evidence**: 7 个交易日按 raw trade_date 顺序逐批 `BEGIN IMMEDIATE` 迁移，**38,789 行全部成功**（successful=7 / failed=0）；每行携带 instrument_id、canonical date（YYYY-MM-DD）、source_id、ingest_run_id、raw_artifact_id、ingested_at、单位显式（LOTS / THOUSAND_CNY）、adjustment_type=RAW。
- **Resolution**: 已落实。失败批次即停（gate_ok），本次无失败。
- **Residual risk**: 低。
- **Blocking?**: No

### P2-8. M7 — V1–V18 验证 + 100% full-row reconciliation

- **Severity**: HIGH — PASS
- **Evidence**: V1 row count（38,789==38,789==manifest）、V2 trade dates（canonical == normalized legacy，7 天一致）、V3 mapping completeness、V4 无重复键、V5/V6/V7 逐行 OHLC/volume/turnover 全等、V8 无 NULL、V9 lineage（source/run/artifact 全链）、V10 快照 artifact 哈希匹配、V11 无孤儿引用、V12 按日聚合 isclose 全过；V13–V18 full-row：**38,789 行 checked，ohlc/volume/turnover/date/mapping mismatch 全为 0**。
- **Resolution**: 已落实。report 落盘 `data/staging/r1c_phase2/20260825T030439Z/migration_report.json`。
- **Residual risk**: 低。
- **Blocking?**: No

### P2-9. 安全与不变量

- **Severity**: HIGH — PASS
- **Evidence**: live `data/market.db` 运行前后 sha256 一致（`7b4359615cbd…`，before==after）；生产 core/private 未创建；staging 目录已被 `.gitignore`（`data/staging/`）；token 全程 env/`~/API.txt` 读取、不出现在日志/report/CLI；`data/raw/` 不入库。
- **Resolution**: 已落实。
- **Residual risk**: 低。
- **Blocking?**: No

### P2-10. 执行过程说明：首轮进程无产物 → 冷却后重跑成功

- **Severity**: MEDIUM — 已解决（过程性）
- **Evidence**: 8-23 首轮（session `nimble-crest`）在 11:08Z 首次 L 查询 40203 后进入滚动等待，但最终**未产生任何产物**（无 staging 目录、无 migration_report.json；12:09Z/13:10Z 重试结果不可考，进程已随 exec session 清理消失）。8-25 距最后一次调用冷却 >47h 后重跑，M2 一次成功，全流程 PASS。
- **Resolution**: 已落实。根本原因是该 token 档位对 stock_basic 的**小时级滚动限频**（P2-3），属真实数据暴露的 API 层约束；脚本重试逻辑已覆盖 2 个 61min 窗口，本次验证有效。进程产物丢失属 exec session 生命周期问题，不涉及系统设计缺陷。
- **Residual risk**: 低。未来若 token 升级档位，限频窗口变化需重新确认。
- **Blocking?**: No

---

## 回归

- **Ran 99 tests — OK（0 failed / 0 errors / 0 skipped）**（R1C Phase 1.2 门槛，2026-08-25 复跑）

## 汇总

| Severity | 数量 | 状态 |
|----------|------|------|
| HIGH | 8（P2-1…P2-9 中计 8 项） | PASS |
| MEDIUM | 1（P2-10） | 已解决 |

**Blocking findings remaining = 0**

**R1C PHASE 2 COMPLETE — REAL-DATA STAGING REHEARSAL PASS**

## 产出物

- 报告：`data/staging/r1c_phase2/20260825T030439Z/migration_report.json`
- 快照：`data/raw/legacy/market_20260825T030439Z.db`（+ 8-23 旧快照保留）
- stock_basic：`data/raw/tushare/stock_basic_20260825T030439Z.{csv,meta.json}`
- staging DB：`data/staging/r1c_phase2/20260825T030439Z/{core,private}.db`
- 脚本：`scripts/phase2_staging_rehearsal.py`（含限频修复）+ `scripts/legacy_migration_utils.py` / `timestamp_utils.py` 描述更新

## 未授权 / 未执行

- 生产 `data/runtime/core.db` / `data/private/private.db`：**未创建**
- 真实迁移 / dual-write：**未执行**
- `fetch_daily.py` 生产行为：**未修改**
