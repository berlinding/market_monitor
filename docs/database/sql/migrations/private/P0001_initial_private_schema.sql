-- =============================================================================
-- P0001_initial_private_schema.sql — private.db 初始 schema（CANONICAL EXECUTABLE SOURCE）
-- =============================================================================
-- Market Monitor private.db — PRIVATE 数据库（持仓/账户/自选/thesis/告警）
-- R1A v2 FROZEN (Berlin approved 2026-08-22) | R1B migration P0001
--
-- 权威来源声明（DB-D029）：
--   * Migration files are canonical executable source.
--   * Consolidated schema (docs/database/sql/private_schema_v1.sql) is a
--     review snapshot derived from this file.
--
-- 执行方式：R1C 经 migration runner 按序执行；事务内运行，成功后写入
--   schema_migrations(P0001, sha256, ...)。本文件不手工执行。
--
-- 跨库引用（private.db → core.db）：entity_uid / instrument_uid / event_uid /
--   generic_analysis_uid 为 TEXT，无伪 FK，由应用层 validator 校验（见
--   "CROSS-DB REFERENCE" 注释）。同库关系使用原生 FK。
-- 全局约定同 core（UID/Timestamp/Boolean/JSON/REAL，见 C0001 头注）。
-- =============================================================================

-- ---------------------------------------------------------------------------
-- P-schema_migrations（private.db 独立迁移历史 P0001...，DB-D030）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS schema_migrations (
    migration_id TEXT PRIMARY KEY,
    checksum     TEXT    NOT NULL CHECK (length(checksum) = 64),
    applied_at   TEXT    NOT NULL,
    description  TEXT,
    execution_ms INTEGER
);

-- ---------------------------------------------------------------------------
-- 1. accounts（B5；F8A type 规范化）
-- ---------------------------------------------------------------------------
CREATE TABLE accounts (
    account_id   INTEGER PRIMARY KEY,
    account_uid  TEXT    NOT NULL UNIQUE CHECK (length(account_uid) = 36),
    account_name TEXT    NOT NULL UNIQUE,
    broker       TEXT,
    account_type TEXT    NOT NULL CHECK (account_type IN (
        'CASH','MARGIN','RETIREMENT','PAPER','OTHER'
    )),
    base_currency TEXT   NOT NULL,
    status       TEXT    NOT NULL DEFAULT 'ACTIVE' CHECK (status IN (
        'ACTIVE','CLOSED'
    )),
    created_at   TEXT    NOT NULL,
    updated_at   TEXT    NOT NULL
);
-- 注：不保存 password/token/credential（B5）。

-- ---------------------------------------------------------------------------
-- 2. positions（B6）
-- ---------------------------------------------------------------------------
CREATE TABLE positions (
    position_id    INTEGER PRIMARY KEY,
    account_id     INTEGER NOT NULL REFERENCES accounts(account_id),
    -- CROSS-DB REFERENCE: instrument_uid → core.instruments.instrument_uid
    -- validated by application layer against core.db (ensure_instrument_uid)
    instrument_uid TEXT    NOT NULL CHECK (length(instrument_uid) = 36),
    quantity       REAL    NOT NULL,
    avg_cost       REAL,
    currency_code  TEXT    NOT NULL,
    as_of_date     TEXT    NOT NULL,
    source         TEXT,
    status         TEXT    NOT NULL DEFAULT 'OPEN' CHECK (status IN (
        'OPEN','CLOSED'
    )),
    created_at     TEXT    NOT NULL,
    updated_at     TEXT    NOT NULL
);
CREATE UNIQUE INDEX ux_positions_open
    ON positions(account_id, instrument_uid)
    WHERE status = 'OPEN';
CREATE INDEX idx_positions_instrument
    ON positions(instrument_uid);

-- ---------------------------------------------------------------------------
-- 3. watchlists
-- ---------------------------------------------------------------------------
CREATE TABLE watchlists (
    watchlist_id INTEGER PRIMARY KEY,
    name         TEXT    NOT NULL UNIQUE,
    created_at   TEXT    NOT NULL,
    updated_at   TEXT    NOT NULL
);

-- ---------------------------------------------------------------------------
-- 4. watchlist_items（B4 XOR）
-- ---------------------------------------------------------------------------
CREATE TABLE watchlist_items (
    item_id        INTEGER PRIMARY KEY,
    watchlist_id   INTEGER NOT NULL REFERENCES watchlists(watchlist_id),
    -- CROSS-DB REFERENCES (XOR):
    --   entity_uid     → core.entities.entity_uid
    --   instrument_uid → core.instruments.instrument_uid
    entity_uid     TEXT CHECK (length(entity_uid) = 36),
    instrument_uid TEXT CHECK (length(instrument_uid) = 36),
    reason         TEXT,
    priority       INTEGER,
    status         TEXT    NOT NULL DEFAULT 'ACTIVE' CHECK (status IN (
        'ACTIVE','ARCHIVED'
    )),
    created_at     TEXT    NOT NULL,
    updated_at     TEXT    NOT NULL,
    CHECK (
        (entity_uid IS NOT NULL AND instrument_uid IS NULL)
        OR
        (entity_uid IS NULL AND instrument_uid IS NOT NULL)
    )
);
CREATE UNIQUE INDEX ux_watchlist_items_entity
    ON watchlist_items(watchlist_id, entity_uid)
    WHERE entity_uid IS NOT NULL;
CREATE UNIQUE INDEX ux_watchlist_items_instrument
    ON watchlist_items(watchlist_id, instrument_uid)
    WHERE instrument_uid IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 5. investment_theses
-- ---------------------------------------------------------------------------
CREATE TABLE investment_theses (
    thesis_id       INTEGER PRIMARY KEY,
    -- CROSS-DB REFERENCE: entity_uid → core.entities.entity_uid
    entity_uid      TEXT    NOT NULL CHECK (length(entity_uid) = 36),
    title           TEXT    NOT NULL,
    status          TEXT    NOT NULL DEFAULT 'ACTIVE' CHECK (status IN (
        'DRAFT','ACTIVE','INVALIDATED','ARCHIVED'
    )),
    base_case       TEXT,
    bull_case       TEXT,
    bear_case       TEXT,
    invalidate_conditions TEXT,
    key_metrics     TEXT,
    key_catalysts   TEXT,
    key_risks       TEXT,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL
);
CREATE INDEX idx_investment_theses_entity
    ON investment_theses(entity_uid);

-- ---------------------------------------------------------------------------
-- 6. event_thesis_analysis（B7）
-- ---------------------------------------------------------------------------
CREATE TABLE event_thesis_analysis (
    thesis_analysis_id  INTEGER PRIMARY KEY,
    -- CROSS-DB REFERENCE: event_uid → core.events.event_uid
    event_uid           TEXT    NOT NULL CHECK (length(event_uid) = 36),
    thesis_id           INTEGER NOT NULL REFERENCES investment_theses(thesis_id),
    impact_direction    TEXT    NOT NULL CHECK (impact_direction IN (
        'POSITIVE','NEGATIVE','NEUTRAL','MIXED'
    )),
    impact_severity     INTEGER NOT NULL CHECK (impact_severity BETWEEN 1 AND 5),
    reasoning_summary   TEXT,
    invalidate_triggered INTEGER NOT NULL DEFAULT 0 CHECK (invalidate_triggered IN (0,1)),
    recommended_attention TEXT,
    model_provider      TEXT    NOT NULL,
    model_id            TEXT    NOT NULL,
    prompt_version      TEXT    NOT NULL,
    analysis_version    TEXT    NOT NULL,
    raw_output          TEXT,
    created_at          TEXT    NOT NULL,
    UNIQUE (event_uid, thesis_id, analysis_version)
);
CREATE INDEX idx_event_thesis_analysis_thesis
    ON event_thesis_analysis(thesis_id);

-- ---------------------------------------------------------------------------
-- 7. alerts（B8；F8B generic_analysis_uid）
-- ---------------------------------------------------------------------------
CREATE TABLE alerts (
    alert_id           INTEGER PRIMARY KEY,
    alert_uid          TEXT    NOT NULL UNIQUE CHECK (length(alert_uid) = 36),
    alert_key          TEXT    NOT NULL UNIQUE,
    -- CROSS-DB REFERENCES（按 alert 类型选择，非全部必需）:
    --   event_uid           → core.events.event_uid
    --   instrument_uid      → core.instruments.instrument_uid
    --   generic_analysis_uid → core.event_analysis.analysis_uid (F8B)
    event_uid          TEXT CHECK (length(event_uid) = 36),
    instrument_uid     TEXT CHECK (length(instrument_uid) = 36),
    generic_analysis_uid TEXT CHECK (length(generic_analysis_uid) = 36),
    thesis_analysis_id INTEGER REFERENCES event_thesis_analysis(thesis_analysis_id),
    alert_type         TEXT    NOT NULL,
    channel            TEXT,
    rule_ref           TEXT,
    status             TEXT    NOT NULL DEFAULT 'PENDING' CHECK (status IN (
        'PENDING','SENT','FAILED','ACKED','DISMISSED'
    )),
    delivered_at       TEXT,
    created_at         TEXT    NOT NULL,
    updated_at         TEXT    NOT NULL
);
CREATE INDEX idx_alerts_status
    ON alerts(status);
CREATE INDEX idx_alerts_event
    ON alerts(event_uid);
