# R1A Schema Review v1

> R1A 设计审查 —— 自审结果
> 日期：2026-08-17 ｜ 状态：Design (not implemented)
> 方法：按任务指定的 11 类风险逐一排查；每项给 Finding / Severity / Affected tables / Why / Resolution / Residual risk

---

## Findings

### F1. Provider leakage（provider 标识泄漏进身份模型）

- **Severity**: HIGH（已解决）
- **Affected**: `instruments` vs `instrument_identifiers`
- **Why**: 原 daily_bars 以 ts_code 为主键，是 source-specific 身份；若 canonical 继续硬编码任何 provider 符号，未来接 FMP/SEC 会返工。
- **Resolution**: `instruments` 不含任何 provider 标识；`instrument_identifiers` 独立成表（provider + identifier_type + identifier + validity），ts_code 作为 TUSHARE/TICKER 一行。
- **Residual risk**: 低。映射表未来增长需维护（ticker 变更时 valid_to 关闭 + 新行）。

### F2. Ticker-as-identity（把 ticker 当身份）

- **Severity**: HIGH（已解决）
- **Affected**: `entities` / `instruments` / `investment_theses`
- **Why**: ticker 可重用、可变更；thesis 挂 ticker 会在换代码后丢失逻辑。
- **Resolution**: 双层身份（Entity→Instrument→Identifier）；thesis 挂 `entity_id`；watchlist_item 挂 `instrument_id`。
- **Residual risk**: 低，取决于应用层是否遵守（R1B 提供校验函数）。

### F3. Volume / Turnover 单位歧义（Tushare 陷阱）

- **Severity**: HIGH（已解决）
- **Affected**: `market_prices_daily`
- **Why**: Tushare `vol` 单位=手、`amount` 单位=千元；FMP 等单位不同。不显式标注则跨市场数据无法比较。
- **Resolution**: `volume_unit` / `turnover_unit` 必填列，存 provider raw 数值 + 显式单位，换算只在查询层。
- **Residual risk**: 低。历史遗留：legacy daily_bars 无单位标注，迁移时按 Tushare 约定（LOTS/THOUSAND_CNY）标注（迁移文档已写明）。

### F4. Timestamp ambiguity（无时区时间戳）

- **Severity**: MEDIUM（已解决）
- **Affected**: 全表（尤其 `events`、`ingest_runs`）
- **Why**: 本地时间无时区 → 跨时区对比/夏令时/换时区主机全部出错；fetch_log.fetched_at 是本地时间（legacy 遗留）。
- **Resolution**: 全 schema "时刻一律 UTC ISO-8601"；日历日期用 DATE 无时区；事件额外 `event_timezone`；legacy fetch_log 不迁移（由 ingest_runs 取代）。
- **Residual risk**: 低。legacy market.db 的 fetched_at 仅作历史参考，不进入 canonical。

### F5. Currency 歧义

- **Severity**: MEDIUM（已解决）
- **Affected**: `market_prices_daily` / `positions` / `financial_*`
- **Why**: 港股 HKD、A股 CNY、美股 USD；成本币种与报价币种不同。
- **Resolution**: ISO 4217 显式列；positions 有独立 currency_code（成本币种）；行情 currency_code 与 instrument.currency_code 冗余存储（便于审计，应用层校验一致）。
- **Residual risk**: 低。future FX 资产需额外 pair 约定（R2+ 再细化）。

### F6. Mutable historical fact（历史事实被覆盖）

- **Severity**: MEDIUM（已决议）
- **Affected**: `market_prices_daily`（受控 upsert）、`events.summary`
- **Why**: provider 会重新发布修正值；严格不可变则修正永远丢失，严格可变则审计链断裂。
- **Resolution**: R1 决议 = 受控 upsert（同键覆盖 + ingested_at 更新 + ingest_runs 记录）；原始证据存档（raw_artifacts）Deferred，届时提供完整不可变证据链。`events` 保持 append-only（status 流转），summary 属事实描述允许人工修正。
- **Residual risk**: MEDIUM（接受）。provider 修正的历史版本不可回溯，直到 raw_artifacts 落地。若 Berlin 要求严格版本化，需提前加 `price_revisions` 表（已列入 Open Questions）。

### F7. Event fact / AI analysis 混淆

- **Severity**: HIGH（已解决）
- **Affected**: `events` / `event_analysis`
- **Why**: importance/判断若进 events，同一事件不同模型结论会污染事实层。
- **Resolution**: 严格分离。events 只存确定性字段；importance_score/recommended_attention/thesis_impact/bullish·bearish_points 全部在 event_analysis（带 model_id/prompt_version/analysis_version）。
- **Residual risk**: 低。风险在应用层是否遵守（R1B 文档 + 校验）。

### F8. positions 语义（snapshot vs ledger）

- **Severity**: MEDIUM（已决议）
- **Affected**: `positions` / `transactions`(Deferred)
- **Why**: 若 positions 是 ledger 却只有一行，历史与成本计算会错；若双写则 split-brain。
- **Resolution**: positions = snapshot state（一行=当前状态，OPEN partial unique）；transactions = 未来 canonical ledger，建立后 positions 转为 derived（重放/同步推导）。R1 阶段 positions 独立工作（手动/导入）。
- **Residual risk**: MEDIUM。过渡期内 positions 的更新可能丢失（如券商导入失败未察觉）→ 用 as_of_date + source 字段缓解，R2 引入 transactions 后消除。

### F9. Destructive migration risk

- **Severity**: HIGH（已解决）
- **Affected**: `daily_bars` → `market_prices_daily`
- **Why**: 直接改写旧表 = 数据永久丢失风险。
- **Resolution**: 迁移方案 = copy + validate + 双写观察期 + 备份 + Berlin 批准后才可删除旧表（见 daily_bars_migration_plan_v1.md）。
- **Residual risk**: 低。执行纪律依赖 R1B 脚本实现完整（V1–V7 验证清单）。

### F10. Over-normalization / 冗余 lookup 表

- **Severity**: LOW（已解决）
- **Affected**: enum 设计全局
- **Why**: 为每个枚举建 lookup 表 → 无意义 join 与维护成本。
- **Resolution**: SQL CHECK + 应用层常量；只有会增长的字典（event_type、metric_key）在未来升级 lookup。
- **Residual risk**: 低。event_type 若快速膨胀（R4 接入多源），CHECK 迁移成本一次，可接受。

### F11. Under-normalization（sector/industry 缺失）

- **Severity**: LOW（已决议）
- **Affected**: `entities`
- **Why**: sector/industry 是常用筛选维度，R1 不建模可能让 R2 选股返工。
- **Resolution**: R1 有意不入表（mutable classification，多分类体系并存）；未来 `entity_classifications` 表（entity_id, classification_system, code, valid_from/to）。已列入 Open Questions 供 Berlin 决策。
- **Residual risk**: LOW。若 Berlin 现在就需要行业维度，R1B 可加一张轻量表。

### F12. Future schema migration traps

- **Severity**: MEDIUM（已解决）
- **Affected**: 全局
- **Why**: 无版本管理 → 改表不可追溯、无法回滚。
- **Resolution**: `schema_migrations` 表 + 手写 SQL + stdlib runner（R1B）；append-only 日志；migration 文件入 Git。
- **Residual risk**: 低。

### F13. Privacy leakage

- **Severity**: HIGH（已解决）
- **Affected**: `positions` / `watchlists` / `investment_theses` / 未来 `accounts` `transactions`
- **Why**: 持仓/成本/账户/交易/投资逻辑一旦进入公开仓库 = 永久泄漏。
- **Resolution**: 物理分库（private.db）+ .gitignore（已覆盖 `*.db`、`data/private/`、portfolio*/positions*/trades*）+ 提交前检查（§Git 检查清单）。core.db 不含任何持仓/成本数据。
- **Residual risk**: 低（依赖 git 纪律，已在 PROJECT_RULES §4 与本次 commit 检查中落实）。

### F14. 跨库一致性（core/private 引用完整性）

- **Severity**: MEDIUM（已决议）
- **Affected**: `positions.instrument_id` / `watchlist_items.*` / `investment_theses.entity_id`
- **Why**: SQLite 无跨库 FK，孤儿引用会导致 join 丢行。
- **Resolution**: 引用式关联 + 应用层写入校验（ensure_instrument/ensure_entity）+ 定期孤儿检查脚本；唯一真源在 core.db。
- **Residual risk**: MEDIUM（接受）。R2 实施一致性检查脚本后降为低。

---

## 汇总

| Severity | 数量 | 状态 |
|----------|------|------|
| HIGH | 6（F1 F2 F3 F7 F9 F13） | 全部已解决 |
| MEDIUM | 7（F4 F5 F6 F8 F12 F14 + F8/F14 重复计数修正） | 已决议（含 3 项接受残余风险） |
| LOW | 2（F10 F11） | 已解决/已决议 |

**接受残余风险（需 Berlin 知悉）**：F6（行情受控 upsert，raw 证据链待 raw_artifacts）、F8（positions 过渡期 snapshot 语义）、F14（跨库引用一致性靠应用层 + 定期检查）。
