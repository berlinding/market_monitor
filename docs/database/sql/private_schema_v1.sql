-- =============================================================================
-- private_schema_v1.sql — private.db 完整 schema（REVIEW SNAPSHOT）
-- =============================================================================
-- Market Monitor private.db — PRIVATE 数据库（持仓/账户/自选/thesis/告警）
-- R1A v2 FROZEN (Berlin approved 2026-08-22) | R1B DDL specification
--
-- 说明：
--   * 本文件是 consolidated REVIEW SNAPSHOT，用于人工审查。
--   * 可执行权威来源 = docs/database/sql/migrations/private/P0001_initial_private_schema.sql
--     （DB-D029）
--   * 本文件不执行；执行由 R1C 经 migration runner 进行。
--   * 跨库引用（private.db → core.db）：entity_uid / instrument_uid / event_uid /
--     generic_analysis_uid 为 TEXT，**无伪 FK**，由应用层 validator 校验（见 SQL 注释
--     "CROSS-DB REFERENCE"）。
--   * 同库关系（如 positions→accounts、event_thesis_analysis→investment_theses、
--     alerts→event_thesis_analysis）使用原生 FK。
--
-- 全局约定（同 core）：INTEGER PK 仅单库内部；UID=TEXT(36) UUIDv4 由 application
-- 生成；Timestamp=TEXT UTC ISO-8601 由 application 写入（DB-D027）；Boolean=
-- INTEGER CHECK(0,1)；JSON=TEXT 应用层校验（DB-D028）；REAL 金额/价格。
-- =============================================================================

PRAGMA foreign_keys = ON;

-- =============================================================================
-- P-schema_migrations — private.db 独立迁移历史（DB-D030：P0001...）
-- =============================================================================
CREATE TABLE IF NOT EXISTS schema_migrations (
    migration_id TEXT PRIMARY KEY,                -- 如 'P0001'
    checksum     TEXT    NOT NULL CHECK (length(checksum) = 64),  -- SHA-256
    applied_at   TEXT    NOT NULL,                -- UTC ISO-8601（runner 写入）
    description  TEXT,
    execution_ms INTEGER
);

-- =============================================================================
-- 1. accounts — 账户（B5 提升 Core；F8A type 规范化）
-- =============================================================================
CREATE TABLE accounts (
    account_id   INTEGER PRIMARY KEY,
    account_uid  TEXT    NOT NULL UNIQUE CHECK (length(account_uid) = 36),
    account_name TEXT    NOT NULL UNIQUE,
    broker       TEXT,                            -- 券商名（IBKR/富途/...）
    account_type TEXT    NOT NULL CHECK (account_type IN (
        'CASH','MARGIN','RETIREMENT','PAPER','OTHER'
    )),
    base_currency TEXT   NOT NULL,                -- ISO 4217
    status       TEXT    NOT NULL DEFAULT 'ACTIVE' CHECK (status IN (
        'ACTIVE','CLOSED'
    )),
    created_at   TEXT    NOT NULL,
    updated_at   TEXT    NOT NULL
);
-- 注：不保存 password/token/credential（B5）。account_type 不含 broker 名（F8A/DB-D023）。

-- =============================================================================
-- 2. positions — 持仓快照（B6：account_id NOT NULL + instrument_uid NOT NULL）
-- =============================================================================
CREATE TABLE positions (
    position_id    INTEGER PRIMARY KEY,
    account_id     INTEGER NOT NULL REFERENCES accounts(account_id),
    -- CROSS-DB REFERENCE: instrument_uid → core.instruments.instrument_uid
    -- validated by application layer against core.db (ensure_instrument_uid)
    instrument_uid TEXT    NOT NULL CHECK (length(instrument_uid) = 36),
    quantity       REAL    NOT NULL,
    avg_cost       REAL,
    currency_code  TEXT    NOT NULL,              -- 成本币种 ISO 4217
    as_of_date     TEXT    NOT NULL,              -- 'YYYY-MM-DD'
    source         TEXT,                          -- MANUAL/BROKER_IMPORT/...
    status         TEXT    NOT NULL DEFAULT 'OPEN' CHECK (status IN (
        'OPEN','CLOSED'
    )),
    created_at     TEXT    NOT NULL,
    updated_at     TEXT    NOT NULL
);
-- OPEN 唯一：同一账户同一标的仅一条 OPEN 快照（B6 账户级重设计）
CREATE UNIQUE INDEX ux_positions_open
    ON positions(account_id, instrument_uid)
    WHERE status = 'OPEN';
CREATE INDEX idx_positions_instrument
    ON positions(instrument_uid);

-- =============================================================================
-- 3. watchlists — 自选列表
-- =============================================================================
CREATE TABLE watchlists (
    watchlist_id INTEGER PRIMARY KEY,
    name         TEXT    NOT NULL UNIQUE,
    created_at   TEXT    NOT NULL,
    updated_at   TEXT    NOT NULL
);

-- =============================================================================
-- 4. watchlist_items — 自选条目（B4 XOR）
-- =============================================================================
CREATE TABLE watchlist_items (
    item_id        INTEGER PRIMARY KEY,
    watchlist_id   INTEGER NOT NULL REFERENCES watchlists(watchlist_id),
    -- CROSS-DB REFERENCES (二选一，XOR):
    --   entity_uid    → core.entities.entity_uid      (关注公司)
    --   instrument_uid → core.instruments.instrument_uid (关注工具)
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
-- 分别防 entity duplicate / instrument duplicate（B4）
CREATE UNIQUE INDEX ux_watchlist_items_entity
    ON watchlist_items(watchlist_id, entity_uid)
    WHERE entity_uid IS NOT NULL;
CREATE UNIQUE INDEX ux_watchlist_items_instrument
    ON watchlist_items(watchlist_id, instrument_uid)
    WHERE instrument_uid IS NOT NULL;

-- =============================================================================
-- 5. investment_theses — 投资逻辑
-- =============================================================================
CREATE TABLE investment_theses (
    thesis_id       INTEGER PRIMARY KEY,
    -- CROSS-DB REFERENCE: entity_uid → core.entities.entity_uid
    entity_uid      TEXT    NOT NULL CHECK (length(entity_uid) = 36),
    title           TEXT    NOT NULL,
    status          TEXT    NOT NULL DEFAULT 'ACTIVE' CHECK (status IN (
        'DRAFT','ACTIVE','INVALIDATED','ARCHIVED'
    )),
    base_case       TEXT,                         -- Markdown
    bull_case       TEXT,                         -- Markdown
    bear_case       TEXT,                         -- Markdown
    invalidate_conditions TEXT,                   -- Markdown
    key_metrics     TEXT,                         -- JSON array（app 校验）
    key_catalysts   TEXT,                         -- JSON array
    key_risks       TEXT,                         -- JSON array
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL
);
CREATE INDEX idx_investment_theses_entity
    ON investment_theses(entity_uid);

-- =============================================================================
-- 6. event_thesis_analysis — 事件 ↔ 投资逻辑 私人分析（B7）
-- =============================================================================
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
    raw_output          TEXT,                     -- JSON（模型原始输出）
    created_at          TEXT    NOT NULL,
    UNIQUE (event_uid, thesis_id, analysis_version)
);
CREATE INDEX idx_event_thesis_analysis_thesis
    ON event_thesis_analysis(thesis_id);

-- =============================================================================
-- 7. alerts — 告警（B8 移入 private；F8B generic_analysis_uid）
-- =============================================================================
CREATE TABLE alerts (
    alert_id           INTEGER PRIMARY KEY,
    alert_uid          TEXT    NOT NULL UNIQUE CHECK (length(alert_uid) = 36),
    alert_key          TEXT    NOT NULL UNIQUE,   -- 业务去重键
    -- CROSS-DB REFERENCES（按 alert 类型选择，非全部必需）:
    --   event_uid          → core.events.event_uid
    --   instrument_uid     → core.instruments.instrument_uid
    --   generic_analysis_uid → core.event_analysis.analysis_uid (F8B)
    event_uid          TEXT CHECK (length(event_uid) = 36),
    instrument_uid     TEXT CHECK (length(instrument_uid) = 36),
    generic_analysis_uid TEXT CHECK (length(generic_analysis_uid) = 36),
    thesis_analysis_id INTEGER REFERENCES event_thesis_analysis(thesis_analysis_id),
    alert_type         TEXT    NOT NULL,          -- R6 定义（THESIS_IMPACT/EVENT/PRICE/...）
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
