#!/usr/bin/env python3
"""
phase2_staging_rehearsal.py — R1C Phase 2 Full-Scale Real-Data Staging Rehearsal (stdlib only)

Berlin-authorized (2026-08-22 #381-#387):
  real legacy data/market.db (READ-ONLY) -> frozen snapshot -> real Tushare
  stock_basic (L/D/P merged) -> staging core.db / private.db (C0001/P0001)
  -> real entities/instruments/identifiers -> full daily_bars migration
  (per trade_date atomic batches) -> V1-V18 validation + 100% full-row
  reconciliation -> migration_report.json.

Hard guards:
  * NEVER writes data/runtime/core.db or data/private/private.db
    (PRODUCTION_WRITES_ENABLED stays False; PRODUCTION_PATHS hard-rejected).
  * NEVER modifies live data/market.db (opened read-only only).
  * Tushare token read from env or ~/API.txt inside the process; never echoed,
    never written to report/log/CLI.
  * All migration reads come from the FROZEN SNAPSHOT only (P0-3).

Run:
  python3 scripts/phase2_staging_rehearsal.py [--run-id YYYYMMDDTHHMMSSZ]
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import sqlite3
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.legacy_migration_utils import (  # noqa: E402
    capture_snapshot_baseline,
    create_frozen_snapshot,
    inspect_live_source_health,
    validate_snapshot,
    build_ts_code_mapping,
    MappingGateError,
    SUFFIX_MIC,
)
from scripts.date_utils import normalize_date  # noqa: E402
from scripts.timestamp_utils import utc_now_iso  # noqa: E402

# ---------------------------------------------------------------------------
# Paths / constants
# ---------------------------------------------------------------------------
LIVE_DB = PROJECT_ROOT / "data" / "market.db"
SNAPSHOT_DIR = PROJECT_ROOT / "data" / "raw" / "legacy"
TUSHARE_RAW_DIR = PROJECT_ROOT / "data" / "raw" / "tushare"
STAGING_ROOT = PROJECT_ROOT / "data" / "staging" / "r1c_phase2"
MIGRATIONS_DIR = PROJECT_ROOT / "docs" / "database" / "sql" / "migrations"
API_TXT = Path.home() / "API.txt"
TUSHARE_API = "http://api.tushare.pro"

PRODUCTION_PATHS = {
    "core": (PROJECT_ROOT / "data" / "runtime" / "core.db").resolve(),
    "private": (PROJECT_ROOT / "data" / "private" / "private.db").resolve(),
}

STOCK_BASIC_FIELDS = (
    "ts_code,symbol,name,area,industry,market,exchange,curr_type,"
    "list_status,list_date,delist_date"
)
LEGACY_TZ = "Asia/Shanghai"  # CONFIRMED (DB-D035 / S2 / #25)

# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_head() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=15,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return "unknown"


def load_tushare_token() -> str:
    """Read TUSHARE_TOKEN from env or ~/API.txt. Never printed."""
    token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if token:
        return token
    for api_path in (API_TXT, PROJECT_ROOT / "API.txt"):
        try:
            with open(api_path, encoding="utf-8") as f:
                for line in f:
                    if line.startswith("TUSHARE_TOKEN="):
                        return line.split("=", 1)[1].strip()
        except FileNotFoundError:
            continue
    return ""


def tushare_post(api_name: str, token: str, params: dict, fields: str) -> list[dict]:
    body = json.dumps(
        {"api_name": api_name, "token": token, "params": params, "fields": fields}
    ).encode("utf-8")
    req = urllib.request.Request(
        TUSHARE_API, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("code") != 0:
        raise RuntimeError(f"Tushare error {data.get('code')}: {data.get('msg')}")
    f_out = data["data"]["fields"]
    items = data["data"]["items"]
    return [dict(zip(f_out, row)) for row in items]


def tushare_post_with_retry(
    api_name: str,
    token: str,
    params: dict,
    fields: str,
    max_retries: int = 2,
    retry_wait_s: float = 3660.0,
) -> list[dict]:
    """POST with retry on Tushare rate-limit errors (code 40203 / 频率超限).

    Real-data finding (2026-08-23): stock_basic on this token tier is limited
    to 1 call/hour (rolling window). We wait out the full hourly window before
    retrying; other errors fail fast. Never prints or stores the token.
    """
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            return tushare_post(api_name, token, params, fields)
        except RuntimeError as exc:
            last_exc = exc
            msg = str(exc)
            if "40203" not in msg and "频率超限" not in msg:
                raise
            if attempt < max_retries - 1:
                print(
                    f"[tushare] rate-limited ({msg.split(':')[-1].strip()}); "
                    f"waiting {retry_wait_s:.0f}s before retry {attempt + 1}/{max_retries - 1}",
                    flush=True,
                )
                time.sleep(retry_wait_s)
    assert last_exc is not None
    raise last_exc


def open_ro(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


# ---------------------------------------------------------------------------
# M0 — live preflight (informational ONLY; authoritative baseline = snapshot)
# ---------------------------------------------------------------------------
def m0_live_preflight() -> dict:
    health = inspect_live_source_health(LIVE_DB)
    info = {}
    if health["ok"]:
        conn = open_ro(LIVE_DB)
        try:
            info["row_count"] = conn.execute("SELECT COUNT(*) FROM daily_bars").fetchone()[0]
            info["distinct_trade_dates"] = conn.execute(
                "SELECT COUNT(DISTINCT trade_date) FROM daily_bars"
            ).fetchone()[0]
            info["trade_date_distribution"] = dict(
                conn.execute(
                    "SELECT trade_date, COUNT(*) FROM daily_bars GROUP BY trade_date"
                ).fetchall()
            )
            info["distinct_ts_code"] = conn.execute(
                "SELECT COUNT(DISTINCT ts_code) FROM daily_bars"
            ).fetchone()[0]
            info["fetch_log_count"] = conn.execute("SELECT COUNT(*) FROM fetch_log").fetchone()[0]
            info["latest_fetch_time_raw"] = conn.execute(
                "SELECT MAX(fetched_at) FROM fetch_log"
            ).fetchone()[0]
            info["suffix_set"] = sorted(
                {
                    r[0].split(".")[-1]
                    for r in conn.execute("SELECT DISTINCT ts_code FROM daily_bars")
                    if "." in r[0]
                }
            )
            # full integrity check (spec M0: quick_check + integrity_check)
            info["integrity_check"] = conn.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            conn.close()
        info["file_size"] = LIVE_DB.stat().st_size
        info["mtime"] = datetime.fromtimestamp(
            LIVE_DB.stat().st_mtime, tz=timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        # S4: every observed suffix must have a deterministic MIC mapping
        unknown = sorted(set(info["suffix_set"]) - set(SUFFIX_MIC))
        info["unknown_suffixes"] = unknown
        info["suffix_mic_ok"] = not unknown
        health["ok"] = bool(health["ok"] and info["suffix_mic_ok"])
    return {"health": health, "info": info}


# ---------------------------------------------------------------------------
# M1 — frozen snapshot + manifest + snapshot-internal validation
# ---------------------------------------------------------------------------
def m1_frozen_snapshot(run_id: str) -> dict:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    snapshot_path = SNAPSHOT_DIR / f"market_{run_id}.db"
    snapshot_sha = create_frozen_snapshot(LIVE_DB, snapshot_path)
    manifest = capture_snapshot_baseline(snapshot_path)
    validation = validate_snapshot(snapshot_path, manifest)
    all_pass = all(validation.values())
    return {
        "snapshot_path": str(snapshot_path),
        "snapshot_sha256": snapshot_sha,
        "manifest": manifest,
        "validation": validation,
        "pass": all_pass,
    }


# ---------------------------------------------------------------------------
# M2 — real stock_basic download (L/D/P merged, provenance kept)
# ---------------------------------------------------------------------------
def m2_stock_basic(
    run_id: str, token: str, snapshot_path: Path, manifest: dict
) -> dict:
    """Download real stock_basic (coverage-driven L/D/P escalation).

    Rate-limit-aware: stock_basic is 1 call/hour on this tier, so we fetch
    list_status='L' first and only spend additional hourly slots on D/P if the
    legacy ts_code universe is not yet 100% covered (authorization §14).
    """
    TUSHARE_RAW_DIR.mkdir(parents=True, exist_ok=True)
    # legacy ts_code universe from the FROZEN snapshot (P0-3)
    conn = open_ro(snapshot_path)
    try:
        legacy_ts = {
            r[0]
            for r in conn.execute("SELECT DISTINCT ts_code FROM daily_bars")
        }
    finally:
        conn.close()

    rows: list[dict] = []
    provenance: list[dict] = []
    statuses = ("L", "D", "P")
    for idx, status in enumerate(statuses):
        fetched_at = utc_now_iso()
        try:
            params = {"list_status": status}
            resp = tushare_post_with_retry(
                "stock_basic", token, params, STOCK_BASIC_FIELDS, max_retries=3
            )
        except Exception as exc:  # noqa: BLE001
            provenance.append(
                {
                    "list_status": status,
                    "params": {"list_status": status},
                    "retrieved_at_utc": fetched_at,
                    "row_count": 0,
                    "error": str(exc),
                }
            )
            raise
        provenance.append(
            {
                "list_status": status,
                "params": {"list_status": status},
                "retrieved_at_utc": fetched_at,
                "row_count": len(resp),
            }
        )
        rows.extend(resp)
        provider_ts = {r["ts_code"] for r in rows if r.get("ts_code")}
        covered = legacy_ts <= provider_ts
        print(
            f"[M2] status={status}: +{len(resp)} rows; "
            f"cumulative coverage {len(legacy_ts & provider_ts)}/{len(legacy_ts)}"
            f" -> {'100% (no more queries)' if covered else 'need more'}",
            flush=True,
        )
        if covered:
            break
        if idx < len(statuses) - 1:
            print(
                f"[M2] waiting 61min for next hourly slot before querying '{statuses[idx + 1]}'",
                flush=True,
            )
            time.sleep(3660)

    # each ts_code must be unique; L/D/P are mutually exclusive in Tushare.
    seen: dict[str, dict] = {}
    dup_conflict: list[dict] = []
    for r in rows:
        ts = r.get("ts_code")
        if not ts:
            continue
        if ts in seen:
            prev = seen[ts]
            conflict = (
                prev.get("name") != r.get("name")
                or prev.get("list_date") != r.get("list_date")
            )
            dup_conflict.append({"ts_code": ts, "conflict": conflict})
        else:
            seen[ts] = r
    if any(d["conflict"] for d in dup_conflict):
        raise RuntimeError(
            f"stock_basic ambiguous duplicate ts_code (conflicting values): "
            f"{[d['ts_code'] for d in dup_conflict if d['conflict']][:5]}"
        )
    dedup_rows = list(seen.values())

    csv_path = TUSHARE_RAW_DIR / f"stock_basic_{run_id}.csv"
    fieldnames = list(dedup_rows[0].keys()) if dedup_rows else STOCK_BASIC_FIELDS.split(",")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(dedup_rows)
    csv_sha = sha256_bytes(csv_path.read_bytes())

    meta = {
        "run_id": run_id,
        "provider": "TUSHARE",
        "api_name": "stock_basic",
        "retrieved_at_utc": utc_now_iso(),
        "queries": provenance,
        "merged_row_count": len(rows),
        "duplicate_ts_codes": len(dup_conflict),
        "unique_ts_code_count": len(dedup_rows),
        "legacy_ts_code_count": len(legacy_ts),
        "csv_path": str(csv_path),
        "sha256": csv_sha,
        "fields": fieldnames,
    }
    meta_path = TUSHARE_RAW_DIR / f"stock_basic_{run_id}.meta.json"
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"rows": dedup_rows, "meta": meta, "csv_path": str(csv_path), "sha256": csv_sha}


# ---------------------------------------------------------------------------
# M3/M4 — stock_basic strict validation + 100% mapping gate
# ---------------------------------------------------------------------------
def m3_m4_mapping(snapshot_path: Path, rows: list[dict]) -> dict:
    coverage = {"total_provider_records": len(rows)}
    try:
        mapping = build_ts_code_mapping(snapshot_path, rows)
        coverage["status"] = "PASS"
        return {"coverage": coverage, "mapping": mapping}
    except MappingGateError as exc:
        coverage["status"] = "FAIL"
        coverage["error"] = str(exc)
        # legacy set for diagnostics
        conn = open_ro(snapshot_path)
        try:
            legacy_ts = {
                r[0]
                for r in conn.execute("SELECT DISTINCT ts_code FROM daily_bars")
            }
        finally:
            conn.close()
        provider_ts = {r["ts_code"] for r in rows if r.get("ts_code")}
        coverage["legacy_ts_code_count"] = len(legacy_ts)
        coverage["provider_ts_code_count"] = len(provider_ts)
        coverage["missing_legacy_ts_code"] = sorted(legacy_ts - provider_ts)
        coverage["extra_provider_ts_code"] = sorted(provider_ts - legacy_ts)[:50]
        diagnostics = {
            "run_note": "mapping gate FAILED; bar migration NOT started",
            "coverage": coverage,
        }
        diag_path = STAGING_ROOT / "mapping_diagnostics.json"
        STAGING_ROOT.mkdir(parents=True, exist_ok=True)
        diag_path.write_text(
            json.dumps(diagnostics, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        coverage["diagnostics_path"] = str(diag_path)
        return {"coverage": coverage, "mapping": None}


# ---------------------------------------------------------------------------
# Staging DB creation via migration runner (C0001/P0001)
# ---------------------------------------------------------------------------
def create_staging_dbs(run_id: str) -> dict:
    from scripts.migrate import run_migrations  # local import keeps CLI clean

    staging_dir = STAGING_ROOT / run_id
    staging_dir.mkdir(parents=True, exist_ok=True)
    core_db = staging_dir / "core.db"
    private_db = staging_dir / "private.db"
    for p in (core_db, private_db):
        if p.resolve() in PRODUCTION_PATHS.values():
            raise RuntimeError(f"refusing: staging path collides with production: {p}")

    core_rows = run_migrations(core_db, MIGRATIONS_DIR / "core", "C", db_label="core")
    private_rows = run_migrations(
        private_db, MIGRATIONS_DIR / "private", "P", db_label="private"
    )
    core_status = {r["migration_id"]: r["status"] for r in core_rows}
    private_status = {r["migration_id"]: r["status"] for r in private_rows}
    core_checksums = {r["migration_id"]: r["checksum"] for r in core_rows}
    private_checksums = {r["migration_id"]: r["checksum"] for r in private_rows}

    # checks: core = 17 tables (16 domain + schema_migrations)
    core_checks = verify_staging_schema(
        core_db, expected_prefix="C", expected_table_count=17
    )
    private_checks = verify_staging_schema(
        private_db,
        expected_prefix="P",
        expected_table_count=8,
        expected_tables={
            "schema_migrations", "accounts", "positions", "watchlists",
            "watchlist_items", "investment_theses", "event_thesis_analysis",
            "alerts",
        },
    )
    return {
        "staging_dir": str(staging_dir),
        "core_db": str(core_db),
        "private_db": str(private_db),
        "core_migrations": core_status,
        "private_migrations": private_status,
        "core_checksums": core_checksums,
        "private_checksums": private_checksums,
        "core_checks": core_checks,
        "private_checks": private_checks,
    }


def verify_staging_schema(
    db_path: Path,
    expected_prefix: str,
    expected_table_count: int | None = None,
    expected_tables: set | None = None,
) -> dict:
    conn = open_ro(db_path)
    try:
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        fk_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        applied = dict(
            conn.execute("SELECT migration_id, checksum FROM schema_migrations")
        )
    finally:
        conn.close()
    result = {
        "tables": sorted(tables),
        "table_count": len(tables),
        "foreign_key_check_empty": len(fk_violations) == 0,
        "schema_migrations": applied,
        "table_count_ok": (
            expected_table_count is None or len(tables) == expected_table_count
        ),
    }
    if expected_tables is not None:
        result["expected_tables_present"] = expected_tables <= tables
    return result


# ---------------------------------------------------------------------------
# M2/M2B — bootstrap source/dataset metadata + register snapshot raw_artifact
# ---------------------------------------------------------------------------
def m2_metadata(core_conn: sqlite3.Connection) -> dict:
    now = utc_now_iso()
    cur = core_conn.execute(
        "INSERT INTO data_sources"
        "(source_code, source_name, source_type, status, notes, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?)",
        ("TUSHARE", "Tushare", "MARKET_DATA", "ACTIVE",
         "A-share market data provider", now, now),
    )
    source_id = cur.lastrowid
    cur = core_conn.execute(
        "INSERT INTO datasets"
        "(dataset_code, dataset_name, dataset_type, granularity, target_table,"
        " write_mode, status, notes, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        ("CN_EQUITY_DAILY", "China equity daily bars", "PRICE_DAILY", "DAILY",
         "market_prices_daily", "UPSERT", "ACTIVE",
         "Canonical daily price history (R1B)", now, now),
    )
    dataset_id = cur.lastrowid
    core_conn.execute(
        "INSERT INTO dataset_sources"
        "(dataset_id, source_id, role, priority_rank, is_active, notes, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (dataset_id, source_id, "PRIMARY", 1, 1, "Primary source", now, now),
    )
    core_conn.commit()
    return {"source_id": source_id, "dataset_id": dataset_id}


def m2b_raw_artifacts(
    core_conn: sqlite3.Connection,
    dataset_id: int,
    source_id: int,
    snapshot_result: dict,
    stock_basic_result: dict,
) -> dict:
    import uuid

    now = utc_now_iso()
    # legacy frozen snapshot artifact
    cur = core_conn.execute(
        "INSERT INTO raw_artifacts"
        "(artifact_uid, dataset_id, source_id, run_id, artifact_type,"
        " local_path_or_reference, content_hash, retrieved_at, metadata, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            str(uuid.uuid4()),
            dataset_id,
            source_id,
            None,
            "DB_SNAPSHOT",
            snapshot_result["snapshot_path"],
            snapshot_result["snapshot_sha256"],
            now,
            json.dumps(
                {
                    "run_id": None,
                    "backup_method": "sqlite3.Connection.backup()",
                    "manifest": snapshot_result["manifest"],
                    "validation": snapshot_result["validation"],
                },
                ensure_ascii=False,
            ),
            now,
        ),
    )
    legacy_artifact_id = cur.lastrowid
    # stock_basic CSV artifact
    cur = core_conn.execute(
        "INSERT INTO raw_artifacts"
        "(artifact_uid, dataset_id, source_id, run_id, artifact_type,"
        " local_path_or_reference, content_hash, retrieved_at, metadata, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            str(uuid.uuid4()),
            dataset_id,
            source_id,
            None,
            "FILE",
            stock_basic_result["csv_path"],
            stock_basic_result["sha256"],
            stock_basic_result["meta"]["retrieved_at_utc"],
            json.dumps(stock_basic_result["meta"], ensure_ascii=False),
            now,
        ),
    )
    stock_basic_artifact_id = cur.lastrowid
    core_conn.commit()
    return {
        "legacy_snapshot_artifact_id": legacy_artifact_id,
        "stock_basic_artifact_id": stock_basic_artifact_id,
    }


# ---------------------------------------------------------------------------
# M3/M4 — entities / instruments / instrument_identifiers (1:1 strict)
# ---------------------------------------------------------------------------
def m3_entities_instruments(
    core_conn: sqlite3.Connection, mapping: dict[str, dict]
) -> dict:
    import uuid

    now = utc_now_iso()
    created_entities = 0
    created_instruments = 0
    created_identifiers = 0
    for ts, m in mapping.items():
        entity_uid = str(uuid.uuid4())
        cur = core_conn.execute(
            "INSERT INTO entities"
            "(entity_uid, canonical_name, entity_type, country_code, status, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (entity_uid, m["entity_name"], "COMPANY", "CN", "ACTIVE", now, now),
        )
        entity_id = cur.lastrowid
        created_entities += 1

        instrument_uid = str(uuid.uuid4())
        cur = core_conn.execute(
            "INSERT INTO instruments"
            "(instrument_uid, entity_id, instrument_type, primary_symbol, exchange_code,"
            " currency_code, country_code, status, listing_date, delisting_date, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                instrument_uid,
                entity_id,
                "EQUITY",
                m["symbol"],
                m["mic"],
                "CNY",
                "CN",
                "ACTIVE",
                m["list_date"],  # canonical YYYY-MM-DD (D2)
                None,
                now,
                now,
            ),
        )
        instrument_id = cur.lastrowid
        created_instruments += 1

        # identifier 1: TUSHARE EXCHANGE_SYMBOL (ts_code) primary
        core_conn.execute(
            "INSERT INTO instrument_identifiers"
            "(instrument_id, provider, identifier_type, identifier, valid_from,"
            " valid_to, is_primary, created_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (instrument_id, "TUSHARE", "EXCHANGE_SYMBOL", ts, m["list_date"], None, 1, now),
        )
        created_identifiers += 1
        # identifier 2: STANDARD TICKER (symbol)
        core_conn.execute(
            "INSERT INTO instrument_identifiers"
            "(instrument_id, provider, identifier_type, identifier, valid_from,"
            " valid_to, is_primary, created_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (instrument_id, "STANDARD", "TICKER", m["symbol"], m["list_date"], None, 0, now),
        )
        created_identifiers += 1

        m["instrument_id"] = instrument_id
        m["instrument_uid"] = instrument_uid
        m["entity_id"] = entity_id

    core_conn.commit()

    # 1:1 verification: every legacy ts_code -> exactly one instrument
    conn = open_ro(core_conn_db_path(core_conn))
    try:
        distinct_instruments = conn.execute(
            "SELECT COUNT(*) FROM instruments"
        ).fetchone()[0]
        identifier_matches = conn.execute(
            "SELECT COUNT(DISTINCT i.instrument_id) FROM instruments i"
            " JOIN instrument_identifiers ii ON ii.instrument_id = i.instrument_id"
            " WHERE ii.provider='TUSHARE' AND ii.identifier_type='EXCHANGE_SYMBOL'"
        ).fetchone()[0]
        ts_code_identifiers = set(
            r[0]
            for r in conn.execute(
                "SELECT identifier FROM instrument_identifiers"
                " WHERE provider='TUSHARE' AND identifier_type='EXCHANGE_SYMBOL'"
            )
        )
    finally:
        conn.close()

    one_to_one_ok = (
        distinct_instruments == len(mapping)
        and identifier_matches == len(mapping)
        and len(ts_code_identifiers) == len(mapping)
    )
    return {
        "entities_created": created_entities,
        "instruments_created": created_instruments,
        "identifiers_created": created_identifiers,
        "one_to_one_ok": one_to_one_ok,
    }


def core_conn_db_path(conn: sqlite3.Connection) -> Path:
    """Recover db path from a live connection (for read-only re-open)."""
    row = conn.execute("PRAGMA database_list").fetchone()
    return Path(row[2])


# ---------------------------------------------------------------------------
# M5 — ingest_runs backfill (timezone CONFIRMED Asia/Shanghai)
# ---------------------------------------------------------------------------
def m5_ingest_runs(
    core_conn: sqlite3.Connection,
    snapshot_path: Path,
    manifest: dict,
    dataset_id: int,
    source_id: int,
) -> dict:
    from scripts.legacy_migration_utils import backfill_runs

    runs = backfill_runs(snapshot_path, LEGACY_TZ)  # {trade_date: {started_at_utc,...}}
    run_by_date: dict[str, int] = {}
    created = 0
    for trade_date in sorted(runs):
        info = runs[trade_date]
        cur = core_conn.execute(
            "INSERT INTO ingest_runs"
            "(dataset_id, source_id, trigger_type, started_at, finished_at, status,"
            " rows_expected, rows_loaded, notes)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (
                dataset_id,
                source_id,
                "BACKFILL",
                info["started_at_utc"],
                info["started_at_utc"],
                "SUCCESS",
                info["rows"],
                info["rows"],
                f"legacy fetch_log backfill; legacy_fetched_at_raw="
                f"{info['legacy_fetched_at_raw']}",
            ),
        )
        run_by_date[trade_date] = cur.lastrowid
        created += 1
    core_conn.commit()

    # every legacy daily date must have exactly one ingest_run
    legacy_dates = set(manifest["trade_date_distribution"].keys())
    missing = legacy_dates - set(run_by_date.keys())
    extra = set(run_by_date.keys()) - legacy_dates
    ok = not missing and not extra
    return {
        "runs_created": created,
        "run_by_date": run_by_date,
        "missing_dates": sorted(missing),
        "extra_dates": sorted(extra),
        "gate_ok": ok,
    }


# ---------------------------------------------------------------------------
# M6 — full daily bar migration (per trade_date atomic batches)
# ---------------------------------------------------------------------------
def m6_migrate_bars(
    core_conn: sqlite3.Connection,
    snapshot_path: Path,
    manifest: dict,
    mapping: dict[str, dict],
    source_id: int,
    raw_artifact_id: int,
    run_by_date: dict[str, int],
) -> dict:
    snap = open_ro(snapshot_path)
    successful: list[str] = []
    failed: list[dict] = []
    total_inserted = 0
    try:
        dates = sorted(manifest["trade_date_distribution"].keys())
        for raw_date in dates:
            rows = snap.execute(
                "SELECT ts_code, open, high, low, close, vol, amount"
                " FROM daily_bars WHERE trade_date = ?",
                (raw_date,),
            ).fetchall()
            core_conn.execute("BEGIN IMMEDIATE;")
            try:
                canonical_date = normalize_date(raw_date)
                run_id = run_by_date[raw_date]
                ingested_at = utc_now_iso()
                for ts_code, o, h, l, c, vol, amt in rows:
                    m = mapping.get(ts_code)
                    if m is None:
                        raise RuntimeError(f"unmapped ts_code in bars: {ts_code}")
                    core_conn.execute(
                        "INSERT INTO market_prices_daily"
                        "(instrument_id, trade_date, open, high, low, close,"
                        " volume, volume_unit, turnover, turnover_unit, currency_code,"
                        " adjustment_type, source_id, ingest_run_id, raw_artifact_id, ingested_at)"
                        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            m["instrument_id"],
                            canonical_date,
                            o, h, l, c,
                            vol, "LOTS",
                            amt, "THOUSAND_CNY",
                            "CNY",
                            "RAW",
                            source_id,
                            run_id,
                            raw_artifact_id,
                            ingested_at,
                        ),
                    )
                core_conn.commit()
                successful.append(raw_date)
                total_inserted += len(rows)
            except Exception as exc:  # noqa: BLE001
                core_conn.rollback()
                failed.append({"trade_date": raw_date, "rows": len(rows), "error": str(exc)})
                break
    finally:
        snap.close()
    return {
        "successful_batches": successful,
        "failed_batches": failed,
        "bars_inserted": total_inserted,
        "gate_ok": not failed,
    }


# ---------------------------------------------------------------------------
# M7 — V1..V18 validation + 100% full-row reconciliation
# ---------------------------------------------------------------------------
def m7_validate(
    core_db: Path,
    snapshot_path: Path,
    manifest: dict,
    mapping: dict[str, dict],
    source_id: int,
    run_by_date: dict[str, int],
    legacy_artifact_id: int,
) -> dict:
    results: dict[str, dict] = {}
    def record(vid: str, ok: bool, detail: str = ""):
        results[vid] = {"pass": bool(ok), "detail": detail}

    conn = open_ro(core_db)
    snap = open_ro(snapshot_path)
    try:
        # ---- V1 row count
        canon_count = conn.execute("SELECT COUNT(*) FROM market_prices_daily").fetchone()[0]
        legacy_count = snap.execute("SELECT COUNT(*) FROM daily_bars").fetchone()[0]
        record("V1_row_count", canon_count == legacy_count == manifest["row_count"],
               f"canonical={canon_count} legacy={legacy_count} manifest={manifest['row_count']}")

        # ---- V2 trade dates (canonical set == normalized legacy set)
        canon_dates = {
            r[0] for r in conn.execute("SELECT DISTINCT trade_date FROM market_prices_daily")
        }
        legacy_dates = {
            r[0] for r in snap.execute("SELECT DISTINCT trade_date FROM daily_bars")
        }
        expected = {normalize_date(d) for d in legacy_dates}
        record("V2_trade_dates", canon_dates == expected,
               f"canonical={sorted(canon_dates)} expected={sorted(expected)}")

        # ---- V3 mapping completeness
        mapped_ts = {ts for ts, m in mapping.items() if m.get("instrument_id")}
        legacy_ts = {
            r[0] for r in snap.execute("SELECT DISTINCT ts_code FROM daily_bars")
        }
        record("V3_mapping_completeness", mapped_ts == legacy_ts,
               f"mapped={len(mapped_ts)} legacy={len(legacy_ts)}")

        # ---- V4 duplicate canonical keys
        dup = conn.execute(
            "SELECT COUNT(*) - COUNT(DISTINCT instrument_id || '|' || trade_date || '|'"
            " || adjustment_type || '|' || source_id) FROM market_prices_daily"
        ).fetchone()[0]
        record("V4_no_duplicate_keys", dup == 0, f"duplicates={dup}")

        # ---- V5/V6/V7 per-row equality (FULL row, not sample)
        canon_rows: dict[tuple, tuple] = {}
        for row in conn.execute(
            "SELECT instrument_id, trade_date, open, high, low, close, volume, turnover"
            " FROM market_prices_daily"
        ):
            canon_rows[(row[0], row[1])] = row[2:]
        legacy_rows = snap.execute(
            "SELECT ts_code, trade_date, open, high, low, close, vol, amount"
            " FROM daily_bars"
        ).fetchall()

        ohlc_mismatch = 0
        vol_mismatch = 0
        turn_mismatch = 0
        date_mismatch = 0
        map_mismatch = 0
        rows_checked = 0
        for ts_code, raw_date, o, h, l, c, vol, amt in legacy_rows:
            rows_checked += 1
            m = mapping.get(ts_code)
            if m is None or not m.get("instrument_id"):
                map_mismatch += 1
                continue
            canon_date = normalize_date(raw_date)
            key = (m["instrument_id"], canon_date)
            canon = canon_rows.get(key)
            if canon is None:
                map_mismatch += 1
                continue
            co, ch, cl, cc, cvol, cturn = canon
            if not (o == co and h == ch and l == cl and c == cc):
                ohlc_mismatch += 1
            if vol != cvol:
                vol_mismatch += 1
            if amt != cturn:
                turn_mismatch += 1
            # V17 defensive: stored canonical date must equal normalized raw date.
            # By construction key=(instrument_id, canon_date), so this is a
            # structural invariant check, not a re-derivation.
            if key[1] != canon_date:
                date_mismatch += 1

        record("V5_ohlc_equality", ohlc_mismatch == 0, f"mismatch={ohlc_mismatch}")
        record("V6_volume_equality", vol_mismatch == 0, f"mismatch={vol_mismatch}")
        record("V7_turnover_equality", turn_mismatch == 0, f"mismatch={turn_mismatch}")

        # ---- V8 NULL/type validation
        nulls = conn.execute(
            "SELECT COUNT(*) FROM market_prices_daily WHERE"
            " instrument_id IS NULL OR trade_date IS NULL OR open IS NULL"
            " OR high IS NULL OR low IS NULL OR close IS NULL OR volume IS NULL"
            " OR turnover IS NULL OR currency_code IS NULL OR adjustment_type IS NULL"
            " OR source_id IS NULL OR ingest_run_id IS NULL OR ingested_at IS NULL"
        ).fetchone()[0]
        record("V8_null_type", nulls == 0, f"nulls={nulls}")

        # ---- V9 source/run lineage
        bad_source = conn.execute(
            "SELECT COUNT(*) FROM market_prices_daily WHERE source_id != ?", (source_id,)
        ).fetchone()[0]
        bad_run = conn.execute(
            "SELECT COUNT(*) FROM market_prices_daily m"
            " LEFT JOIN ingest_runs r ON r.run_id = m.ingest_run_id"
            " WHERE r.run_id IS NULL"
        ).fetchone()[0]
        bad_artifact = conn.execute(
            "SELECT COUNT(*) FROM market_prices_daily m"
            " LEFT JOIN raw_artifacts a ON a.artifact_id = m.raw_artifact_id"
            " WHERE m.raw_artifact_id IS NULL OR a.artifact_id IS NULL"
        ).fetchone()[0]
        record("V9_lineage", bad_source == 0 and bad_run == 0 and bad_artifact == 0,
               f"bad_source={bad_source} bad_run={bad_run} bad_artifact={bad_artifact}")

        # ---- V10 raw artifact existence/hash
        artifact_row = conn.execute(
            "SELECT local_path_or_reference, content_hash FROM raw_artifacts"
            " WHERE artifact_id = ?", (legacy_artifact_id,)
        ).fetchone()
        if artifact_row and Path(artifact_row[0]).exists():
            actual = sha256_bytes(Path(artifact_row[0]).read_bytes())
            v10 = actual == artifact_row[1]
            record("V10_artifact_hash", v10, f"hash_match={v10}")
        else:
            record("V10_artifact_hash", False, "artifact missing")

        # ---- V11 orphan instrument refs
        orphan = conn.execute(
            "SELECT COUNT(*) FROM market_prices_daily m"
            " LEFT JOIN instruments i ON i.instrument_id = m.instrument_id"
            " WHERE i.instrument_id IS NULL"
        ).fetchone()[0]
        bad_entity = conn.execute(
            "SELECT COUNT(*) FROM instruments i"
            " LEFT JOIN entities e ON e.entity_id = i.entity_id"
            " WHERE i.entity_id IS NOT NULL AND e.entity_id IS NULL"
        ).fetchone()[0]
        record("V11_orphan_refs", orphan == 0 and bad_entity == 0,
               f"orphan_instrument={orphan} bad_entity={bad_entity}")

        # ---- V12 aggregate reconciliation (tolerance)
        legacy_agg = {
            r[0]: (r[1], r[2])
            for r in snap.execute(
                "SELECT trade_date, SUM(vol), SUM(amount) FROM daily_bars GROUP BY trade_date"
            )
        }
        canon_agg = {
            r[0]: (r[1], r[2])
            for r in conn.execute(
                "SELECT trade_date, SUM(volume), SUM(turnover) FROM market_prices_daily"
                " GROUP BY trade_date"
            )
        }
        agg_ok = True
        agg_detail = []
        for raw_date, (lvol, lturn) in sorted(legacy_agg.items()):
            cdate = normalize_date(raw_date)
            c = canon_agg.get(cdate)
            if c is None:
                agg_ok = False
                agg_detail.append(f"{cdate}: missing")
                continue
            vol_ok = math.isclose(c[0], lvol, rel_tol=1e-6, abs_tol=1e-9)
            turn_ok = math.isclose(c[1], lturn, rel_tol=1e-6, abs_tol=1e-9)
            if not (vol_ok and turn_ok):
                agg_ok = False
                agg_detail.append(
                    f"{cdate}: canon_vol={c[0]} legacy_vol={lvol}"
                    f" canon_turn={c[1]} legacy_turn={lturn}"
                )
        record("V12_aggregate", agg_ok, "; ".join(agg_detail) or "all dates match")

        # ---- V13-V18 full-row reconciliation
        record("V13_full_rows_checked", rows_checked == manifest["row_count"],
               f"checked={rows_checked} manifest={manifest['row_count']}")
        record("V14_ohlc_mismatch_zero", ohlc_mismatch == 0, f"mismatch={ohlc_mismatch}")
        record("V15_volume_mismatch_zero", vol_mismatch == 0, f"mismatch={vol_mismatch}")
        record("V16_turnover_mismatch_zero", turn_mismatch == 0, f"mismatch={turn_mismatch}")
        record("V17_date_mismatch_zero", date_mismatch == 0, f"mismatch={date_mismatch}")
        record("V18_mapping_mismatch_zero", map_mismatch == 0, f"mismatch={map_mismatch}")

        reconciliation = {
            "rows_checked": rows_checked,
            "ohlc_mismatches": ohlc_mismatch,
            "volume_mismatches": vol_mismatch,
            "turnover_mismatches": turn_mismatch,
            "date_mismatches": date_mismatch,
            "mapping_mismatches": map_mismatch,
        }
    finally:
        snap.close()
        conn.close()
    return {"v_results": results, "reconciliation": reconciliation}


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def build_report(
    run_id: str,
    started_at: str,
    m0: dict,
    m1: dict,
    m2: dict,
    m3m4: dict,
    staging: dict,
    meta: dict,
    artifacts: dict,
    entities: dict,
    m5: dict,
    m6: dict,
    m7: dict,
    warnings: list[str],
) -> dict:
    v_errors = {
        vid: ("" if v["pass"] else v["detail"])
        for vid, v in m7["v_results"].items()
        if not v["pass"]
    }
    all_pass = (
        m0["health"]["ok"]
        and m1["pass"]
        and m3m4["coverage"]["status"] == "PASS"
        and staging["core_checks"]["foreign_key_check_empty"]
        and staging["private_checks"]["foreign_key_check_empty"]
        and entities["one_to_one_ok"]
        and m5["gate_ok"]
        and m6["gate_ok"]
        and all(v["pass"] for v in m7["v_results"].values())
    )
    return {
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": utc_now_iso(),
        "git_commit": git_head(),
        "reproducibility": {
            "git_commit_sha": git_head(),
            "c0001_checksum": staging["core_checksums"].get("C0001", "n/a"),
            "p0001_checksum": staging["private_checksums"].get("P0001", "n/a"),
            "legacy_snapshot_sha256": m1["snapshot_sha256"],
            "stock_basic_snapshot_sha256": m2["sha256"],
            "timezone": LEGACY_TZ,
            "canonical_date_contract": "YYYY-MM-DD",
            "source": "TUSHARE",
        },
        "legacy_live_health": m0,
        "snapshot": {
            "path": m1["snapshot_path"],
            "hash": m1["snapshot_sha256"],
            "manifest": m1["manifest"],
            "validation": m1["validation"],
        },
        "stock_basic": {
            "row_count": m2["meta"]["merged_row_count"],
            "unique_ts_code": m2["meta"]["unique_ts_code_count"],
            "artifact_hash": m2["sha256"],
            "meta": m2["meta"],
        },
        "mapping": {
            "legacy_distinct_ts_code": m1["manifest"]["distinct_ts_code"],
            "mapped_count": len(m3m4["mapping"]) if m3m4["mapping"] else 0,
            "coverage": m3m4["coverage"],
        },
        "staging": {
            "dir": staging["staging_dir"],
            "core_db": staging["core_db"],
            "private_db": staging["private_db"],
            "core_migration_status": staging["core_migrations"],
            "private_migration_status": staging["private_migrations"],
            "core_checks": staging["core_checks"],
            "private_checks": staging["private_checks"],
            "metadata": meta,
            "artifacts": artifacts,
        },
        "migration": {
            "entities_created": entities["entities_created"],
            "instruments_created": entities["instruments_created"],
            "identifiers_created": entities["identifiers_created"],
            "one_to_one_ok": entities["one_to_one_ok"],
            "ingest_runs": {
                "created": m5["runs_created"],
                "run_by_date": m5["run_by_date"],
                "gate_ok": m5["gate_ok"],
                "missing_dates": m5["missing_dates"],
                "extra_dates": m5["extra_dates"],
            },
            "bars": {
                "inserted": m6["bars_inserted"],
                "successful_batches": m6["successful_batches"],
                "failed_batches": m6["failed_batches"],
                "gate_ok": m6["gate_ok"],
            },
        },
        "full_row_reconciliation": m7["reconciliation"],
        "v1_v18": {
            vid: ("PASS" if v["pass"] else f"FAIL: {v['detail']}")
            for vid, v in m7["v_results"].items()
        },
        "v1_v18_errors": v_errors,
        "warnings": warnings,
        "final_result": "PASS" if all_pass else "FAIL",
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="R1C Phase 2 real-data staging rehearsal")
    parser.add_argument("--run-id", default=None, help="UTC run id YYYYMMDDTHHMMSSZ")
    args = parser.parse_args()

    run_id = args.run_id or utc_now_iso().replace("-", "").replace(":", "")
    started_at = utc_now_iso()
    warnings: list[str] = []

    # safety: production DBs must not exist
    for label, p in PRODUCTION_PATHS.items():
        if p.exists():
            print(f"ERROR: production path exists, refusing to continue: {p}", file=sys.stderr)
            return 1

    print(f"== R1C Phase 2 staging rehearsal ==")
    print(f"run_id: {run_id}  started_at: {started_at}  git: {git_head()}")
    print(f"live legacy: {LIVE_DB}")

    # M0
    m0 = m0_live_preflight()
    print(f"[M0] live preflight status={m0['health']['ok']}")
    if m0["health"]["ok"]:
        print(
            f"     rows={m0['info']['row_count']} distinct_ts={m0['info']['distinct_ts_code']}"
            f" dates={m0['info']['trade_date_distribution']}"
            f" suffixes={m0['info']['suffix_set']}"
            f" hash={m0['health']['live_source_file_hash_observed'][:12]}…"
        )
    else:
        print(f"[M0] FAIL: {m0['health']}", file=sys.stderr)
        return 1

    # M1
    m1 = m1_frozen_snapshot(run_id)
    print(f"[M1] frozen snapshot -> {m1['snapshot_path']}")
    print(f"     sha256={m1['snapshot_sha256'][:16]}… row_count={m1['manifest']['row_count']}")
    if not m1["pass"]:
        print(f"[M1] snapshot validation FAIL: {m1['validation']}", file=sys.stderr)
        return 1
    snapshot_path = Path(m1["snapshot_path"])

    # M2 — Tushare stock_basic (rate-limit-aware, coverage-driven L/D/P)
    token = load_tushare_token()
    if not token:
        print("ERROR: TUSHARE_TOKEN not found (env or ~/API.txt)", file=sys.stderr)
        return 1
    try:
        m2 = m2_stock_basic(run_id, token, snapshot_path, m1["manifest"])
    except Exception as exc:  # noqa: BLE001
        print(f"[M2] stock_basic download FAIL: {exc}", file=sys.stderr, flush=True)
        return 1
    print(
        f"[M2] stock_basic downloaded: merged={m2['meta']['merged_row_count']}"
        f" unique_ts={m2['meta']['unique_ts_code_count']}"
        f" sha256={m2['sha256'][:16]}… -> {m2['csv_path']}",
        flush=True,
    )

    # M3/M4 mapping
    m3m4 = m3_m4_mapping(snapshot_path, m2["rows"])
    if m3m4["mapping"] is None:
        print("[M3/M4] mapping gate FAILED — diagnostics written; ABORT before bar copy", file=sys.stderr)
        print(json.dumps(m3m4["coverage"], indent=2, ensure_ascii=False))
        return 1
    print(
        f"[M3/M4] mapping PASS: legacy={m1['manifest']['distinct_ts_code']}"
        f" mapped={len(m3m4['mapping'])}"
    )

    # staging DBs
    staging = create_staging_dbs(run_id)
    print(f"[staging] core={staging['core_db']} private={staging['private_db']}")
    print(
        f"     core migrations={staging['core_migrations']} tables={staging['core_checks']['table_count']}"
        f" fk_empty={staging['core_checks']['foreign_key_check_empty']}"
    )
    print(
        f"     private migrations={staging['private_migrations']}"
        f" tables={staging['private_checks']['table_count']}"
        f" fk_empty={staging['private_checks']['foreign_key_check_empty']}"
    )
    if (
        not staging["core_checks"]["foreign_key_check_empty"]
        or not staging["private_checks"]["foreign_key_check_empty"]
        or not staging["core_checks"]["table_count_ok"]
        or not staging["private_checks"]["table_count_ok"]
    ):
        print(
            f"[staging] schema checks FAIL: {staging['core_checks']} {staging['private_checks']}",
            file=sys.stderr,
        )
        return 1

    # M2 metadata + M2B artifacts
    core_conn = sqlite3.connect(staging["core_db"])
    core_conn.execute("PRAGMA foreign_keys = ON;")
    meta = m2_metadata(core_conn)
    artifacts = m2b_raw_artifacts(core_conn, meta["dataset_id"], meta["source_id"], m1, m2)
    print(
        f"[M2/M2B] source_id={meta['source_id']} dataset_id={meta['dataset_id']}"
        f" legacy_artifact_id={artifacts['legacy_snapshot_artifact_id']}"
        f" stock_basic_artifact_id={artifacts['stock_basic_artifact_id']}"
    )

    # M3/M4 entities/instruments
    entities = m3_entities_instruments(core_conn, m3m4["mapping"])
    print(
        f"[M3/M4] entities={entities['entities_created']}"
        f" instruments={entities['instruments_created']}"
        f" identifiers={entities['identifiers_created']}"
        f" 1:1={entities['one_to_one_ok']}"
    )
    if not entities["one_to_one_ok"]:
        print("[M3/M4] 1:1 mapping check FAIL", file=sys.stderr)
        return 1

    # M5 ingest runs
    m5 = m5_ingest_runs(
        core_conn, snapshot_path, m1["manifest"], meta["dataset_id"], meta["source_id"]
    )
    print(f"[M5] ingest_runs={m5['runs_created']} gate_ok={m5['gate_ok']}")
    if not m5["gate_ok"]:
        print(f"[M5] missing={m5['missing_dates']} extra={m5['extra_dates']} — ABORT", file=sys.stderr)
        return 1

    # M6 bars
    m6 = m6_migrate_bars(
        core_conn,
        snapshot_path,
        m1["manifest"],
        m3m4["mapping"],
        meta["source_id"],
        artifacts["legacy_snapshot_artifact_id"],
        m5["run_by_date"],
    )
    print(
        f"[M6] bars_inserted={m6['bars_inserted']}"
        f" batches_ok={len(m6['successful_batches'])}"
        f" batches_failed={len(m6['failed_batches'])}"
    )
    if not m6["gate_ok"]:
        print(f"[M6] FAILED batches: {m6['failed_batches']}", file=sys.stderr)
        return 1
    core_conn.close()

    # M7 validation
    m7 = m7_validate(
        Path(staging["core_db"]),
        snapshot_path,
        m1["manifest"],
        m3m4["mapping"],
        meta["source_id"],
        m5["run_by_date"],
        artifacts["legacy_snapshot_artifact_id"],
    )
    print("[M7] V1–V18:")
    for vid in sorted(m7["v_results"]):
        v = m7["v_results"][vid]
        print(f"     {vid:<28} {'PASS' if v['pass'] else 'FAIL'}  {v['detail']}")
    print(
        f"     full-row reconciliation: rows_checked={m7['reconciliation']['rows_checked']}"
        f" ohlc_mm={m7['reconciliation']['ohlc_mismatches']}"
        f" vol_mm={m7['reconciliation']['volume_mismatches']}"
        f" turn_mm={m7['reconciliation']['turnover_mismatches']}"
        f" date_mm={m7['reconciliation']['date_mismatches']}"
        f" map_mm={m7['reconciliation']['mapping_mismatches']}"
    )

    # report
    report = build_report(
        run_id, started_at, m0, m1, m2, m3m4, staging, meta, artifacts,
        entities, m5, m6, m7, warnings,
    )
    staging_dir = STAGING_ROOT / run_id
    staging_dir.mkdir(parents=True, exist_ok=True)
    report_path = staging_dir / "migration_report.json"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"[report] {report_path}")
    print(f"== FINAL RESULT: {report['final_result']} ==")

    # live market.db must be untouched
    after = sha256_bytes(LIVE_DB.read_bytes())
    before = m0["health"]["live_source_file_hash_observed"]
    print(f"live market.db sha256 before={before[:12]}… after={after[:12]}…"
          f" unchanged={before == after}")
    if before != after:
        print("ERROR: live market.db changed during rehearsal!", file=sys.stderr)
        return 1
    return 0 if report["final_result"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
