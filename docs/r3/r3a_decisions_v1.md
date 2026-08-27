# R3-A Decisions — Canonical Incremental Daily-Bar Ingestion

> 日期：2026-08-27 ｜ Status: Adopted ｜ R3-A 增量入库决策登记
> 前置：R1/R2 COMPLETE（DB-D001–D057 冻结 + P-D001–P-D005）

## R3-D001 — 增量输入源 = legacy market.db（R3-A 阶段）

- **Decision**: R3-A 的 canonical 增量入库从 **legacy `data/market.db`**（fetch_daily.py 每日写入的可靠 raw input）读取新交易日，导出该日 payload 为 raw artifact（`data/raw/tushare/daily_YYYY-MM-DD.json`，sha256），再入库 canonical。不直接调 Tushare API。
- **Rationale**: 本轮停止边界要求 legacy downloader 继续保留；legacy 数据已是经过 fetch_daily.py 校验的可靠输入；与 legacy↔canonical reconciliation 语义天然一致（同源对比）。
- **Consequences**: 未来若 legacy 退休（未授权），R3-B 需将输入源切换为直接 API fetch，decision 另行登记。

## R3-D002 — Identity expansion：只新增、不重生成

- **Decision**: 新交易日出现 core 中不存在的 ts_code（新上市/复牌）时，从**已注册的 stock_basic FILE artifact**（core.raw_artifacts 中 stock_basic CSV，R2 Part A 登记）解析 name/symbol/list_date，**新建** entity + instrument + 2 identifiers（新 UUIDv4）。**绝不改动已有 instrument_uid**（stable UID 契约，P-D001）。
- **Rationale**: A 股新上市/复牌是真实市场事件（本次实测 600984.SH 复牌、688835.SH 新上市）；不扩展身份则 mapping 永远无法 100%；扩展身份不是"重新生成 identity"（已有 UID 不动）。
- **Consequences**: 身份创建与 ingest_run 同事务（原子）；解析不到（core 与 stock_basic 均无）→ MappingGateError ABORT，不静默丢行。测试 T-R3A-SYNC-01/02/03/04。

## R3-D003 — Controlled upsert 幂等语义（延续 DB-D031）

- **Decision**: 增量 bar 写入使用 `INSERT ... ON CONFLICT(instrument_id, trade_date, adjustment_type, source_id) DO UPDATE SET ...`（同 source 覆盖，bar_id 稳定）；重跑同交易日 → row count 不增加。
- **Rationale**: 与 DB-D031 冻结语义一致；幂等是验收硬条件。
- **Consequences**: 测试 T-R3A-IDEMPOTENT-01。

## R3-D004 — 100% mapping gate（延续 DB-D037）

- **Decision**: 每交易日所有 ts_code 必须映射到恰一个 instrument；未知/歧义 → 事务回滚 + FAILED run 记录，0 行写入。
- **Rationale**: 延续 R1 严格 gate 语义；"未知 instrument 明确失败，不静默丢行"是验收条件。
- **Consequences**: 测试 T-R3A-UNKNOWN-01 / T-R3A-MAPPING-01。

## R3-D005 — Lineage 契约：run + artifact + source 全链

- **Decision**: 每次入库 = 1 ingest_run（trigger MANUAL/SCHEDULED/BACKFILL）+ 1 raw_artifact（FILE，content_hash=文件 sha256）+ bars 全行引用 source_id/ingest_run_id/raw_artifact_id；post-validation `loaded == expected` 不通过 → 回滚 + FAILED run。
- **Rationale**: 可追溯性验收；DB-D027（UTC 时间戳）/ DB-D034（BEGIN IMMEDIATE + parameterized + 应用层 commit/rollback）延续。
- **Consequences**: 测试 T-R3A-LINEAGE-01 / T-R3A-LOAD-01。

## R3-D006 — Production 写入授权边界

- **Decision**: `ingest_daily.py` 默认 `PRODUCTION_WRITES_ENABLED=False`；写 production core.db 必须显式 `--allow-production`（R3-A 由 Berlin 本轮授权）。reconcile 模式只读。
- **Rationale**: 延续 migrate.py 的 production guard 模式；防止 cron 误写。
- **Consequences**: 测试 T-R3A-GUARD-01。
