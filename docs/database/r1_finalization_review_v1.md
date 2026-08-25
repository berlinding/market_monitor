# R1 Finalization Review

> R1 Finalization Gate — Clean-Commit Reproducibility Rehearsal 自审
> 日期：2026-08-25 ｜ **Decision: R1 COMPLETE**（clean committed code 独立复现真实 staging PASS）
> 审查对象：`scripts/phase2_staging_rehearsal.py`（commit `a6007b3` 版本）+ 真实数据 rehearsal（run `20260825T043812Z`）
> 授权：Berlin 2026-08-25（R1 Finalization Gate 指令）

---

## Decision

**R1 COMPLETE**

- R1 design validated（R1A v2 FROZEN + R1B spec + R1C Phase 0/1/1.1/1.2）
- R1 implementation validated（migration runner + validators + 103 tests）
- R1 real-data staging validated（Phase 2 run + Finalization run 均 PASS）
- R1 reproducibility gate validated（clean commit 上独立复现 PASS）
- **R1 COMPLETE ≠ production monitoring / dual-write / R3 complete**（R1 使命 = canonical data model + migration foundation）

## Git Reproducibility

| 项 | 值 |
|----|----|
| git_commit | `a6007b35a3c64af991047eec087cc6da0542c1d0` |
| git_branch | `main` |
| git_dirty | `false`（clean committed tree） |
| runner_path | `scripts/phase2_staging_rehearsal.py` |
| runner_sha256 | `d429dae7eedb4402068dadfb77546fc89b6fded2c9d6e26be32327bf5091d3cf` |
| C0001_sha256 | `0dd5b58ed96197d86324c171204dba0dd465da8775175028abc7f94999cc19b2` |
| P0001_sha256 | `2cce514fa6860e1e548f3cce747f9fcb11c99576d559fe2319e0ca44e84723ec` |
| runner exists in reported HEAD | **YES**（`git show HEAD:... | sha256sum` == report runner_sha256） |
| HEAD == origin/main | YES（`a6007b3`） |
| working tree | clean（`git status --porcelain` 空） |

## Real Inputs

- live `data/market.db`：38,789 rows / 7 trade dates / 5,548 instruments（只读，前后 sha256 `7b435961…` 一致）
- frozen snapshot：`data/raw/legacy/market_20260825T043812Z.db`（sha256 `ac5b2acd…`）
- real Tushare `stock_basic`：5,550 rows（L 单查一次成功，覆盖率 5,548/5,548 = 100%，未触发 D/P 补查）

## Mapping

- expected：5,548（frozen snapshot distinct ts_code）
- mapped：5,548
- coverage：100%（status PASS）
- missing：0 ／ duplicates：0 ／ unknown suffix：0 ／ ambiguous：0

## Migration

- entities：5,548 ／ instruments：5,548 ／ identifiers：11,096（1:1 严格）
- ingest_runs：7（Asia/Shanghai backfill）
- bars：38,789 migrated（7/7 原子批次成功，0 失败）

## V1–V18

**ALL PASS**（V1 row count / V2 trade dates / V3 mapping / V4 dup keys / V5 OHLC / V6 volume / V7 turnover / V8 null / V9 lineage / V10 artifact hash / V11 orphan refs / V12 aggregate / V13–V18 full-row）

## Full Row Reconciliation

- rows checked：38,789（100%，非 sample）
- OHLC mismatch：0 ／ volume mismatch：0 ／ turnover mismatch：0 ／ date mismatch：0 ／ mapping mismatch：0

## Safety

| 项 | 值 |
|----|----|
| production core.db exists | NO（`data/runtime/core.db` 未创建） |
| production private.db exists | NO（`data/private/private.db` 未创建） |
| live DB writer used | NO（全程 mode=ro） |
| token exposed | NO |
| dual-write enabled | NO |
| fetch_daily production behavior modified | NO |
| PRODUCTION_WRITES_ENABLED | False（runner PRODUCTION_PATHS hard guard 生效） |

## Governance Cleanup

- README：Current Stage R0 → **R1 Core Data Model — COMPLETE** + What works today / Not yet implemented（§二十五）
- PROJECT_STATUS：stale Data Status（16,620 / 3 dates / 5,546）移除，改为 Current Live Legacy Snapshot vs Last Validated Staging Snapshot 双栏（§二十六）；Runtime Status 过期 cron 时间清理（§二十七）
- Decision Register：DB-D054 – DB-D057 新增（§二十八）
- PROJECT_PROGRESS_LOG：append 2026-08-25 — R1 Finalization Gate（§三十）
- 无进一步 R1.x 设计阶段计划（§二十四）

## Residual Risks（真实，非 blocker）

1. **production cutover 尚未执行**——真实 core.db/private.db 创建与 daily_bars 生产迁移需 Berlin 另行授权（M8 dual-write 观察 + M9 retirement gate）。
2. **production canonical daily pipeline 尚未实现**——`fetch_daily.py` 仍写 legacy `market.db`；canonical `market_prices_daily` 每日入库属 R3。
3. **stock_basic 限频约束**——低积分 token 对 `stock_basic` 为小时级滚动限频（40203），未来身份更新/增量抓取需预留冷却（memory 2026-08-23 记录）。
4. **portfolio / event / alert 均属后续 roadmap**（R2/R4/R6），不阻塞 R1。

**Blocking findings remaining = 0**
