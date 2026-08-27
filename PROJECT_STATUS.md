# PROJECT_STATUS.md

## Current Snapshot

Current Stage: R3-A — A 股日线 canonical 增量入库 + Raw Artifact Immutability Hardening（COMPLETE 2026-08-27）
System Status: Development
Production Monitoring: NOT ENABLED
Automated Trading: DISABLED
## Roadmap

R0 — Project Governance & Architecture
R1 — Core Data Model
R2 — Portfolio & Watchlist
R3 — Data Pipeline
R4 — Event Engine
R5 — Event Intelligence
R6 — Alert System
R7 — Daily Briefing
R8 — Historical Intelligence
R9 — Quant Layer

## Completed

- R0 — Project Governance & Architecture（2026-08-17）
- R1A v1 — Core Domain Model & Data Contract（2026-08-17，设计未实施）
- Credential Security（2026-08-17，API.txt 保密规则）
- R1A.1 — Recovery, Repository Reconciliation & Schema Freeze Candidate（2026-08-22）
- R1A.2 — Final Freeze Corrections（2026-08-22，F1–F8 修正）
- **R1A v2 — FROZEN**（2026-08-22，Berlin 批准）
- **R1B — SQL DDL & Migration Specification**（2026-08-22，只写不执行）
- **R1B.1 — Implementation Safety Corrections**（2026-08-22，S1–S6 修正）
- **R1C Phase 0 — Pre-Implementation Reconciliation**（2026-08-22，P0-1/P0-2/P0-3）
- **R1C Phase 1 — Temp-DB Implementation & Validation**（2026-08-22，62 tests OK）
- **R1C Phase 1.1 — Final Pre-Production Hardening**（2026-08-22，H1–H4，77 tests OK）
- **R1C Phase 1.2 — Canonical Date Contract Fix**（2026-08-22，D1–D5，99 tests OK）
- **R1C Phase 2 — Full-Scale Real-Data Staging Rehearsal**（2026-08-25，**FINAL RESULT: PASS**：real market.db → frozen snapshot → 真实 stock_basic → staging core/private.db → 38,789 行全量迁移 → V1–V18 全 PASS + 100% full-row reconciliation 0 mismatch）
- **R1 Finalization Gate — Clean-Commit Reproducibility Rehearsal**（2026-08-25，**FINAL RESULT: PASS**：commit `a6007b3` clean tree 上独立复现真实 staging，git_dirty=false，runner 属 HEAD，**R1 — Core Data Model: COMPLETE**）
- **R2 Part A — Canonical Identity Activation**（2026-08-25，**PASS**：production core.db INITIALIZED 5,548 instruments / 38,789 bars；production private.db INITIALIZED schema-only；clean commit `a9af1dd` validate V1–V18 ALL PASS）
- **R2 Part B — Minimal Portfolio & Watchlist**（2026-08-25，**PASS**：account/position/watchlist service + CLI + identity resolution + cross-db validator + monitoring universe；125 tests OK）
- **R3-A — A 股日线 canonical 增量入库**（2026-08-27，**PASS**：production core.db 新增真实交易日 08-25/08-26 = 11,093 bars；identity 扩展 2 个新上市/复牌 instrument；mapping coverage 100%；reconciliation 0 mismatch；幂等重跑 row count 不变；lineage 完整；143 tests OK）
- **R3-A Hardening — Raw Artifact Immutability**（2026-08-27，**PASS**：raw artifact 改为 content-addressed 不可变路径（R3-D007）；历史 artifact 3/4/5 重建/迁移修复，全部 `content_hash == sha256(local_path bytes)`；同日重跑不覆盖历史文件；145 tests OK）

## Current

- **R3-A Minimal Canonical Incremental Ingestion + Immutability Hardening COMPLETE — awaiting Berlin review**
- 实现：`scripts/ingest_daily.py`（CLI：`--date/--latest/--reconcile/--allow-production/--stock-basic`）+ identity 扩展（新上市/复牌 instrument 从已注册 stock_basic artifact 解析，已有 UID 不动）+ **content-addressed 不可变 raw artifact（R3-D007）**
- 测试：`tests/` 12 个文件，**Ran 145 tests — OK（0 failed / 0 errors / 0 skipped）**
- Review：`docs/r3/r3a_ingest_review_v1.md`（**Blocking findings = 0**）+ `docs/r3/r3a_decisions_v1.md`（R3-D001–R3-D006）
- Real portfolio data: NOT POPULATED（等待 Berlin 主动录入）

## Validation（R1C Phase 1.2）

- Canonical trade_date = YYYY-MM-DD PASS（legacy 20260814 → canonical 2026-08-14；T-CANONICAL-TRADE-DATE-01）
- Canonical listing_date = YYYY-MM-DD PASS（20010827 → 2001-08-27；T-CANONICAL-LIST-DATE-01）
- Canonical valid_from = YYYY-MM-DD PASS（instrument_identifiers.valid_from == 2001-08-27）
- Invalid dates fail-fast PASS（20260230/20261340/abcdefgh/空 → DateNormalizationError / MappingGateError）
- Snapshot manifest JSON-safe PASS（json.dumps 成功；T-MANIFEST-JSON-01）
- V2/V12 校验用 normalized date semantics（不再 raw==raw oracle）
- 其余全部 PASS：Temp core/private schema、runner atomicity、constraints、cross-db uid、legacy fixture、privacy、H1–H4
- 真实 legacy 时区：**CONFIRMED = Asia/Shanghai**

## Real DB

- **production `data/runtime/core.db`：INITIALIZED + R3-A ACTIVE INGESTION（2026-08-27）**——C0001 + **5,550 instruments**（R2 5,548 + R3-A 新增 2：600984.SH 复牌 / 688835.SH 新上市）/ 11,100 identifiers / **49,882 bars = 9 个交易日（08-14→08-26）** / 11 ingest_runs；gitignored 不入 Git
- **R3-A 增量入库（2026-08-27）**：08-25（5,546 行，run 8）+ 08-26（5,547 行，run 9）真实新交易日进入 production；identity 扩展新增 600984.SH（建设机械，listing 2004-07-07 复牌）/ 688835.SH（高凯技术，listing 2026-08-25 新上市）；已有 5,548 个 instrument_uid 未变
- **R3-A Hardening（2026-08-27）**：raw artifact 改为 content-addressed 不可变路径（`daily_YYYY-MM-DD_<sha256[:16]>.json`）；历史 artifact 3（run 8）被 run 10 覆盖的文件已**精确重建**（exported_at_utc 爆破命中 `2026-08-27T03:27:36Z`，sha256 全匹配），artifact 4/5 迁移到 content-addressed 路径；全部 FILE artifact `content_hash == sha256(local_path bytes)` 成立；run 11 重跑验证历史文件不受影响
- **production `data/private/private.db`：INITIALIZED（2026-08-25）**——P0001 schema-only，业务表为空（等待 Berlin 真实 portfolio 录入）；gitignored
- **Real Legacy Migration（production cutover）: NOT EXECUTED**——legacy market.db 原样保留；dual-write OFF；legacy 仍为当前运行数据源（§12/§13）；R3-A 增量从 legacy 读取入 canonical

## Staging Rehearsal（R1C Phase 2，2026-08-25 run `20260825T030439Z`）

- **FINAL RESULT: PASS**（report：`data/staging/r1c_phase2/20260825T030439Z/migration_report.json`，gitignored）
- 数据规模：38,789 行 / 7 交易日（08-14→08-24）/ 5,548 标的（SH·SZ·BJ）
- frozen snapshot：`data/raw/legacy/market_20260825T030439Z.db`（sha256 `ac5b2acd…`；8-23 旧快照保留）
- stock_basic：真实下载 5,550 条（L 单查覆盖 5,548/5,548 = 100%），CSV+meta 落盘 `data/raw/tushare/`
- staging：core.db（17 tables，C0001）+ private.db（8 tables，P0001），FK check 全空
- 迁移：5,548 entities / 5,548 instruments / 11,096 identifiers（1:1）、7 ingest_runs、38,789 bars 全量
- V1–V18 全 PASS；full-row reconciliation：38,789 行 checked，0 mismatch
- live market.db 运行前后 sha256 一致（`7b435961…`）

## R1 Finalization Rehearsal（2026-08-25 run `20260825T043812Z`）

- **FINAL RESULT: PASS**（report：`data/staging/r1_finalization/20260825T043812Z/r1_finalization_report.json`，gitignored）
- **Clean-commit reproducibility**：HEAD==origin/main==`a6007b3`，working tree clean，git_dirty=false
- runner 属 HEAD：HEAD runner sha256 `d429dae7…` == report runner_sha256（可精确重建）
- C0001 sha256 `0dd5b58e…` / P0001 sha256 `2cce514f…`（raw-byte 契约）
- 数据规模：38,789 行 / 7 交易日 / 5,548 标的；stock_basic 5,550 条（L 单查 100% 覆盖）
- staging：core.db（17 tables，C0001）+ private.db（8 tables，P0001），FK check 全空
- 迁移：5,548 entities / 5,548 instruments / 11,096 identifiers（1:1）、7 ingest_runs、38,789 bars 全量
- V1–V18 全 PASS；full-row reconciliation：38,789 行 checked，0 mismatch
- safety：production core/private 不存在、live 只读（sha256 before==after `7b435961…`）、token 未暴露、dual-write off

## Existing Prototype

- **Dividend / Quality Dashboard**（港股高股息/质量筛选面板）
- 位置：`prototypes/dividend_dashboard/`（`index.html` + `chart.umd.min.js` + `data/dashboard_data.js`；2026-08-22 从根目录迁入，git mv 保留历史）
- Status: **Prototype, not integrated with canonical DB**（未接入 core.db/private.db）
- 治理记录：`docs/prototypes/dividend_dashboard_status_v1.md`；决策：DB-D015
- **自动同步治理修复（2026-08-27）**：根因 = invest-lab `deploy.sh` 把 dashboard 产物复制到 repo root 后 commit/push（invest-agent cron `dbece3dc` 每日 17:30 触发）。已修复：deploy.sh 目标改为 `prototypes/dividend_dashboard/` + 自同步 + 防回归断言；GitHub main 已清除 root 副本（commit `9885170`）；`.gitignore` 增加 root 锚定 ignore；新增 `tests/test_dashboard_governance.py`（T-DASH-ROOT-01/02 + T-DASH-PROTO-01）
- 本轮不扩展、不继续开发 dashboard 功能

## Next

- **Berlin reviews R3-A artifacts（`r3a_ingest_review_v1.md` + `r3a_decisions_v1.md`（R3-D001–D007）+ 145 tests）→ 稳定运行观察（连续多日自动增量入库）→ 之后 R3-B（canonical fetch 独立化 / legacy 依赖解除）或直接演进**。
- 不自动开始下一个 milestone；不自动写真实持仓（等待 Berlin 录入）。

## Not Authorized

- legacy retirement / production cutover / dual-write（fetch_daily.py 保持只写 legacy；R3-A 增量从 legacy 读 canonical，非 cutover）
- 自动写真实 portfolio（accounts/positions/watchlists 数据需 Berlin 主动录入）
- Dashboard 继续开发
- R3-B / R4 自动开始

## Active Components

（暂无）

## Data Sources

- Tushare — A股行情/财务/指数（已接入，密钥在 `~/API.txt`）
- FMP — 美股/全球基本面（密钥已配置，未接入）
- Alpha Vantage — 美股/外汇/加密（密钥已配置，未接入）
- FRED — 美国宏观（密钥已配置，未接入）
- EIA — 能源（密钥已配置，未接入）
- US Census — 贸易/人口普查（密钥已配置，未接入）

## Data Status

### Current Live Legacy Snapshot（2026-08-25 finalization preflight 实测）

- `data/market.db`：A股日线 `daily_bars` **38,789 行 = 7 个交易日**（08-14: 5,540 / 08-17: 5,539 / 08-18: 5,540 / 08-19: 5,541 / 08-20: 5,541 / 08-21: 5,543 / 08-24: 5,545；distinct ts_code 5,548）+ `fetch_log` 7 条
- 最近一次抓取：2026-08-24 18:33（5545 行）；sha256 `7b435961…`（finalization 前后一致）
- **live mutable state**——每日下载 cron 可能继续追加新交易日，行数会增长

### Last Validated Staging Snapshot（2026-08-25 run `20260825T043812Z`）

- frozen snapshot `data/raw/legacy/market_20260825T043812Z.db`（sha256 `ac5b2acd…`）—— **validated frozen state**，migration 的唯一权威基线（P0-3/DB-D040）
- canonical 设计目标：`data/runtime/core.db`（public）+ `data/private/private.db`（private），R1B 实施，生产迁移未授权

## Runtime Status

- 开发阶段，无生产监控，无自动交易
- legacy downloader（`fetch_daily.py`）存在且每日 cron 运行（写 legacy market.db）；**R3-A 增量入库已打通（`scripts/ingest_daily.py`），可手动/调度执行；production canonical 自动监控 NOT ENABLED（待 R3 稳定运行观察）**
- production core.db = initialized canonical baseline + R3-A 增量（active ingestion target，手动触发）
- legacy downloader operational status（cron 健康度/缺口回补）requires separate R3 review

## Current Blockers

**R1B.1 完成后：Blocking findings remaining = 0 → No R1C blocker**（r1b_ddl_review_v1.md R1B.1 Addendum 确认）。

待 Berlin 决策的开放问题（不阻塞审查）：

1. sector/industry 是否 R1 就需要（否则 R2 建 entity_classifications）
2. financial_reports/financial_facts 是否随 FMP/SEC 接入提前升级（当前 Deferred）
3. ~~market_prices_daily upsert 策略~~ —— **已解决**：DB-D031 CONTROLLED UPSERT（不再开放）
4. ~~event_evidence 同源多版本证据是否需要 version 列~~ —— **已解决**：DB-D032/D036 evidence_key（R1 用 evidence_key；若未来需严格同源版本历史再评估 version 列）
5. legacy fetched_at 时区：R1C 执行前必须 CONFIRMED（Asia/Shanghai 或 Berlin 确认），否则迁移暂停（S2/DB-D035）

## Key Decisions（2026-08-25 R2 增量，详见 P-D001–P-D005）

- Production instrument_uid becomes stable portfolio reference（P-D001）
- Positions remain snapshot semantics in R2（P-D002）
- Portfolio data lives only in private.db（P-D003）
- R2 application layer resolves identifiers through core DB（P-D004）
- Monitoring universe = OPEN positions ∪ watchlist targets（P-D005）
- （DB-D001–D057 保持冻结）

## Next Authorized Step

- Berlin 审查 R3-A 产物（r3a_ingest_review_v1.md + r3a_decisions_v1.md + 145 tests）→ 授权 R3 稳定运行观察（每日增量入库）与后续演进；真实 portfolio 录入仍在 Berlin 侧。
