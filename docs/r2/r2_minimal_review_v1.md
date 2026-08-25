# R2 Minimal Review v1

> R2 — Minimal Portfolio & Watchlist + Canonical Identity Activation 自审
> 日期：2026-08-25 ｜ **Status: R2 FOUNDATION COMPLETE（PASS）**
> 授权：Berlin 2026-08-25（R2 指令 §1–§45）
> 格式：结果摘要 / Part A / Part B / 测试 / 隐私 / 安全 / 治理 / 残余风险

---

## Decision

**R2 MINIMAL PORTFOLIO & WATCHLIST FOUNDATION COMPLETE — PASS**

- Canonical Identity Activation：PASS（production core.db / private.db INITIALIZED）
- Minimal Portfolio & Watchlist：实现 PASS（service + CLI + tests）
- Real portfolio data：NOT POPULATED（等待 Berlin 主动录入，未替用户猜测）

---

## Part A — Canonical Identity Activation

### Production Core：INITIALIZED ✅

- 路径：`data/runtime/core.db`（gitignored，不入 Git）
- 初始化方式：**新 frozen snapshot**（`data/raw/legacy/market_20260825T091354Z.db`，sha256 `ac5b2acd…`）
  + 真实 Tushare stock_basic（L 单查 5,550 条，覆盖率 5,548/5,548 = 100%）
  + R1 已验证 migration semantics（C0001 经 migrate runner，checksum `0dd5b58e…`）
- 数据：entities 5,548 / instruments 5,548 / identifiers 11,096 / ingest_runs 7 / bars **38,789**
- V1–V18：**ALL PASS**；full-row reconciliation 38,789 行 checked，**mismatch = 0**
- FK check：空；schema_migrations：C0001 APPLIED
- **stable identity**：`entity_uid` / `instrument_uid` 正式成为 production 稳定引用（P-D001）

### Production Private：INITIALIZED ✅

- 路径：`data/private/private.db`（gitignored，不入 Git）
- P0001 APPLIED（checksum `2cce514f…`）；8 表齐全；FK check 空
- **未写入任何真实 portfolio**（accounts/positions/watchlists 均为 0 行）

### 初始化可复现性（§30 initialize-if-absent / validate-if-present）

- 首次执行：initialize 模式（新 snapshot → production core/private）
- 再次执行：validate-if-present 模式——检测 DB 已存在 → **重跑 V1–V18 + full-row reconciliation**
  （从 raw_artifacts 恢复 snapshot/manifest/mapping）→ 不重复 insert、不生成新 UID、不覆盖
- validate run（clean commit `a9af1dd`）：core valid=True / private valid=True / **final PASS**

### 过程说明（reproducibility gate 生效）

- 首次 initialize 时 production_init.py 尚未提交 → report 因 git_dirty=true 标记 FAIL
  （数据层全部 PASS，但 gate 拒绝 dirty tree 宣告 PASS —— 正确行为）
- 按 §31 纪律：commit `f6da1e1` → 修复 reconciliation 检查（mismatch 字段过滤）→ commit `a9af1dd`
  → clean tree 上 validate-if-present → **PASS**（git_dirty=false）

---

## Part B — Minimal Portfolio & Watchlist

### 新增文件

| 文件 | 职责 |
|------|------|
| `scripts/portfolio/__init__.py` | 包声明 |
| `scripts/portfolio/repository.py` | SQL 集中（core 只读 + private 读写） |
| `scripts/portfolio/service.py` | 业务规则（identity 解析 / XOR / snapshot / universe） |
| `scripts/portfolio.py` | 最小 CLI（argparse 薄壳，规则在 service 层） |
| `tests/test_r2_portfolio.py` | R2 测试（temp DB，synthetic 数据） |
| `scripts/production_init.py` | Part A 生产初始化（initialize-if-absent / validate-if-present） |

### Service API（§16）

- Account：create_account / list_accounts / get_account
- Position：set_position（insert or controlled update）/ close_position / list_positions / get_position
- Watchlist：create_watchlist / list_watchlists / add_watchlist_item / remove_watchlist_item / list_watchlist_items
- Identity：resolve_instrument / resolve_entity（ts_code / bare ticker / uid → stable uid）
- Cross-db：validate_private_core_references（§26）
- Universe：get_monitoring_universe（§32：OPEN positions ∪ watchlist，source=POSITION/WATCHLIST/BOTH）

### CLI（§23）

`python3 scripts/portfolio.py account|position|watchlist|resolve|universe|validate-refs`

### Production identity smoke test（§25，只读）

| identifier | 解析结果 |
|------------|---------|
| 600519.SH | instrument_uid `19a5e7c4…` → 贵州茅台 / XSHG |
| 000001.SZ | instrument_uid `7765a90e…` → 平安银行 / XSHE |
| 920000.BJ | instrument_uid `b9d5eaa8…` → 安徽凤凰 / XBSE（北交所新代码段） |
| 600036（bare） | → 招商银行 / XSHG |
| ABC_NOT_EXIST | IdentityNotFoundError（fail-fast，§27） |

---

## Tests

- **Ran 125 tests — OK（0 failed / 0 errors / 0 skipped）**（原 103 + 新增 22 R2 tests）
- R2 覆盖：R2-ACCOUNT-01/UNIQUE-01、R2-POSITION-01/UPDATE-01/CLOSE-01/IDENTITY-FAIL-01、
  R2-WATCHLIST-01/INSTRUMENT-01/ENTITY-01/XOR-01/DUP-01、R2-CROSSDB-01/ORPHAN-01、R2-PRIVACY-01、
  identity resolution（ts_code/BJ/bare/unknown）、universe union/dedupe/source
- 全部使用 temp DB（TemporaryDirectory + temp core/private），未触碰 production DB（§29）

---

## Privacy（§19 硬规则）

- real portfolio automatically populated = **NO**
- private data committed to Git = **NO**
- private fields in core = **NO**（test_r2_privacy_01 验证）
- 测试使用 synthetic portfolio（贵州茅台/平安银行 fixture）

---

## Safety

| 项 | 值 |
|----|----|
| dual-write | OFF（fetch_daily.py 未修改，§12） |
| legacy retirement | NO（market.db 保留，legacy cron 继续，§13） |
| production monitoring | NOT ENABLED |
| event engine started | NO（§33） |
| Telegram started | NO |
| production DB overwrite | NO（validate-if-present 语义，§6/§30） |
| live market.db | 只读，sha256 前后一致（`7b435961…`） |
| token | 未出现在日志/report/CLI（env/~/API.txt 读取） |

---

## Governance Cleanup

- `docs/portfolio/portfolio_decisions_v1.md`：P-D001–P-D005（§37）
- `PROJECT_STATUS.md`：R2 Current Stage / Canonical Identity Activation PASS / production core+private INITIALIZED
  / R2 implementation PASS / Real Portfolio NOT POPULATED（§38）
- `README.md`：What works today 增加 identity DB / portfolio service / resolution / universe（§39）
- `PROJECT_PROGRESS_LOG.md`：append 2026-08-25 — R2 Minimal Portfolio & Watchlist（§40）
- `.gitignore`：`data/runtime/` 增加（§36）；data/private / data/raw / data/staging / API.txt 已 ignore

---

## Residual Risks（真实，非 blocker）

1. **real Berlin portfolio 尚未录入**——private.db 业务表为空；Berlin 录入后 universe/positions 才有真实数据。
2. **canonical daily incremental ingestion 尚未实现**——production core.db 是 initialized baseline，
   不是 active ingestion target（R3）。
3. **港/美 identity/provider coverage 尚未实现**——R2 仅 A 股 ts_code/ticker 解析（R4/R5 扩展）。
4. **events/intelligence/Telegram 尚未实现**——R4/R5/R6。
5. **stock_basic 限频约束**——未来身份更新需预留冷却（memory 2026-08-23）。

---

## Stage Decision

- **R2 MINIMAL PORTFOLIO & WATCHLIST FOUNDATION COMPLETE**
- SYSTEM NOW KNOWS: WHO BERLIN HOLDS / WATCHES（能力已实现；真实数据等待 Berlin 主动录入）
- NEXT: R3 Minimal Canonical Data Pipeline → R4 Earnings/Filing → R5 Relevance/Thesis Intelligence → R6 Telegram
