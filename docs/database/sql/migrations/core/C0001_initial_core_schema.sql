-- =============================================================================
-- C0001_initial_core_schema.sql — core.db 初始 schema（CANONICAL EXECUTABLE SOURCE）
-- =============================================================================
-- Market Monitor core.db — PUBLIC canonical database
-- R1A v2 FROZEN (Berlin approved 2026-08-22) | R1B migration C0001
--
-- 权威来源声明（DB-D029）：
--   * Migration files are canonical executable source.
--   * Consolidated schema (docs/database/sql/core_schema_v1.sql) is a
--     review snapshot derived from this file. Do not edit the snapshot
--     directly; edit this migration and regenerate the snapshot.
--
-- 执行方式：R1C 经 migration runner（stdlib sqlite3）按序执行；
--   本文件在事务中运行，成功后写入 schema_migrations(C0001, sha256, ...)。
--   本文件不手工执行。
--
-- 全局约定（FROZEN R1A v2 / R1B decisions）：
--   * ID: INTEGER PRIMARY KEY = 单库内部 surrogate；禁止跨库引用。
--   * UID: TEXT(36) UUIDv4，application 生成；CHECK(length=36)，格式校验在应用层。
--   * Timestamps: TEXT UTC ISO-8601，application 显式写入（DB-D027），不用 CURRENT_TIMESTAMP。
--   * Calendar date: TEXT 'YYYY-MM-DD'。
--   * Boolean: INTEGER CHECK(value IN (0,1))。
--   * JSON: TEXT，应用层校验（DB-D028），不硬依赖 JSON1。
--   * content_hash: TEXT(64) SHA-256 hex。
--   * 金额/价格: REAL。
--   * Enum: SQL CHECK + 应用层常量。
-- =============================================================================

-- 运行时连接级 PRAGMA 由 runner 设置（foreign_keys=ON, journal_mode=WAL, synchronous=NORMAL）
-- 不写入 migration 文件（DB-D027 约定：runtime PRAGMA 与 schema DDL 分开记录）。

-- ---------------------------------------------------------------------------
-- 1. data_sources
-- ---------------------------------------------------------------------------
CREATE TABLE data_sources (
    source_id   INTEGER PRIMARY KEY,
    source_code TEXT    NOT NULL UNIQUE,
    source_name TEXT    NOT NULL,
    source_type TEXT    NOT NULL CHECK (source_type IN (
        'MARKET_DATA','FUNDAMENTALS','MACRO','FILINGS','NEWS','MANUAL'
    )),
    base_url    TEXT,
    status      TEXT    NOT NULL DEFAULT 'ACTIVE' CHECK (status IN (
        'ACTIVE','DEGRADED','SUSPENDED'
    )),
    notes       TEXT,
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL
);
-- 注：无 priority 字段（F3/DB-D018）。

-- ---------------------------------------------------------------------------
-- 2. datasets（无 primary_source_id，F2/DB-D018）
-- ---------------------------------------------------------------------------
CREATE TABLE datasets (
    dataset_id   INTEGER PRIMARY KEY,
    dataset_code TEXT    NOT NULL UNIQUE,
    dataset_name TEXT    NOT NULL,
    dataset_type TEXT    NOT NULL CHECK (dataset_type IN (
        'PRICE_DAILY','PRICE_MINUTE','FINANCIAL','MACRO','FILINGS','EVENTS'
    )),
    granularity  TEXT    NOT NULL CHECK (granularity IN (
        'DAILY','MINUTE','QUARTERLY','ANNUAL','EVENT'
    )),
    target_table TEXT,
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

-- ---------------------------------------------------------------------------
-- 3. dataset_sources（F4/DB-D019）
-- ---------------------------------------------------------------------------
CREATE TABLE dataset_sources (
    dataset_source_id INTEGER PRIMARY KEY,
    dataset_id        INTEGER NOT NULL REFERENCES datasets(dataset_id),
    source_id         INTEGER NOT NULL REFERENCES data_sources(source_id),
    role              TEXT    NOT NULL CHECK (role IN (
        'PRIMARY','FALLBACK','ARCHIVE'
    )),
    priority_rank     INTEGER NOT NULL,
    is_active         INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    notes             TEXT,
    created_at        TEXT    NOT NULL,
    updated_at        TEXT    NOT NULL,
    UNIQUE (dataset_id, source_id),
    UNIQUE (dataset_id, priority_rank)
);
CREATE UNIQUE INDEX ux_dataset_sources_active_primary
    ON dataset_sources(dataset_id)
    WHERE role = 'PRIMARY' AND is_active = 1;

-- ---------------------------------------------------------------------------
-- 4. entities（B2 canonical_name 非唯一；B3 entity_uid）
-- ---------------------------------------------------------------------------
CREATE TABLE entities (
    entity_id      INTEGER PRIMARY KEY,
    entity_uid     TEXT    NOT NULL UNIQUE CHECK (length(entity_uid) = 36),
    canonical_name TEXT    NOT NULL,
    entity_type    TEXT    NOT NULL CHECK (entity_type IN (
        'COMPANY','GOVERNMENT','INDEX_PROVIDER','ETF_ISSUER',
        'FUND_MANAGER','SUPRA_NATIONAL','OTHER'
    )),
    country_code   TEXT,
    status         TEXT    NOT NULL DEFAULT 'ACTIVE' CHECK (status IN (
        'ACTIVE','INACTIVE','MERGED','DELISTED'
    )),
    created_at     TEXT    NOT NULL,
    updated_at     TEXT    NOT NULL
);

-- ---------------------------------------------------------------------------
-- 5. entity_identifiers（B1）
-- ---------------------------------------------------------------------------
CREATE TABLE entity_identifiers (
    entity_identifier_id INTEGER PRIMARY KEY,
    entity_id            INTEGER NOT NULL REFERENCES entities(entity_id),
    provider             TEXT    NOT NULL,
    identifier_type      TEXT    NOT NULL CHECK (identifier_type IN (
        'LEI','SEC_CIK','PROVIDER_COMPANY_ID','GLEIF','OTHER'
    )),
    identifier           TEXT    NOT NULL,
    valid_from           TEXT    NOT NULL,
    valid_to             TEXT,
    is_primary           INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0,1)),
    created_at           TEXT    NOT NULL,
    UNIQUE (provider, identifier_type, identifier, valid_to)
);
CREATE UNIQUE INDEX ux_entity_identifiers_current
    ON entity_identifiers(provider, identifier_type, identifier)
    WHERE valid_to IS NULL;
CREATE INDEX idx_entity_identifiers_entity
    ON entity_identifiers(entity_id);

-- ---------------------------------------------------------------------------
-- 6. instruments（F1 无 symbol 复合 UNIQUE）
-- ---------------------------------------------------------------------------
CREATE TABLE instruments (
    instrument_id   INTEGER PRIMARY KEY,
    instrument_uid  TEXT    NOT NULL UNIQUE CHECK (length(instrument_uid) = 36),
    entity_id       INTEGER REFERENCES entities(entity_id),
    instrument_type TEXT    NOT NULL CHECK (instrument_type IN (
        'EQUITY','ADR','ETF','INDEX','FX','FUTURE','OPTION',
        'BOND','COMMODITY','CRYPTO'
    )),
    primary_symbol  TEXT    NOT NULL,
    exchange_code   TEXT    NOT NULL,
    currency_code   TEXT    NOT NULL,
    country_code    TEXT,
    status          TEXT    NOT NULL DEFAULT 'ACTIVE' CHECK (status IN (
        'ACTIVE','SUSPENDED','DELISTED','PENDING'
    )),
    listing_date    TEXT,
    delisting_date  TEXT,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL
);
CREATE INDEX idx_instruments_entity ON instruments(entity_id);

-- ---------------------------------------------------------------------------
-- 7. instrument_identifiers（B1）
-- ---------------------------------------------------------------------------
CREATE TABLE instrument_identifiers (
    identifier_id   INTEGER PRIMARY KEY,
    instrument_id   INTEGER NOT NULL REFERENCES instruments(instrument_id),
    provider        TEXT    NOT NULL,
    identifier_type TEXT    NOT NULL CHECK (identifier_type IN (
        'TICKER','EXCHANGE_SYMBOL','ISIN','CUSIP','SEDOL','FIGI','CURRENCY_PAIR'
    )),
    identifier      TEXT    NOT NULL,
    valid_from      TEXT    NOT NULL,
    valid_to        TEXT,
    is_primary      INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0,1)),
    created_at      TEXT    NOT NULL,
    UNIQUE (provider, identifier_type, identifier, valid_to)
);
CREATE UNIQUE INDEX ux_instrument_identifiers_current
    ON instrument_identifiers(provider, identifier_type, identifier)
    WHERE valid_to IS NULL;
CREATE INDEX idx_instrument_identifiers_instrument
    ON instrument_identifiers(instrument_id);

-- ---------------------------------------------------------------------------
-- 8. ingest_runs
-- ---------------------------------------------------------------------------
CREATE TABLE ingest_runs (
    run_id        INTEGER PRIMARY KEY,
    dataset_id    INTEGER NOT NULL REFERENCES datasets(dataset_id),
    source_id     INTEGER NOT NULL REFERENCES data_sources(source_id),
    trigger_type  TEXT    NOT NULL CHECK (trigger_type IN (
        'SCHEDULED','MANUAL','BACKFILL'
    )),
    started_at    TEXT    NOT NULL,
    finished_at   TEXT,
    status        TEXT    NOT NULL DEFAULT 'RUNNING' CHECK (status IN (
        'RUNNING','SUCCESS','FAILED','PARTIAL'
    )),
    rows_expected INTEGER,
    rows_loaded   INTEGER,
    notes         TEXT,
    UNIQUE (dataset_id, source_id, started_at)
);
CREATE INDEX idx_ingest_runs_dataset_start
    ON ingest_runs(dataset_id, started_at);

-- ---------------------------------------------------------------------------
-- 9. raw_artifacts（B12 Core；F5 hash 语义）
-- ---------------------------------------------------------------------------
CREATE TABLE raw_artifacts (
    artifact_id           INTEGER PRIMARY KEY,
    artifact_uid          TEXT    NOT NULL UNIQUE CHECK (length(artifact_uid) = 36),
    dataset_id            INTEGER NOT NULL REFERENCES datasets(dataset_id),
    source_id             INTEGER NOT NULL REFERENCES data_sources(source_id),
    run_id                INTEGER REFERENCES ingest_runs(run_id),
    artifact_type         TEXT    NOT NULL CHECK (artifact_type IN (
        'FILE','URL','API_PAYLOAD','DB_SNAPSHOT','ARCHIVE','OTHER'
    )),
    local_path_or_reference TEXT,
    content_hash          TEXT    NOT NULL CHECK (length(content_hash) = 64),
    retrieved_at          TEXT    NOT NULL,
    metadata              TEXT,
    created_at            TEXT    NOT NULL
);
CREATE INDEX idx_raw_artifacts_hash
    ON raw_artifacts(content_hash);
CREATE UNIQUE INDEX ux_raw_artifacts_run_hash
    ON raw_artifacts(run_id, content_hash)
    WHERE run_id IS NOT NULL;
CREATE INDEX idx_raw_artifacts_dataset_source_run
    ON raw_artifacts(dataset_id, source_id, run_id);

-- ---------------------------------------------------------------------------
-- 10. data_gaps
-- ---------------------------------------------------------------------------
CREATE TABLE data_gaps (
    gap_id         INTEGER PRIMARY KEY,
    dataset_id     INTEGER NOT NULL REFERENCES datasets(dataset_id),
    instrument_id  INTEGER REFERENCES instruments(instrument_id),
    related_run_id INTEGER REFERENCES ingest_runs(run_id),
    gap_date       TEXT,
    status         TEXT    NOT NULL DEFAULT 'OPEN' CHECK (status IN (
        'OPEN','INVESTIGATING','RESOLVED','WONT_FIX'
    )),
    resolution     TEXT,
    notes          TEXT,
    created_at     TEXT    NOT NULL,
    updated_at     TEXT    NOT NULL
);
CREATE INDEX idx_data_gaps_dataset_status
    ON data_gaps(dataset_id, status);

-- ---------------------------------------------------------------------------
-- 11. market_prices_daily（B13 血缘）
-- ---------------------------------------------------------------------------
CREATE TABLE market_prices_daily (
    bar_id          INTEGER PRIMARY KEY,
    instrument_id   INTEGER NOT NULL REFERENCES instruments(instrument_id),
    trade_date      TEXT    NOT NULL,
    open            REAL    NOT NULL,
    high            REAL    NOT NULL,
    low             REAL    NOT NULL,
    close           REAL    NOT NULL,
    volume          REAL    NOT NULL,
    volume_unit     TEXT    NOT NULL CHECK (volume_unit IN (
        'LOTS','SHARES','CONTRACTS','UNITS','OTHER'
    )),
    turnover        REAL    NOT NULL,
    turnover_unit   TEXT    NOT NULL CHECK (turnover_unit IN (
        'THOUSAND_CNY','CNY','USD','HKD','OTHER'
    )),
    currency_code   TEXT    NOT NULL,
    adjustment_type TEXT    NOT NULL CHECK (adjustment_type IN (
        'RAW','FWD','BWD','NONE'
    )),
    source_id       INTEGER NOT NULL REFERENCES data_sources(source_id),
    ingest_run_id   INTEGER NOT NULL REFERENCES ingest_runs(run_id),
    raw_artifact_id INTEGER REFERENCES raw_artifacts(artifact_id),
    ingested_at     TEXT    NOT NULL,
    UNIQUE (instrument_id, trade_date, adjustment_type, source_id)
);
CREATE INDEX idx_mpd_instrument_date
    ON market_prices_daily(instrument_id, trade_date);
CREATE INDEX idx_mpd_trade_date
    ON market_prices_daily(trade_date);
CREATE INDEX idx_mpd_ingest_run
    ON market_prices_daily(ingest_run_id);
CREATE INDEX idx_mpd_source
    ON market_prices_daily(source_id);

-- ---------------------------------------------------------------------------
-- 12. events（B10；F7 discovered_by_source_id）
-- ---------------------------------------------------------------------------
CREATE TABLE events (
    event_id                INTEGER PRIMARY KEY,
    event_uid               TEXT    NOT NULL UNIQUE CHECK (length(event_uid) = 36),
    fingerprint             TEXT    NOT NULL UNIQUE,
    discovered_by_source_id INTEGER REFERENCES data_sources(source_id),
    event_type              TEXT    NOT NULL,
    event_time              TEXT,
    event_timezone          TEXT,
    title                   TEXT    NOT NULL,
    summary                 TEXT,
    status                  TEXT    NOT NULL DEFAULT 'NEW' CHECK (status IN (
        'NEW','CONFIRMED','SUPERSEDED','REJECTED'
    )),
    created_at              TEXT    NOT NULL,
    updated_at              TEXT    NOT NULL
);
CREATE INDEX idx_events_type_time
    ON events(event_type, event_time);
CREATE INDEX idx_events_discovered_by
    ON events(discovered_by_source_id);

-- ---------------------------------------------------------------------------
-- 13. event_entities（B10；DB-D026 可控可变）
-- ---------------------------------------------------------------------------
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
CREATE INDEX idx_event_entities_entity
    ON event_entities(entity_id);

-- ---------------------------------------------------------------------------
-- 14. event_instruments（B10；DB-D026 可控可变）
-- ---------------------------------------------------------------------------
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

-- ---------------------------------------------------------------------------
-- 15. event_evidence（B11；F6 + DB-D032 evidence_key）
-- ---------------------------------------------------------------------------
CREATE TABLE event_evidence (
    evidence_id      INTEGER PRIMARY KEY,
    evidence_uid     TEXT    NOT NULL UNIQUE CHECK (length(evidence_uid) = 36),
    event_id         INTEGER NOT NULL REFERENCES events(event_id),
    source_id        INTEGER NOT NULL REFERENCES data_sources(source_id),
    evidence_key     TEXT    NOT NULL,
    evidence_type    TEXT    NOT NULL CHECK (evidence_type IN (
        'HKEX_FILING','SEC_FILING','COMPANY_IR','NEWS',
        'API_PAYLOAD','MANUAL','OTHER'
    )),
    source_reference TEXT,
    published_at     TEXT,
    detected_at      TEXT    NOT NULL,
    content_hash     TEXT    NOT NULL CHECK (length(content_hash) = 64),
    is_primary       INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0,1)),
    metadata         TEXT,
    created_at       TEXT    NOT NULL,
    UNIQUE (event_id, evidence_key)
);
CREATE UNIQUE INDEX ux_event_evidence_primary
    ON event_evidence(event_id)
    WHERE is_primary = 1;
CREATE INDEX idx_event_evidence_hash
    ON event_evidence(content_hash);
CREATE INDEX idx_event_evidence_detected
    ON event_evidence(detected_at);

-- ---------------------------------------------------------------------------
-- 16. event_analysis（B7 generic；F8B analysis_uid）
-- ---------------------------------------------------------------------------
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
    bullish_points     TEXT,
    bearish_points     TEXT,
    recommended_attention TEXT,
    raw_output         TEXT,
    created_at         TEXT    NOT NULL,
    UNIQUE (event_id, model_provider, model_id, prompt_version, analysis_version)
);
CREATE INDEX idx_event_analysis_event
    ON event_analysis(event_id);

-- ---------------------------------------------------------------------------
-- 17. schema_migrations（infra；core.db 独立历史 C0001...，DB-D030）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS schema_migrations (
    migration_id TEXT PRIMARY KEY,
    checksum     TEXT    NOT NULL CHECK (length(checksum) = 64),
    applied_at   TEXT    NOT NULL,
    description  TEXT,
    execution_ms INTEGER
);
