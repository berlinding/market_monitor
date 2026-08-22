#!/usr/bin/env python3
"""
legacy_migration_utils.py — synthetic legacy migration helpers (R1C Phase 1.1)

Implements M0–M7 of legacy_daily_bars_migration_spec_v1.md at FIXTURE level,
operating ONLY on temp/synthetic databases (never on data/market.db).

Key invariants implemented here (P0-1/P0-2/P0-3 + H1, DB-D035/DB-D037/DB-D038):
  * live DB is used ONLY for health/readability preflight and to produce the
    frozen snapshot (H1) — it is NOT the authoritative migration baseline;
  * authoritative baseline manifest is generated FROM the frozen snapshot
    (capture_snapshot_baseline) and drives M3–M7;
  * validate_snapshot NEVER reopens the live DB (no post-backup live reads);
  * dynamic migration-time baseline (not a fixed row count);
  * 100% mapping gate; duplicate stock_basic ts_code / missing fields are
    fatal (H2); unknown ts_code suffix -> abort;
  * legacy naive timestamps converted with an explicit IANA zone, never guessed.
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from scripts.date_utils import DateNormalizationError, normalize_date
from scripts.timestamp_utils import convert_legacy_naive_to_utc

# deterministic suffix -> MIC mapping (S4 / DB-D037); extend with new exchanges only via decision.
SUFFIX_MIC = {"SH": "XSHG", "SZ": "XSHE", "BJ": "XBSE"}

REQUIRED_DAILY_BARS_COLUMNS = {
    "ts_code", "trade_date", "open", "high", "low", "close",
    "pre_close", "change", "pct_chg", "vol", "amount",
}
REQUIRED_FETCH_LOG_COLUMNS = {"trade_date", "fetched_at", "rows", "note"}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class MappingGateError(ValueError):
    """100% instrument mapping gate failed."""


# ---------------------------------------------------------------------------
# Fixture builders (deterministic, offline)
# ---------------------------------------------------------------------------
def create_legacy_fixture(
    db_path: Path,
    bars: list[tuple[str, str, float, float, float, float, float, float]],
    fetch_log: list[tuple[str, str, int]],
) -> None:
    """Create a synthetic legacy market.db (daily_bars + fetch_log)."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE daily_bars (
            ts_code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            open REAL, high REAL, low REAL, close REAL,
            pre_close REAL, change REAL, pct_chg REAL,
            vol REAL, amount REAL,
            PRIMARY KEY (ts_code, trade_date)
        );
        CREATE TABLE fetch_log (
            trade_date TEXT PRIMARY KEY,
            fetched_at TEXT,
            rows INTEGER,
            note TEXT
        );
        """
    )
    conn.executemany(
        "INSERT INTO daily_bars VALUES (?,?,?,?,?,?,?,?,?,?,?)", bars
    )
    conn.executemany(
        "INSERT INTO fetch_log(trade_date, fetched_at, rows, note) VALUES (?,?,?,?)",
        [(td, fa, r, "") for td, fa, r in fetch_log],
    )
    conn.commit()
    conn.close()


def build_stock_basic_fixture(ts_codes: list[str]) -> list[dict]:
    """Synthetic stock_basic rows (ts_code, name, list_date).

    list_date uses the provider-raw compact format (YYYYMMDD) to exercise
    canonical normalization, matching real Tushare stock_basic output (D2).
    """
    out = []
    for i, ts in enumerate(ts_codes, start=1):
        out.append(
            {
                "ts_code": ts,
                "name": f"Fixture Co {i}",
                "list_date": "20100101",
            }
        )
    return out


# ---------------------------------------------------------------------------
# M0 — live health preflight (H1: NOT authoritative baseline)
# ---------------------------------------------------------------------------
def inspect_live_source_health(live_path: Path) -> dict:
    """Live preflight: file exists, readable, required tables/columns, integrity.

    This is a HEALTH CHECK ONLY. The observed values (including
    live_source_file_hash_observed) are informational audit data and must NOT
    be used as the authoritative migration baseline (H1). The authoritative
    baseline comes from the frozen snapshot (capture_snapshot_baseline).
    """
    result = {
        "observed_at": _utc_now_iso(),
        "live_path": str(live_path),
        "file_exists": live_path.exists(),
        "sqlite_readable": False,
        "tables_ok": False,
        "columns_ok": False,
        "integrity_check_ok": False,
        "ok": False,
    }
    if not live_path.exists():
        return result
    try:
        conn = sqlite3.connect(f"file:{live_path.resolve()}?mode=ro", uri=True)
        try:
            result["sqlite_readable"] = True
            tables = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            result["tables_ok"] = {"daily_bars", "fetch_log"} <= tables
            if result["tables_ok"]:
                db_cols = {
                    c[1]
                    for c in conn.execute("PRAGMA table_info('daily_bars')")
                }
                fl_cols = {
                    c[1]
                    for c in conn.execute("PRAGMA table_info('fetch_log')")
                }
                result["columns_ok"] = (
                    REQUIRED_DAILY_BARS_COLUMNS <= db_cols
                    and REQUIRED_FETCH_LOG_COLUMNS <= fl_cols
                )
            result["integrity_check_ok"] = (
                conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
            )
            result["ok"] = (
                result["tables_ok"]
                and result["columns_ok"]
                and result["integrity_check_ok"]
            )
            # informational only — never used for migration reconciliation
            result["live_source_file_hash_observed"] = hashlib.sha256(
                live_path.read_bytes()
            ).hexdigest()
        finally:
            conn.close()
    except sqlite3.Error:
        pass
    return result


# ---------------------------------------------------------------------------
# M1B — authoritative migration baseline manifest FROM frozen snapshot (H1)
# ---------------------------------------------------------------------------
def capture_snapshot_baseline(snapshot_path: Path) -> dict:
    """Generate the authoritative migration baseline manifest from the snapshot.

    This manifest is the SINGLE source of truth for M3–M7 reconciliation.
    It is derived only from the frozen snapshot file — never from the live DB.
    """
    conn = sqlite3.connect(f"file:{snapshot_path.resolve()}?mode=ro", uri=True)
    try:
        row_count = conn.execute("SELECT COUNT(*) FROM daily_bars").fetchone()[0]
        dist_dates = conn.execute(
            "SELECT COUNT(DISTINCT trade_date) FROM daily_bars"
        ).fetchone()[0]
        date_dist = dict(
            conn.execute(
                "SELECT trade_date, COUNT(*) FROM daily_bars GROUP BY trade_date"
            ).fetchall()
        )
        dist_ts = conn.execute(
            "SELECT COUNT(DISTINCT ts_code) FROM daily_bars"
        ).fetchone()[0]
        fetch_count = conn.execute("SELECT COUNT(*) FROM fetch_log").fetchone()[0]
        latest = conn.execute(
            "SELECT MAX(fetched_at) FROM fetch_log"
        ).fetchone()[0]
        suffixes = sorted(
            {
                r[0].split(".")[-1]
                for r in conn.execute("SELECT DISTINCT ts_code FROM daily_bars")
                if "." in r[0]
            }
        )
        aggregates = {
            r[0]: {"sum_volume": r[1], "sum_turnover": r[2]}
            for r in conn.execute(
                "SELECT trade_date, SUM(vol), SUM(amount) FROM daily_bars "
                "GROUP BY trade_date"
            )
        }
    finally:
        conn.close()
    data = snapshot_path.read_bytes()
    return {
        "captured_at": _utc_now_iso(),
        "snapshot_path": str(snapshot_path),
        "snapshot_sha256": hashlib.sha256(data).hexdigest(),
        "file_size": len(data),
        "row_count": row_count,
        "distinct_trade_dates": dist_dates,
        "trade_date_distribution": date_dist,
        "distinct_ts_code": dist_ts,
        "fetch_log_count": fetch_count,
        "latest_fetch_time_raw": latest,
        "ts_code_suffixes": suffixes,
        "aggregates": aggregates,
    }


# ---------------------------------------------------------------------------
# M1 — frozen snapshot (Type B logical backup) + snapshot-internal validation
# ---------------------------------------------------------------------------
def create_frozen_snapshot(src_path: Path, dst_path: Path) -> str:
    """sqlite3.Connection.backup() -> frozen snapshot file; returns its SHA-256."""
    src = sqlite3.connect(f"file:{src_path.resolve()}?mode=ro", uri=True)
    dst = sqlite3.connect(str(dst_path))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return hashlib.sha256(dst_path.read_bytes()).hexdigest()


def validate_snapshot(snapshot_path: Path, manifest: dict) -> dict[str, bool]:
    """Snapshot-internal validation (H1): NEVER reopens the live DB.

    Checks: integrity, required schema/columns, manifest self-consistency,
    snapshot_sha256 == sha256(snapshot bytes). The live DB is not consulted.
    """
    conn = sqlite3.connect(f"file:{snapshot_path.resolve()}?mode=ro", uri=True)
    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        schema_ok = {"daily_bars", "fetch_log"} <= tables
        db_cols = {
            c[1]
            for c in conn.execute("PRAGMA table_info('daily_bars')")
        }
        fl_cols = {
            c[1]
            for c in conn.execute("PRAGMA table_info('fetch_log')")
        }
        columns_ok = (
            REQUIRED_DAILY_BARS_COLUMNS <= db_cols
            and REQUIRED_FETCH_LOG_COLUMNS <= fl_cols
        )
        row_count = conn.execute("SELECT COUNT(*) FROM daily_bars").fetchone()[0]
        date_dist = dict(
            conn.execute(
                "SELECT trade_date, COUNT(*) FROM daily_bars GROUP BY trade_date"
            ).fetchall()
        )
        dist_ts = conn.execute(
            "SELECT COUNT(DISTINCT ts_code) FROM daily_bars"
        ).fetchone()[0]
        fetch_count = conn.execute("SELECT COUNT(*) FROM fetch_log").fetchone()[0]
        agg = {
            r[0]: {"sum_volume": r[1], "sum_turnover": r[2]}
            for r in conn.execute(
                "SELECT trade_date, SUM(vol), SUM(amount) FROM daily_bars "
                "GROUP BY trade_date"
            )
        }
    finally:
        conn.close()

    return {
        "integrity_check": integrity,
        "schema_equality": schema_ok,
        "columns_ok": columns_ok,
        "row_count_equality": row_count == manifest["row_count"],
        "fetch_log_count_equality": fetch_count == manifest["fetch_log_count"],
        "trade_date_distribution_equality": date_dist
        == manifest["trade_date_distribution"],
        "distinct_ts_code_equality": dist_ts == manifest["distinct_ts_code"],
        "aggregate_self_consistency": agg == manifest["aggregates"],
        "snapshot_hash_matches": hashlib.sha256(
            snapshot_path.read_bytes()
        ).hexdigest()
        == manifest["snapshot_sha256"],
    }


# ---------------------------------------------------------------------------
# M3/M4 — instrument mapping (strict gate, DB-D037 + H2)
# ---------------------------------------------------------------------------
def validate_stock_basic_input(stock_basic: list[dict]) -> None:
    """H2 + D2: stock_basic input validation — duplicates, missing fields and
    invalid list_date are fatal.

    Raises MappingGateError (never last-one-wins / drop_duplicates / silent fill).
    """
    seen: set[str] = set()
    for row in stock_basic:
        if not isinstance(row, dict):
            raise MappingGateError(
                f"stock_basic row is not a dict: {row!r}"
            )
        ts = row.get("ts_code")
        if not ts or not isinstance(ts, str) or not ts.strip():
            raise MappingGateError(
                f"stock_basic row missing/empty ts_code: {row!r}"
            )
        name = row.get("name")
        if not name or not isinstance(name, str) or not name.strip():
            raise MappingGateError(
                f"stock_basic row missing/empty name for ts_code {ts!r}: {row!r}"
            )
        list_date = row.get("list_date")
        if not list_date or not isinstance(list_date, str) or not list_date.strip():
            raise MappingGateError(
                f"stock_basic row missing/empty list_date for ts_code {ts!r}: {row!r}"
            )
        try:
            normalize_date(list_date)
        except DateNormalizationError as exc:
            raise MappingGateError(
                f"invalid list_date for ts_code {ts!r}: {list_date!r} "
                f"(must be a real calendar date YYYYMMDD or YYYY-MM-DD)"
            ) from exc
        if ts in seen:
            raise MappingGateError(
                f"duplicate stock_basic ts_code: {ts!r} appears more than once; "
                "refusing to guess which identity wins (strict mapping gate)"
            )
        seen.add(ts)


def build_ts_code_mapping(
    snapshot_path: Path, stock_basic: list[dict]
) -> dict[str, dict]:
    """Map every distinct legacy ts_code to a deterministic instrument identity.

    Returns {ts_code: {"symbol", "mic", "entity_name", "list_date" (canonical
    YYYY-MM-DD), "provider_list_date_raw"}}.
    Raises MappingGateError on:
      * malformed stock_basic row (missing ts_code/name/list_date)  [H2]
      * invalid list_date calendar value                            [D2]
      * duplicate stock_basic ts_code                              [H2]
      * missing legacy ts_code in stock_basic                      [strict gate]
      * unknown suffix                                             [strict gate]
    """
    validate_stock_basic_input(stock_basic)

    conn = sqlite3.connect(f"file:{snapshot_path.resolve()}?mode=ro", uri=True)
    try:
        legacy_ts = {
            r[0]
            for r in conn.execute("SELECT DISTINCT ts_code FROM daily_bars")
        }
    finally:
        conn.close()

    basic = {row["ts_code"]: row for row in stock_basic}
    missing = legacy_ts - set(basic)
    if missing:
        raise MappingGateError(
            f"100% mapping gate failed: stock_basic missing {len(missing)} ts_code(s): "
            f"{sorted(missing)[:5]}"
        )

    mapping: dict[str, dict] = {}
    for ts in sorted(legacy_ts):
        suffix = ts.split(".")[-1]
        if suffix not in SUFFIX_MIC:
            raise MappingGateError(f"unknown ts_code suffix {suffix!r} for {ts}")
        if ts in mapping:
            raise MappingGateError(f"duplicate mapping for {ts}")
        symbol = ts.split(".")[0]
        raw_list_date = basic[ts]["list_date"]
        mapping[ts] = {
            "symbol": symbol,
            "mic": SUFFIX_MIC[suffix],
            "entity_name": basic[ts]["name"],
            "list_date": normalize_date(raw_list_date),
            "provider_list_date_raw": raw_list_date,
        }
    return mapping


# ---------------------------------------------------------------------------
# M5 — ingest run backfill with explicit timezone (DB-D035)
# ---------------------------------------------------------------------------
def backfill_runs(
    snapshot_path: Path, timezone_name: str | None
) -> dict[str, dict]:
    """Read fetch_log from the frozen snapshot; map trade_date -> run info.

    timezone_name None -> TimestampResolutionError (never guess UTC).
    """
    conn = sqlite3.connect(f"file:{snapshot_path.resolve()}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT trade_date, fetched_at, rows FROM fetch_log ORDER BY trade_date"
        ).fetchall()
    finally:
        conn.close()

    runs: dict[str, dict] = {}
    for trade_date, fetched_raw, n_rows in rows:
        started_utc = convert_legacy_naive_to_utc(fetched_raw, timezone_name)
        runs[trade_date] = {
            "trade_date": trade_date,
            "started_at_utc": started_utc,
            "legacy_fetched_at_raw": fetched_raw,
            "rows": n_rows,
        }
    return runs


# ---------------------------------------------------------------------------
# M6 — copy bars from frozen snapshot only (P0-3)
# ---------------------------------------------------------------------------
def migrate_bars_from_snapshot(
    snapshot_path: Path,
    mapping: dict[str, dict],
    conn: sqlite3.Connection,
    *,
    source_id: int,
    run_by_date: dict[str, int],
    raw_artifact_id: int,
    adjustment_type: str = "RAW",
    currency_code: str = "CNY",
) -> int:
    """Copy daily_bars from frozen snapshot into canonical market_prices_daily.

    D1: legacy trade_date is compact YYYYMMDD; canonical trade_date is written
    as YYYY-MM-DD via normalize_date(). run_by_date lookup keeps using the raw
    legacy key (fetch_log.trade_date == legacy daily_bars.trade_date == YYYYMMDD).
    """
    snap = sqlite3.connect(f"file:{snapshot_path.resolve()}?mode=ro", uri=True)
    count = 0
    try:
        for ts, m in mapping.items():
            rows = snap.execute(
                "SELECT trade_date, open, high, low, close, vol, amount "
                "FROM daily_bars WHERE ts_code = ?",
                (ts,),
            ).fetchall()
            for raw_trade_date, o, h, l, c, vol, amt in rows:
                run_id = run_by_date[raw_trade_date]
                canonical_trade_date = normalize_date(raw_trade_date)
                instrument_id = m["instrument_id"]
                conn.execute(
                    "INSERT INTO market_prices_daily"
                    "(instrument_id, trade_date, open, high, low, close,"
                    " volume, volume_unit, turnover, turnover_unit, currency_code,"
                    " adjustment_type, source_id, ingest_run_id, raw_artifact_id,"
                    " ingested_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        instrument_id,
                        canonical_trade_date,
                        o,
                        h,
                        l,
                        c,
                        vol,
                        "LOTS",
                        amt,
                        "THOUSAND_CNY",
                        currency_code,
                        adjustment_type,
                        source_id,
                        run_id,
                        raw_artifact_id,
                        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    ),
                )
                count += 1
    finally:
        snap.close()
    return count


# ---------------------------------------------------------------------------
# M7 — validation (fixture-level V1/V2/V3/V4/V12 subset + full flags)
# ---------------------------------------------------------------------------
def validate_migration(
    conn: sqlite3.Connection,
    snapshot_path: Path,
    manifest: dict,
    mapping: dict[str, dict],
) -> dict[str, bool]:
    snap = sqlite3.connect(f"file:{snapshot_path.resolve()}?mode=ro", uri=True)
    try:
        legacy_rows = snap.execute("SELECT COUNT(*) FROM daily_bars").fetchone()[0]
        legacy_dates = set(
            r[0]
            for r in snap.execute("SELECT DISTINCT trade_date FROM daily_bars")
        )
        legacy_ts = {
            r[0]
            for r in snap.execute("SELECT DISTINCT ts_code FROM daily_bars")
        }
        legacy_agg = {
            (r[0], r[1], r[2])
            for r in snap.execute(
                "SELECT trade_date, SUM(vol), SUM(amount) FROM daily_bars "
                "GROUP BY trade_date"
            )
        }
    finally:
        snap.close()

    canon_rows = conn.execute(
        "SELECT COUNT(*) FROM market_prices_daily"
    ).fetchone()[0]
    canon_dates = set(
        r[0]
        for r in conn.execute("SELECT DISTINCT trade_date FROM market_prices_daily")
    )
    canon_ts = {
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT identifier FROM instrument_identifiers "
            "WHERE identifier_type='EXCHANGE_SYMBOL' AND provider='TUSHARE'"
        )
    }
    canon_agg = {
        (r[0], r[1], r[2])
        for r in conn.execute(
            "SELECT trade_date, SUM(volume), SUM(turnover) FROM market_prices_daily "
            "GROUP BY trade_date"
        )
    }
    dup_keys = conn.execute(
        "SELECT COUNT(*) - COUNT(DISTINCT instrument_id || '|' || trade_date || '|' "
        "|| adjustment_type || '|' || source_id) FROM market_prices_daily"
    ).fetchone()[0]

    # D4: canonical dates are normalized YYYY-MM-DD; compare against the
    # normalized expectation derived from legacy raw dates (not raw == raw).
    expected_canonical_dates = {normalize_date(d) for d in legacy_dates}
    expected_legacy_agg = {
        (normalize_date(r[0]), r[1], r[2]) for r in legacy_agg
    }

    return {
        "V1_row_count": canon_rows == legacy_rows == manifest["row_count"],
        "V2_trade_dates": canon_dates == expected_canonical_dates,
        "V3_mapping_complete": len(mapping) == manifest["distinct_ts_code"]
        and canon_ts == legacy_ts,
        "V4_no_duplicate_keys": dup_keys == 0,
        "V12_aggregate_reconciliation": canon_agg == expected_legacy_agg,
    }
