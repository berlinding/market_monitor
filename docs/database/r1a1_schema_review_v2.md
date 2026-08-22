# R1A.1 Schema Review v2

> R1A.1 设计自审 —— v2 Freeze Candidate 审查
> 日期：2026-08-22 ｜ **Status: FREEZE CANDIDATE — NOT YET APPROVED**
> 方法：按任务指定的 21 项风险逐一排查；每项给 Finding / Severity / Affected Tables / Problem / Resolution / Residual Risk / Blocking?
> 结论见文末汇总。

---

## Findings

### R1. Identity collision（身份冲突）

- **Severity**: HIGH — 已解决
- **Affected**: `entities` / `instruments` / `events`
- **Problem**: v1 中 events 只有单一 `entity_id`/`instrument_id`，多主体事件（并购 ACQUIRER+TARGET）无法表达，且 INTEGER id 跨库引用在重建后可能漂移。
- **Resolution**: v2 引入 `entity_uid`/`instrument_uid`/`event_uid`（UUIDv4）作为稳定身份；events 移除单一主体列，多主体走 `event_entities`/`event_instruments`（role=PRIMARY/ACQUIRER/TARGET/ISSUER/AFFECTED/RELATED）。跨库引用只用 uid（B3/B10）。
- **Residual risk**: 低。应用层必须遵守"uid 引用"纪律；R1B 提供校验函数。
- **Blocking?**: No

### R2. Entity identifier correctness（Entity 标识正确性）

- **Severity**: HIGH — 已解决
- **Affected**: `entities` / `entity_identifiers` / `instrument_identifiers`
- **Problem**: v1 把 LEI 放进 instrument_identifiers（`identifier_type` 含 LEI），身份归属错误——LEI 标识法人主体（Entity），不是 Instrument。
- **Resolution**: v2 新增 `entity_identifiers`（B1），identifier_type ∈ LEI/SEC_CIK/PROVIDER_COMPANY_ID/GLEIF/OTHER；LEI、SEC CIK 明确属 Entity；ticker/ISIN/FIGI/CUSIP/SEDOL 属 Instrument。两表严格分属。
- **Residual risk**: 低。R1B 需在字典与校验函数中固化归属。
- **Blocking?**: No

### R3. Ticker reuse（ticker 重用）

- **Severity**: MEDIUM — 已解决
- **Affected**: `instrument_identifiers`
- **Problem**: 历史不同公司可能使用同一 ticker；无 validity 区间会撞唯一约束。
- **Resolution**: 沿用 v1 partial unique `UNIQUE(provider, identifier_type, identifier) WHERE valid_to IS NULL`（当前有效映射唯一）+ 全历史 `(provider, identifier_type, identifier, valid_to)` 允许历史区间共存。
- **Residual risk**: 低。数据录入须带 valid_from/to。
- **Blocking?**: No

### R4. Stable UID（稳定 UID）

- **Severity**: HIGH — 已解决
- **Affected**: `entities` / `instruments` / `events` / `accounts` / `raw_artifacts` / `event_evidence`（全部跨库引用主体）
- **Problem**: v1 全用 INTEGER surrogate；跨库引用（private→core）依赖 ROWID，core.db 重建/合并后引用失效。
- **Resolution**: v2 明确选择 **UUIDv4**（Python stdlib `uuid.uuid4()`，零依赖、离线生成、碰撞可忽略）作为 `*_uid`（B3）。重建 core.db 后 UID 随行保留不变；INTEGER PK 仅作单库内部 surrogate。
- **Residual risk**: 低。UUID 无序性对 B-tree 索引局部性略有影响（行数级可忽略）。
- **Blocking?**: No

### R5. Cross-db rebuild（跨库重建）

- **Severity**: HIGH — 已解决
- **Affected**: `private.db` 全部跨库引用（positions.instrument_uid / watchlist_items.* / investment_theses.entity_uid / event_thesis_analysis.event_uid / alerts.*）
- **Problem**: v1 用 INTEGER id 跨库引用，重建 core.db 可能破坏引用。
- **Resolution**: 跨库引用一律 UID（B3）；同库关系仍可用 INTEGER FK。重建时 UID 不变 → 引用不失效。
- **Residual risk**: 低。依赖应用层只在 private.db 写 uid；R1B 提供 ensure_*_uid() 校验。
- **Blocking?**: No

### R6. Watchlist XOR（自选条目互斥）

- **Severity**: MEDIUM — 已解决
- **Affected**: `watchlist_items`
- **Problem**: v1 允许 entity_id/instrument_id 同时为空或同时存在，语义模糊（关注公司 vs 关注工具）。
- **Resolution**: v2 CHECK XOR：`(entity_uid IS NOT NULL AND instrument_uid IS NULL) OR (entity_uid IS NULL AND instrument_uid IS NOT NULL)`（B4）。
- **Residual risk**: 低。
- **Blocking?**: No

### R7. NULL uniqueness（NULL 唯一性）

- **Severity**: MEDIUM — 已解决
- **Affected**: `watchlist_items` / `instrument_identifiers` / `entity_identifiers`
- **Problem**: SQLite UNIQUE 约束中 NULL 相互不冲突，直接 UNIQUE(watchlist_id, entity_uid) 无法阻止 NULL 行重复。
- **Resolution**: 使用 partial unique index：`UNIQUE(watchlist_id, entity_uid) WHERE entity_uid IS NOT NULL`、`UNIQUE(watchlist_id, instrument_uid) WHERE instrument_uid IS NOT NULL`（B4 防 entity duplicate / instrument duplicate）；identifier 表沿用 partial unique 模式。
- **Residual risk**: 低。
- **Blocking?**: No

### R8. Account consistency（账户一致性）

- **Severity**: HIGH — 已解决
- **Affected**: `accounts` / `positions`
- **Problem**: v1 accounts 是 Deferred，positions 用 `account_ref` 文本暂代，无账户级一致性（多账户时 OPEN 唯一性无法约束）。
- **Resolution**: v2 accounts 提升为 private.db Core（B5），含 account_id/account_uid/account_name/broker/account_type/base_currency/status/created_at/updated_at，**不存 password/token**；positions.account_id 改为 NOT NULL FK → accounts（B6）。
- **Residual risk**: 低。
- **Blocking?**: No

### R9. Privacy boundary（隐私边界）

- **Severity**: HIGH — 已解决
- **Affected**: 全部 core.db vs private.db 划分
- **Problem**: v1 已分库，但 alerts 仍在 core（潜在泄漏运行时用户状态）；event_analysis 含 thesis_impact（私人投资逻辑泄漏到 public schema）。
- **Resolution**: v2 将 alerts 移入 private.db（B8）；event_analysis 收敛为 generic（移除 thesis 字段，B7）；私人 thesis 分析在 private.db event_thesis_analysis。core.db 不含任何持仓/成本/thesis/告警。
- **Residual risk**: 低（依赖 git 纪律 + 物理分库）。
- **Blocking?**: No

### R10. Generic / private analysis（通用 vs 私人分析）

- **Severity**: HIGH — 已解决
- **Affected**: `event_analysis` / `event_thesis_analysis`
- **Problem**: v1 的 event_analysis 同时承担通用判断与 thesis 影响，私人投资逻辑进入 public 表。
- **Resolution**: v2 分离（B7）：core.event_analysis 仅 generic（importance/summary/points/attention/model 信息）；private.event_thesis_analysis 记录 event↔thesis 的 impact_direction/severity/reasoning/invalidate_triggered/recommended_attention/model+prompt+analysis version/raw_output。
- **Residual risk**: 低。LLM 调用层需按目标表分流输出。
- **Blocking?**: No

### R11. Alert privacy（告警隐私）

- **Severity**: MEDIUM — 已解决
- **Affected**: `alerts`
- **Problem**: v1 alerts 在 core（PUBLIC），含触发规则/事件判断，可能暴露用户关注点与 thesis 信号。
- **Resolution**: v2 alerts 移入 private.db（B8），PRIVATE / RUNTIME USER STATE；可关联 event_uid/instrument_uid/thesis_analysis_id。
- **Residual risk**: 低。
- **Blocking?**: No

### R12. Source priority ambiguity（数据源优先级歧义）

- **Severity**: MEDIUM — 已解决
- **Affected**: `data_sources` / `datasets` / `dataset_sources`
- **Problem**: v1 `data_sources.priority` 全局数值优先级与数据集无关，且与 datasets.primary_source_id 语义重叠，多源 canonical 选择规则模糊。
- **Resolution**: v2 新增 `dataset_sources`（dataset_id + source_id + priority_role=PRIMARY/FALLBACK/ARCHIVE，B9）；data_sources.priority 弃用 canonical 含义。示例：CN_EQUITY_DAILY→TUSHARE=PRIMARY/FMP=FALLBACK；US_EQUITY_DAILY→FMP=PRIMARY/ALPHA_VANTAGE=FALLBACK；US_FILINGS→SEC=PRIMARY。
- **Residual risk**: 低。查询层按 priority_role 选源。
- **Blocking?**: No

### R13. Multi-entity event（多主体事件）

- **Severity**: HIGH — 已解决
- **Affected**: `events` / `event_entities` / `event_instruments`
- **Problem**: v1 events 单一 entity_id 无法表达 ACQUIRER+TARGET、ISSUER+AFFECTED 等多主体关系。
- **Resolution**: v2 新增 event_entities / event_instruments（role CHECK，B10）；events 不再设单一主体列。
- **Residual risk**: 低。R4+ 事件摄入层需按 role 归类。
- **Blocking?**: No

### R14. Multi-source event（多源事件）

- **Severity**: HIGH — 已解决
- **Affected**: `events` / `event_evidence`
- **Problem**: v1 一个 event 只有单一 source_id，无法表达同一事件对应 HKEX filing + SEC filing + company IR + news + API payload 多条证据。
- **Resolution**: v2 新增 event_evidence（B11）：evidence_type ∈ HKEX_FILING/SEC_FILING/COMPANY_IR/NEWS/API_PAYLOAD/MANUAL/OTHER；source_reference/published_at/detected_at/content_hash/is_primary/metadata。
- **Residual risk**: 低。证据归一化（dedup → normalized event）在 R4 设计。
- **Blocking?**: No

### R15. Duplicate evidence（证据去重）

- **Severity**: MEDIUM — 已解决
- **Affected**: `event_evidence`
- **Problem**: 同一事件同一证据被多源/多次抓取重复登记。
- **Resolution**: `UNIQUE(event_id, content_hash)`（同事件同内容去重，B11）+ partial `UNIQUE(event_id) WHERE is_primary=1`（每事件至多一条主证据）。
- **Residual risk**: 低。content_hash 计算口径在 R1B 固化。
- **Blocking?**: No

### R16. Raw provenance（原始证据溯源）

- **Severity**: HIGH — 已解决
- **Affected**: `raw_artifacts` / `market_prices_daily`
- **Problem**: v1 raw_artifacts 是 Deferred，canonical 数据无原始证据存档。
- **Resolution**: v2 raw_artifacts 提升为 R1 Core（B12）：artifact_uid/dataset_id/source_id/run_id/artifact_type/local_path_or_reference/content_hash(SHA-256)/retrieved_at/metadata；append-only。
- **Residual risk**: 低。raw 存储目录（data/raw/）已 gitignore。
- **Blocking?**: No

### R17. Canonical lineage（canonical 血缘）

- **Severity**: MEDIUM — 已解决
- **Affected**: `market_prices_daily`
- **Problem**: v1 无法回答"这条行情是哪次 ingest、哪个 source、哪个 raw artifact"。
- **Resolution**: v2 market_prices_daily 增加 `ingest_run_id`（NOT NULL FK → ingest_runs）+ `raw_artifact_id`（可选 FK → raw_artifacts）（B13）。
- **Residual risk**: 低。历史 backfill 行必须关联 backfill run。
- **Blocking?**: No

### R18. Migration reversibility（迁移可逆性）

- **Severity**: MEDIUM — 已解决
- **Affected**: `daily_bars` → `market_prices_daily`（迁移方案）
- **Problem**: 迁移不可逆 = 数据永久丢失风险。
- **Resolution**: v2 双完整性定义（B14）：normalized canonical completeness + raw provenance completeness；legacy 备份注册为 raw_artifact + SHA-256；pre_close/change/pct_chg 明确不迁移但 raw 可追溯；V1–V9 验证 + 30 天双写 + Rollback 方案（按 ingest_run_id 过滤回滚，幂等脚本）。
- **Residual risk**: 低（执行纪律依赖 R1B 实现）。
- **Blocking?**: No

### R19. Orphan references（孤儿引用）

- **Severity**: MEDIUM — 已解决（接受残余）
- **Affected**: private.db 全部跨库 uid 引用
- **Problem**: SQLite 无跨库 FK，private.db 可能引用 core.db 不存在的 uid。
- **Resolution**: 应用层写入校验（ensure_entity_uid/ensure_instrument_uid/ensure_event_uid）+ 定期孤儿检查脚本（R1 手工/脚本触发）。UID 方案下引用不随重建漂移（相对 v1 改进）。
- **Residual risk**: MEDIUM（接受）。与 v1 相同，R2 实施自动一致性检查后降为低。
- **Blocking?**: No

### R20. Parquet compatibility（Parquet 兼容性）

- **Severity**: LOW — 已解决
- **Affected**: 全局（未来归档层）
- **Problem**: v2 新增 uuid 列、hash 列是否影响未来 Parquet 归档。
- **Resolution**: UID 为固定长度 TEXT（36 字符）、hash 为 64 字符 hex TEXT，均为 Parquet 原生 string 类型；布尔/数值/日期原生兼容；JSON 以 TEXT 存储。无阻塞。
- **Residual risk**: 低。
- **Blocking?**: No

### R21. SQLite index strategy（索引策略）

- **Severity**: MEDIUM — 已解决
- **Affected**: 全局
- **Problem**: 多主体/多证据表（event_entities/event_instruments/event_evidence）、血缘表（raw_artifacts）新增后，查询可能全表扫描。
- **Resolution**: v2 明确索引：event_entities(entity_id)、event_instruments(instrument_id)、event_evidence(event_id)/(detected_at)、raw_artifacts(dataset_id, source_id, run_id)、market_prices_daily(ingest_run_id)、event_thesis_analysis(thesis_id)、alerts(alert_key/status)；UNIQUE 约束自带索引。查询模式（按 entity/instrument 查事件、按事件查证据、按 run 查行情）全部有索引支撑。
- **Residual risk**: 低。R1B DDL 按此清单建索引。
- **Blocking?**: No

---

## 汇总

| Severity | 数量 | 状态 |
|----------|------|------|
| HIGH | 9（R1 R2 R4 R5 R8 R9 R10 R13 R14 R16 中计 9 项） | 全部已解决 |
| MEDIUM | 10（R3 R6 R7 R11 R12 R15 R17 R18 R19 R21） | 全部已解决（R19 接受残余：跨库一致性靠应用层+定期检查） |
| LOW | 2（R20 + R12 重计修正） | 已解决 |

**Blocking findings remaining = 0**

**接受残余风险（需 Berlin 知悉）**：
1. R19 — 跨库 uid 引用一致性依赖应用层校验 + 定期孤儿检查（R2 自动化后消除）；
2. R4 — UUID 无序性（行数级影响可忽略）；
3. R18 — 迁移执行纪律依赖 R1B 脚本完整实现 V1–V9。

---

# R1A.2 Final Freeze Review Addendum（2026-08-22）

> R1A.2 对 v2 Freeze Candidate 做最后小范围结构修正后的复查。方法同前：Finding / Severity / Affected Tables / Problem / Resolution / Residual Risk / Blocking?

### F22. Instrument ticker reuse（ticker 重用）

- **Severity**: HIGH — 已解决
- **Affected**: `instruments` / `instrument_identifiers`
- **Problem**: v2 保留 `UNIQUE(instrument_type, primary_symbol, exchange_code)`，会阻止历史 ticker 重用（Company A ABC@XNAS 2020 delisted → Company B ABC@XNAS 2025 无法建立）。
- **Resolution**: 取消该 UNIQUE（F1）；`primary_symbol` 仅为展示/便利字段；身份由 `instrument_uid` 承担；ticker 历史唯一性只由 `instrument_identifiers`（valid_from/valid_to + partial unique）控制。明确 **ticker is an attribute / identifier, not identity**。
- **Residual risk**: 低。应用层不得再用 symbol 组合做唯一查找。
- **Blocking?**: No

### F23. Dataset source double truth（数据集源双重真源）

- **Severity**: HIGH — 已解决
- **Affected**: `datasets` / `dataset_sources`
- **Problem**: `datasets.primary_source_id` 与 `dataset_sources.role='PRIMARY'` 并存，两个 source-of-truth，数据库无法判断听谁的。
- **Resolution**: 从 v2 设计删除 `datasets.primary_source_id`（F2）；主源只能由 `dataset_sources` 决定。
- **Residual risk**: 低。
- **Blocking?**: No

### F24. Fallback ordering（fallback 顺序）

- **Severity**: MEDIUM — 已解决
- **Affected**: `dataset_sources`
- **Problem**: 仅 role（PRIMARY/FALLBACK/ARCHIVE）无法表达多个 FALLBACK 的顺序（FMP/AlphaVantage/Yahoo 谁先）。
- **Resolution**: `dataset_sources` 增加 `priority_rank INTEGER NOT NULL`（数字小优先）；`UNIQUE(dataset_id, priority_rank)` + 保留 `UNIQUE(dataset_id, source_id)`；额外用 partial unique `UNIQUE(dataset_id) WHERE role='PRIMARY' AND is_active=1` 保证每个 dataset 至多一个 active PRIMARY（F4）。
- **Residual risk**: 低。rank 维护靠应用层写入纪律。
- **Blocking?**: No

### F25. Raw artifact provenance duplication（raw 溯源重复）

- **Severity**: MEDIUM — 已解决
- **Affected**: `raw_artifacts`
- **Problem**: `UNIQUE(content_hash)` 阻止同一文件在不同 run / 不同 provider / 不同时间重复登记，丢失有意义 provenance。
- **Resolution**: 取消 `UNIQUE(content_hash)`，改普通 `INDEX(content_hash)`；防同 run 内重复用 `UNIQUE(run_id, content_hash) WHERE run_id IS NOT NULL`（F5）。hash 是内容身份/dedup detection，不等于 provenance record identity。
- **Residual risk**: 低。
- **Blocking?**: No

### F26. Event evidence provenance loss（事件证据溯源丢失）

- **Severity**: HIGH — 已解决
- **Affected**: `event_evidence`
- **Problem**: `UNIQUE(event_id, content_hash)` 使同一内容来自不同 source（Tencent IR PDF vs HKEX PDF）无法共存，丢失 provenance。
- **Resolution**: 改为 `UNIQUE(event_id, source_id, source_reference)`（source-level evidence identity）+ `INDEX(content_hash)` 内容相似检测；`is_primary` 单主约束保留（F6）。source_reference 可 NULL；若未来需要同 (event_id, source_id) 多条 NULL ref 证据，R1B 可加 `evidence_key`。
- **Residual risk**: 低（NULL ref 场景留待 R1B 决策）。
- **Blocking?**: No

### F27. Event source ambiguity（事件来源语义歧义）

- **Severity**: MEDIUM — 已解决
- **Affected**: `events`
- **Problem**: `events.source_id` 语义不明（primary source / first source / canonical source / ingest provider?）。
- **Resolution**: 采纳 **Option B**——更名为 `discovered_by_source_id`，语义 = 第一次让系统创建 normalized event 的 source（**detection provenance**）；不是 primary evidence、不是 canonical truth source（F7）。
- **Residual risk**: 低。写入层需按语义赋值。
- **Blocking?**: No

### F28. Account semantic normalization（账户语义规范化）

- **Severity**: MEDIUM — 已解决
- **Affected**: `accounts`
- **Problem**: `account_type` 含 IBKR/BROKER——不是 type，是 broker，与 `broker` 字段重复且语义污染。
- **Resolution**: `account_type IN ('CASH','MARGIN','RETIREMENT','PAPER','OTHER')`（F8A）；broker 名（IBKR 等）只进 `broker` 字段。示例：broker='IBKR' + account_type='MARGIN'。
- **Residual risk**: 低。
- **Blocking?**: No

### F29. Analysis cross-db identity（分析跨库身份）

- **Severity**: MEDIUM — 已解决
- **Affected**: `event_analysis` / `alerts`
- **Problem**: generic analysis 无稳定 UID，future private.alerts 无法精确跨库引用“哪一次 analysis 触发了 alert”。
- **Resolution**: `event_analysis.analysis_uid TEXT UNIQUE NOT NULL`（UUIDv4，F8B）；`alerts.generic_analysis_uid TEXT NULL` 跨库引用 analysis_uid；业务 UNIQUE `(event_id, model_provider, model_id, prompt_version, analysis_version)` 保留防重复。两个角色不混淆。
- **Residual risk**: 低。
- **Blocking?**: No

### R1A.2 汇总

| Severity | 数量 | 状态 |
|----------|------|------|
| HIGH | 3（F22 F23 F26） | 已解决 |
| MEDIUM | 5（F24 F25 F27 F28 F29） | 已解决 |
| LOW | 0 | — |

**Blocking findings remaining = 0**

---

# Freeze Readiness Checklist（R1A.2）

| # | 检查项 | 结果 |
|---|--------|------|
| 1 | Entity identity stable（entity_uid UUIDv4） | ✅ PASS |
| 2 | Instrument identity stable（instrument_uid UUIDv4） | ✅ PASS |
| 3 | ticker reuse supported（F1：symbol 去 UNIQUE，identifiers 控制历史） | ✅ PASS |
| 4 | cross-db UID stable（仅 uid 跨库，重建不漂移） | ✅ PASS |
| 5 | no duplicate source-of-truth fields（F2：primary_source_id 删除） | ✅ PASS |
| 6 | dataset source ordering deterministic（F4：priority_rank + UNIQUE） | ✅ PASS |
| 7 | raw provenance preserved（F5：hash 非唯一，run 内去重） | ✅ PASS |
| 8 | event evidence provenance preserved（F6：source-level 唯一） | ✅ PASS |
| 9 | event source semantics unambiguous（F7：discovered_by_source_id） | ✅ PASS |
| 10 | generic/private analysis separated（B7：event_analysis vs event_thesis_analysis） | ✅ PASS |
| 11 | accounts semantics normalized（F8A：type 与 broker 分离） | ✅ PASS |
| 12 | alert cross-db references stable（F8B：generic_analysis_uid） | ✅ PASS |
| 13 | legacy migration reversible（B14：备份 + raw_artifact + SHA-256） | ✅ PASS |
| 14 | private/public boundaries clean（core/private 分库 + alerts/thesis 归 private） | ✅ PASS |
| 15 | no R1B implementation performed（本轮仅文档修正） | ✅ PASS |

**Freeze Readiness: READY FOR BERLIN APPROVAL**

> 注意：这仍然是 **FREEZE CANDIDATE**，不是 FROZEN。Berlin 最终批准后方可标记 Frozen 并授权 R1B。
