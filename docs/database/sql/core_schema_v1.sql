-- =============================================================================
-- core_schema_v1.sql — core.db 完整 schema（REVIEW SNAPSHOT）
-- =============================================================================
-- Market Monitor core.db — PUBLIC canonical database
-- R1A v2 FROZEN (Berlin approved 2026-08-22) | R1B DDL specification
--
-- 说明：
--   * 本文件是 consolidated REVIEW SNAPSHOT，用于人工审查。
--   * 可执行权威来源 = docs/database/sql/migrations/core/C0001_initial_core_schema.sql
--     （DB-D029：Migration files are canonical executable source；
--       consolidated schema files are review snapshots）
--   * 本文件不执行；执行由 R1C 经 migration runner 进行。
--   * 跨库引用（private.db → core.db）用 *_uid TEXT，应用层校验，无伪 FK。
--
-- 全局约定（FROZEN R1A v2 / R1B decisions）：
--   * ID: INTEGER PRIMARY KEY = 单库内部 surrogate；禁止跨库引用。
--   * UID: TEXT(36) UUIDv4，application 生成（stdlib uuid.uuid4()），
--     lowercase canonical；CHECK(length=36) 仅长度，格式校验在应用层。
--   * Timestamps: TEXT UTC ISO-8601（如 2026-08-22T02:30:00Z），
--     一律由 application layer 显式写入，不用 SQLite CURRENT_TIMESTAMP（DB-D027）。
--   * Calendar date: TEXT 'YYYY-MM-DD'。
--   * Boolean: INTEGER CHECK(value IN (0,1))。
--   * JSON: TEXT（有效 JSON），校验在 application layer，不硬依赖 JSON1（DB-D028）。
--   * content_hash: TEXT(64) SHA-256 hex。
--   * 金额/价格: REAL（R1 不引入 Decimal storage）。
--   * Enum: SQL CHECK + 应用层常量。
-- =============================================================================

PRAGMA foreign_keys = ON;  -- 运行时连接级 PRAGMA；DDL 与 runtime PRAGMA 分开记录

-- =============================================================================
-- 1. data_sources — 数据源定义（无 FK）
-- =============================================================================
CREATE TABLE data_sources (
    source_id   INTEGER PRIMARY KEY,
    source_code TEXT    NOT NULL UNIQUE,          -- 稳定代码，如 'TUSHARE'
    source_name TEXT    NOT NULL,                 -- 全名
    source_type TEXT    NOT NULL CHECK (source_type IN (
        'MARKET_DATA','FUNDAMENTALS','MACRO','FILINGS','NEWS','MANUAL'
    )),
    base_url    TEXT,                             -- API 基址（可空）
    status      TEXT    NOT NULL DEFAULT 'ACTIVE' CHECK (status IN (
        'ACTIVE','DEGRADED','SUSPENDED'
    )),
    notes       TEXT,
    created_at  TEXT    NOT NULL,                 -- UTC ISO-8601（app 写入）
    updated_at  TEXT    NOT NULL                  -- UTC ISO-8601（app 写入）
);
-- 注：data_sources 不含 priority 字段（F3/DB-D018）；
--     source precedence 完全由 dataset_sources(role + priority_rank) 定义。

-- =============================================================================
-- 2. datasets — 逻辑数据集定义（无 FK；primary_source_id 已删除 F2/DB-D018）
-- =============================================================================
CREATE TABLE datasets (
    dataset_id   INTEGER PRIMARY KEY,
    dataset_code TEXT    NOT NULL UNIQUE,         -- 如 'CN_EQUITY_DAILY'
    dataset_name TEXT    NOT NULL,
    dataset_type TEXT    NOT NULL CHECK (dataset_type IN (
        'PRICE_DAILY','PRICE_MINUTE','FINANCIAL','MACRO','FILINGS','EVENTS'
    )),
    granularity  TEXT    NOT NULL CHECK (granularity IN (
        'DAILY','MINUTE','QUARTERLY','ANNUAL','EVENT'
    )),
    target_table TEXT,                            -- 写入的 canonical 表
    write_mode   TEXT    NOT NULL CHECK (write_mode IN (
        'APPEND','UPSERT','SNAPSHOT'
    )),
    status       TEXT    NOT NULL DEFAULT 'ACTIVE' CHECK (status IN (
        'ACTIVE','DEGRADED','SUSPENDED'
    )),
    notes        TEXT,
    created_at   TEXT    NOT NULL,
    updated_at   TEXT    NOT NULL
);

-- =============================================================================
-- 3. dataset_sources — 数据集 × 源 × 优先级（F4/DB-D019）
-- =============================================================================
CREATE TABLE dataset_sources (
    dataset_source_id INTEGER PRIMARY KEY,
    dataset_id        INTEGER NOT NULL REFERENCES datasets(dataset_id),
    source_id         INTEGER NOT NULL REFERENCES data_sources(source_id),
    role              TEXT    NOT NULL CHECK (role IN (
        'PRIMARY','FALLBACK','ARCHIVE'
    )),
    priority_rank     INTEGER NOT NULL,           -- 数字越小越优先（PRIMARY=1）
    is_active         INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    notes             TEXT,
    created_at        TEXT    NOT NULL,
    updated_at        TEXT    NOT NULL,
    UNIQUE (dataset_id, source_id),
    UNIQUE (dataset_id, priority_rank)
);
-- 每个 dataset 至多一个 active PRIMARY（F4）：partial unique index
CREATE UNIQUE INDEX ux_dataset_sources_active_primary
    ON dataset_sources(dataset_id)
    WHERE role = 'PRIMARY' AND is_active = 1;

-- =============================================================================
-- 4. entities — 经济主体（B2/B3）
-- =============================================================================
CREATE TABLE entities (
    entity_id     INTEGER PRIMARY KEY,
    entity_uid    TEXT    NOT NULL UNIQUE CHECK (length(entity_uid) = 36),
    canonical_name TEXT   NOT NULL,               -- 展示/搜索名；NOT UNIQUE（B2）
    entity_type   TEXT    NOT NULL CHECK (entity_type IN (
        'COMPANY','GOVERNMENT','INDEX_PROVIDER','ETF_ISSUER',
        'FUND_MANAGER','SUPRA_NATIONAL','OTHER'
    )),
    country_code  TEXT,                           -- ISO 3166-1 alpha-2
    status        TEXT    NOT NULL DEFAULT 'ACTIVE' CHECK (status IN (
        'ACTIVE','INACTIVE','MERGED','DELISTED'
    )),
    created_at    TEXT    NOT NULL,
    updated_at    TEXT    NOT NULL
);

-- =============================================================================
-- 5. entity_identifiers — Entity 级标识（B1）
-- =============================================================================
CREATE TABLE entity_identifiers (
    entity_identifier_id INTEGER PRIMARY KEY,
    entity_id            INTEGER NOT NULL REFERENCES entities(entity_id),
    provider             TEXT    NOT NULL,        -- SEC/LEI_PROVIDER/FMP/...
    identifier_type      TEXT    NOT NULL CHECK (identifier_type IN (
        'LEI','SEC_CIK','PROVIDER_COMPANY_ID','GLEIF','OTHER'
    )),
    identifier           TEXT    NOT NULL,        -- LEI / SEC CIK / provider id
    valid_from           TEXT    NOT NULL,        -- 'YYYY-MM-DD'
    valid_to             TEXT,                    -- NULL = 当前有效
    is_primary           INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0,1)),
    created_at           TEXT    NOT NULL,
    UNIQUE (provider, identifier_type, identifier, valid_to)
);
-- 当前有效映射唯一（ticker/标识历史区间并存）
CREATE UNIQUE INDEX ux_entity_identifiers_current
    ON entity_identifiers(provider, identifier_type, identifier)
    WHERE valid_to IS NULL;
CREATE INDEX idx_entity_identifiers_entity
    ON entity_identifiers(entity_id);

-- =============================================================================
-- 6. instruments — 金融工具（B3/F1）
-- =============================================================================
CREATE TABLE instruments (
    instrument_id   INTEGER PRIMARY KEY,
    instrument_uid  TEXT    NOT NULL UNIQUE CHECK (length(instrument_uid) = 36),
    entity_id       INTEGER REFERENCES entities(entity_id),  -- NULL=指数/FX
    instrument_type TEXT    NOT NULL CHECK (instrument_type IN (
        'EQUITY','ADR','ETF','INDEX','FX','FUTURE','OPTION',
        'BOND','COMMODITY','CRYPTO'
    )),
    primary_symbol  TEXT    NOT NULL,             -- 展示/便利字段；NOT UNIQUE（F1）
    exchange_code   TEXT    NOT NULL,             -- ISO 10383 MIC；非交易所 'NONE'
    currency_code   TEXT    NOT NULL,             -- ISO 4217
    country_code    TEXT,
    status          TEXT    NOT NULL DEFAULT 'ACTIVE' CHECK (status IN (
        'ACTIVE','SUSPENDED','DELISTED','PENDING'
    )),
    listing_date    TEXT,                         -- 'YYYY-MM-DD'
    delisting_date  TEXT,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL
);
-- 注：无 UNIQUE(instrument_type, primary_symbol, exchange_code)（F1/DB-D017）；
--     ticker 历史唯一性由 instrument_identifiers 控制。
CREATE INDEX idx_instruments_entity ON instruments(entity_id);

-- =============================================================================
-- 7. instrument_identifiers — Instrument 级标识（B1）
-- =============================================================================
CREATE TABLE instrument_identifiers (
    identifier_id   INTEGER PRIMARY KEY,
    instrument_id   INTEGER NOT NULL REFERENCES instruments(instrument_id),
    provider        TEXT    NOT NULL,             -- TUSHARE/FMP/STANDARD/...
    identifier_type TEXT    NOT NULL CHECK (identifier_type IN (
        'TICKER','EXCHANGE_SYMBOL','ISIN','CUSIP','SEDOL','FIGI','CURRENCY_PAIR'
    )),
    identifier      TEXT    NOT NULL,             -- ts_code / ISIN / CUSIP / ...
    valid_from      TEXT    NOT NULL,
    valid_to        TEXT,                         -- NULL = 当前有效
    is_primary      INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0,1)),
    created_at      TEXT    NOT NULL,
    UNIQUE (provider, identifier_type, identifier, valid_to)
);
CREATE UNIQUE INDEX ux_instrument_identifiers_current
    ON instrument_identifiers(provider, identifier_type, identifier)
    WHERE valid_to IS NULL;
CREATE INDEX idx_instrument_identifiers_instrument
    ON instrument_identifiers(instrument_id);

-- =============================================================================
-- 8. ingest_runs — 抓取运行审计
-- =============================================================================
CREATE TABLE ingest_runs (
    run_id        INTEGER PRIMARY KEY,
    dataset_id    INTEGER NOT NULL REFERENCES datasets(dataset_id),
    source_id     INTEGER NOT NULL REFERENCES data_sources(source_id),
    trigger_type  TEXT    NOT NULL CHECK (trigger_type IN (
        'SCHEDULED','MANUAL','BACKFILL'
    )),
    started_at    TEXT    NOT NULL,               -- UTC ISO-8601
    finished_at   TEXT,
    status        TEXT    NOT NULL DEFAULT 'RUNNING' CHECK (status IN (
        'RUNNING','SUCCESS','FAILED','PARTIAL'
    )),
    rows_expected INTEGER,
    rows_loaded   INTEGER,
    notes         TEXT,
    UNIQUE (dataset_id, source_id, started_at)    -- 防重复审计
);
CREATE INDEX idx_ingest_runs_dataset_start
    ON ingest_runs(dataset_id, started_at);

-- =============================================================================
-- 9. raw_artifacts — 原始证据存档（B12 提升 Core；F5 hash 语义）
-- =============================================================================
CREATE TABLE raw_artifacts (
    artifact_id           INTEGER PRIMARY KEY,
    artifact_uid          TEXT    NOT NULL UNIQUE CHECK (length(artifact_uid) = 36),
    dataset_id            INTEGER NOT NULL REFERENCES datasets(dataset_id),
    source_id             INTEGER NOT NULL REFERENCES data_sources(source_id),
    run_id                INTEGER REFERENCES ingest_runs(run_id),  -- NULL=手工
    artifact_type         TEXT    NOT NULL CHECK (artifact_type IN (
        'FILE','URL','API_PAYLOAD','DB_SNAPSHOT','ARCHIVE','OTHER'
    )),
    local_path_or_reference TEXT,                 -- 本地路径或 URL
    content_hash          TEXT    NOT NULL CHECK (length(content_hash) = 64),
    retrieved_at          TEXT    NOT NULL,       -- UTC ISO-8601
    metadata              TEXT,                   -- JSON（app 校验）
    created_at            TEXT    NOT NULL
);
-- 相同内容可在不同 run / 不同 source 重复登记（provenance，F5/DB-D020）
CREATE INDEX idx_raw_artifacts_hash
    ON raw_artifacts(content_hash);
-- 同一次 run 内防重复 artifact
CREATE UNIQUE INDEX ux_raw_artifacts_run_hash
    ON raw_artifacts(run_id, content_hash)
    WHERE run_id IS NOT NULL;
CREATE INDEX idx_raw_artifacts_dataset_source_run
    ON raw_artifacts(dataset_id, source_id, run_id);

-- =============================================================================
-- 10. data_gaps — 数据缺口登记
-- =============================================================================
CREATE TABLE data_gaps (
    gap_id        INTEGER PRIMARY KEY,
    dataset_id    INTEGER NOT NULL REFERENCES datasets(dataset_id),
    instrument_id INTEGER REFERENCES instruments(instrument_id),  -- NULL=非标的级
    related_run_id INTEGER REFERENCES ingest_runs(run_id),        -- NULL=手工
    gap_date      TEXT,                          -- 'YYYY-MM-DD'
    status        TEXT    NOT NULL DEFAULT 'OPEN' CHECK (status IN (
        'OPEN','INVESTIGATING','RESOLVED','WONT_FIX'
    )),
    resolution    TEXT,
    notes         TEXT,
    created_at    TEXT    NOT NULL,
    updated_at    TEXT    NOT NULL
);
CREATE INDEX idx_data_gaps_dataset_status
    ON data_gaps(dataset_id, status);

-- =============================================================================
-- 11. market_prices_daily — 标准化日线（B13 血缘）
-- =============================================================================
CREATE TABLE market_prices_daily (
    bar_id          INTEGER PRIMARY KEY,
    instrument_id   INTEGER NOT NULL REFERENCES instruments(instrument_id),
    trade_date      TEXT    NOT NULL,            -- 'YYYY-MM-DD'
    open            REAL    NOT NULL,
    high            REAL    NOT NULL,
    low             REAL    NOT NULL,
    close           REAL    NOT NULL,
    volume          REAL    NOT NULL,            -- provider raw 数值（不换算）
    volume_unit     TEXT    NOT NULL CHECK (volume_unit IN (
        'LOTS','SHARES','CONTRACTS','UNITS','OTHER'
    )),
    turnover        REAL    NOT NULL,
    turnover_unit   TEXT    NOT NULL CHECK (turnover_unit IN (
        'THOUSAND_CNY','CNY','USD','HKD','OTHER'
    )),
    currency_code   TEXT    NOT NULL,            -- ISO 4217
    adjustment_type TEXT    NOT NULL CHECK (adjustment_type IN (
        'RAW','FWD','BWD','NONE'
    )),
    source_id       INTEGER NOT NULL REFERENCES data_sources(source_id),
    ingest_run_id   INTEGER NOT NULL REFERENCES ingest_runs(run_id),   -- B13
    raw_artifact_id INTEGER REFERENCES raw_artifacts(artifact_id),     -- B13 可选
    ingested_at     TEXT    NOT NULL,            -- UTC ISO-8601
    UNIQUE (instrument_id, trade_date, adjustment_type, source_id)
);
-- 血缘：bar → ingest_run → (source, dataset, time) → raw_artifact（可选）
CREATE INDEX idx_mpd_instrument_date
    ON market_prices_daily(instrument_id, trade_date);
CREATE INDEX idx_mpd_trade_date
    ON market_prices_daily(trade_date);
CREATE INDEX idx_mpd_ingest_run
    ON market_prices_daily(ingest_run_id);
CREATE INDEX idx_mpd_source
    ON market_prices_daily(source_id);

-- =============================================================================
-- 12. events — 事件事实（B10 多主体；F7 discovered_by_source_id）
-- =============================================================================
CREATE TABLE events (
    event_id              INTEGER PRIMARY KEY,
    event_uid             TEXT    NOT NULL UNIQUE CHECK (length(event_uid) = 36),
    fingerprint           TEXT    NOT NULL UNIQUE,  -- 应用层生成；R4 定义算法
    discovered_by_source_id INTEGER REFERENCES data_sources(source_id), -- NULL=人工
    event_type            TEXT    NOT NULL,       -- 受控清单 + 应用层校验
    event_time            TEXT,                   -- UTC ISO-8601
    event_timezone        TEXT,                   -- IANA（如 Asia/Shanghai）
    title                 TEXT    NOT NULL,
    summary               TEXT,
    status                TEXT    NOT NULL DEFAULT 'NEW' CHECK (status IN (
        'NEW','CONFIRMED','SUPERSEDED','REJECTED'
    )),
    created_at            TEXT    NOT NULL,
    updated_at            TEXT    NOT NULL
);
CREATE INDEX idx_events_type_time
    ON events(event_type, event_time);
CREATE INDEX idx_events_discovered_by
    ON events(discovered_by_source_id);

-- =============================================================================
-- 13. event_entities — 事件主体（多 Entity）（B10；DB-D026 可控可变）
-- =============================================================================
CREATE TABLE event_entities (
    event_entity_id INTEGER PRIMARY KEY,
    event_id        INTEGER NOT NULL REFERENCES events(event_id),
    entity_id       INTEGER NOT NULL REFERENCES entities(entity_id),
    role            TEXT    NOT NULL CHECK (role IN (
        'PRIMARY','ACQUIRER','TARGET','ISSUER','AFFECTED','RELATED'
    )),
    created_at      TEXT    NOT NULL,
    UNIQUE (event_id, entity_id, role)
);
-- 纠错：DELETE incorrect relation + INSERT corrected（DB-D026，无 status/valid_to）
CREATE INDEX idx_event_entities_entity
    ON event_entities(entity_id);

-- =============================================================================
-- 14. event_instruments — 事件相关工具（多 Instrument）（B10；DB-D026 可控可变）
-- =============================================================================
CREATE TABLE event_instruments (
    event_instrument_id INTEGER PRIMARY KEY,
    event_id            INTEGER NOT NULL REFERENCES events(event_id),
    instrument_id       INTEGER NOT NULL REFERENCES instruments(instrument_id),
    role                TEXT    NOT NULL CHECK (role IN (
        'PRIMARY','ACQUIRER','TARGET','ISSUER','AFFECTED','RELATED'
    )),
    created_at          TEXT    NOT NULL,
    UNIQUE (event_id, instrument_id, role)
);
CREATE INDEX idx_event_instruments_instrument
    ON event_instruments(instrument_id);

-- =============================================================================
-- 15. event_evidence — 多源事件证据（B11；F6 + DB-D032 evidence_key）
-- =============================================================================
CREATE TABLE event_evidence (
    evidence_id     INTEGER PRIMARY KEY,
    evidence_uid    TEXT    NOT NULL UNIQUE CHECK (length(evidence_uid) = 36),
    event_id        INTEGER NOT NULL REFERENCES events(event_id),
    source_id       INTEGER NOT NULL REFERENCES data_sources(source_id),
    evidence_key    TEXT    NOT NULL,             -- deterministic normalized key
    evidence_type   TEXT    NOT NULL CHECK (evidence_type IN (
        'HKEX_FILING','SEC_FILING','COMPANY_IR','NEWS',
        'API_PAYLOAD','MANUAL','OTHER'
    )),
    source_reference TEXT,                        -- URL/ref；可 NULL
    published_at    TEXT,                         -- UTC ISO-8601
    detected_at     TEXT    NOT NULL,             -- UTC ISO-8601
    content_hash    TEXT    NOT NULL CHECK (length(content_hash) = 64),
    is_primary      INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0,1)),
    metadata        TEXT,                         -- JSON
    created_at      TEXT    NOT NULL,
    UNIQUE (event_id, evidence_key)               -- DB-D032（方案 B）
);
-- evidence_key 生成规则（DB-D032）：provider native ID → normalized URL/ref
--   → artifact_uid → content-derived fallback（不用随机 UUID 做业务 dedup key）
-- 同内容不同 source 可共存（F6）；内容相同性检测走 content_hash 索引
CREATE UNIQUE INDEX ux_event_evidence_primary
    ON event_evidence(event_id)
    WHERE is_primary = 1;                         -- 每事件至多一条主证据
CREATE INDEX idx_event_evidence_hash
    ON event_evidence(content_hash);
CREATE INDEX idx_event_evidence_detected
    ON event_evidence(detected_at);

-- =============================================================================
-- 16. event_analysis — Generic 事件分析（B7 收敛；F8B analysis_uid）
-- =============================================================================
CREATE TABLE event_analysis (
    analysis_id        INTEGER PRIMARY KEY,
    analysis_uid       TEXT    NOT NULL UNIQUE CHECK (length(analysis_uid) = 36),
    event_id           INTEGER NOT NULL REFERENCES events(event_id),
    model_provider     TEXT    NOT NULL,
    model_id           TEXT    NOT NULL,
    prompt_version     TEXT    NOT NULL,
    analysis_version   TEXT    NOT NULL,
    importance_score   INTEGER CHECK (importance_score BETWEEN 1 AND 5),
    summary            TEXT,
    bullish_points     TEXT,                      -- JSON
    bearish_points     TEXT,                      -- JSON
    recommended_attention TEXT,
    raw_output         TEXT,                      -- JSON（模型原始输出）
    created_at         TEXT    NOT NULL,
    UNIQUE (event_id, model_provider, model_id, prompt_version, analysis_version)
);
-- 业务 UNIQUE 防重复；analysis_uid 负责稳定跨库 identity（F8B，两角色不混淆）
CREATE INDEX idx_event_analysis_event
    ON event_analysis(event_id);

-- =============================================================================
-- 17. schema_migrations — 迁移记录（infra，core.db 独立历史 C0001...）
-- =============================================================================
CREATE TABLE IF NOT EXISTS schema_migrations (
    migration_id TEXT PRIMARY KEY,                -- 如 'C0001'
    checksum     TEXT    NOT NULL CHECK (length(checksum) = 64),  -- SHA-256
    applied_at   TEXT    NOT NULL,                -- UTC ISO-8601（runner 写入）
    description  TEXT,
    execution_ms INTEGER
);
