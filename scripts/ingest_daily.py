#!/usr/bin/env python3
"""
ingest_daily.py — R3-A: canonical incremental daily-bar ingestion (stdlib only)

Berlin-authorized (2026-08-27, R3-A): new real trading days from the legacy
market.db (the reliable raw input maintained by the fetch_daily.py cron) are
ingested into production core.db.market_prices_daily.

Flow (per trade date):

  legacy daily_bars (read-only)
    -> per-day raw artifact JSON (data/raw/tushare/daily_YYYY-MM-DD.json, sha256)
    -> ingest_run (CN_EQUITY_DAILY / TUSHARE)
    -> stable instrument_uid mapping (instrument_identifiers, NEVER new identity)
    -> controlled upsert into market_prices_daily (DB-D031)
    -> post-validation (expected == loaded, lineage complete)

Semantics:
  * Reuses production stable instrument_uid via instrument_identifiers
    (provider='TUSHARE', identifier_type='EXCHANGE_SYMBOL', valid_to IS NULL);
    this script NEVER creates instruments/entities/identifiers.
  * Controlled upsert key = UNIQUE(instrument_id, trade_date, adjustment_type,
    source_id) -> re-running the same trade_date is idempotent (row count
    unchanged, bar_id stable).
  * Unknown instrument / abnormal date (no legacy rows) / NULL required
    fields / incomplete mapping -> explicit failure (MappingGateError /
    IngestValidationError), never silent drops.
  * Writes are atomic (DB-D034): ingest_run + raw_artifact + bars committed
    together; a failure rolls back bars and records a FAILED ingest_run.

Usage:
  python3 scripts/ingest_daily.py --date 2026-08-25 --allow-production
  python3 scripts/ingest_daily.py --latest --allow-production
  python3 scripts/ingest_daily.py --reconcile 2026-08-25
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts import migrate  # noqa: E402
from scripts.date_utils import normalize_date, DateNormalizationError  # noqa: E402
from scripts.legacy_migration_utils import MappingGateError, SUFFIX_MIC  # noqa: E402
from scripts.timestamp_utils import utc_now_iso  # noqa: E402

DEFAULT_LEGACY = PROJECT_ROOT / "data" / "market.db"
DEFAULT_CORE = PROJECT_ROOT / "data" / "runtime" / "core.db"
DEFAULT_RAW_DIR = PROJECT_ROOT / "data" / "raw" / "tushare"
DEFAULT_REPORT_DIR = PROJECT_ROOT / "data" / "staging" / "r3a"

DATASET_CODE = "CN_EQUITY_DAILY"
SOURCE_CODE = "TUSHARE"
ADJUSTMENT_TYPE = "RAW"
VOLUME_UNIT = "LOTS"
TURNOVER_UNIT = "THOUSAND_CNY"
CURRENCY_CODE = "CNY"

# Production-write guard (mirrors migrate.PRODUCTION_WRITES_ENABLED).
# R3-A is Berlin-authorized; explicit --allow-production flag required for the
# production path. Default stays False.
PRODUCTION_WRITES_ENABLED = False

REQUIRED_BAR_FIELDS = ("open", "high", "low", "close", "vol", "amount")


class IngestValidationError(ValueError):
    """Payload rows failed validation (NULL required field, bad ts_code...)."""


class NoDataForDateError(ValueError):
    """Legacy has no rows for the requested trade date (not a trading day)."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def connect_ro(db_path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True)


# ---------------------------------------------------------------------------
# Legacy read + raw artifact export
# ---------------------------------------------------------------------------
def load_legacy_day(legacy_path: Path, canonical_date: str) -> list[dict]:
    """Read one trading day from legacy daily_bars (canonical YYYY-MM-DD)."""
    raw_date = canonical_date.replace("-", "")
    conn = connect_ro(legacy_path)
    try:
        rows = conn.execute(
            "SELECT ts_code, open, high, low, close, vol, amount "
            "FROM daily_bars WHERE trade_date = ? ORDER BY ts_code",
            (raw_date,),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        raise NoDataForDateError(
            f"no legacy data for trade_date {canonical_date} "
            f"(not a trading day or not yet downloaded)"
        )

    out = []
    for r in rows:
        bar = {
            "ts_code": r[0],
            "open": r[1], "high": r[2], "low": r[3], "close": r[4],
            "vol": r[5], "amount": r[6],
        }
        if not isinstance(bar["ts_code"], str) or not bar["ts_code"]:
            raise IngestValidationError(f"empty ts_code in legacy row: {r}")
        for f in REQUIRED_BAR_FIELDS:
            if bar[f] is None:
                raise IngestValidationError(
                    f"NULL required field {f!r} for {bar['ts_code']} "
                    f"on {canonical_date}: partial data, refusing to ingest"
                )
        out.append(bar)
    return out


def export_raw_payload(
    raw_dir: Path, canonical_date: str, rows: list[dict]
) -> dict:
    """Persist the day payload as a raw artifact file; return path + sha256."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": SOURCE_CODE,
        "api": "daily",
        "trade_date": canonical_date,
        "exported_at_utc": utc_now_iso(),
        "row_count": len(rows),
        "rows": rows,
    }
    data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    path = raw_dir / f"daily_{canonical_date}.json"
    path.write_bytes(data)
    return {"path": str(path), "content_hash": sha256_bytes(data)}


# ---------------------------------------------------------------------------
# Core resolution + mapping (stable UID only)
# ---------------------------------------------------------------------------
def resolve_dataset_source(conn: sqlite3.Connection) -> tuple[int, int]:
    ds = conn.execute(
        "SELECT dataset_id FROM datasets WHERE dataset_code = ?",
        (DATASET_CODE,),
    ).fetchone()
    src = conn.execute(
        "SELECT source_id FROM data_sources WHERE source_code = ?",
        (SOURCE_CODE,),
    ).fetchone()
    if not ds or not src:
        raise IngestValidationError(
            "core.db missing canonical dataset/source metadata "
            f"({DATASET_CODE}/{SOURCE_CODE})"
        )
    dataset_id, source_id = ds[0], src[0]
    link = conn.execute(
        "SELECT 1 FROM dataset_sources"
        " WHERE dataset_id=? AND source_id=? AND role='PRIMARY' AND is_active=1",
        (dataset_id, source_id),
    ).fetchone()
    if not link:
        raise IngestValidationError(
            "no active PRIMARY dataset_sources link for "
            f"{DATASET_CODE}/{SOURCE_CODE}"
        )
    return dataset_id, source_id


def build_ts_code_map(conn: sqlite3.Connection) -> dict[str, int]:
    """ts_code -> instrument_id via CURRENT TUSHARE EXCHANGE_SYMBOL identifiers.

    Stable instrument_uid is preserved by construction: we only resolve
    existing instruments, never create new ones.
    """
    rows = conn.execute(
        "SELECT ii.identifier, i.instrument_id"
        " FROM instrument_identifiers ii"
        " JOIN instruments i ON i.instrument_id = ii.instrument_id"
        " WHERE ii.provider=? AND ii.identifier_type='EXCHANGE_SYMBOL'"
        "   AND ii.valid_to IS NULL",
        (SOURCE_CODE,),
    ).fetchall()
    mapping: dict[str, int] = {}
    for identifier, instrument_id in rows:
        if identifier in mapping and mapping[identifier] != instrument_id:
            raise IngestValidationError(
                f"ambiguous current TUSHARE EXCHANGE_SYMBOL {identifier!r}"
            )
        mapping[identifier] = instrument_id
    return mapping


def _unique_started_at(
    conn: sqlite3.Connection, dataset_id: int, source_id: int, base: str
) -> str:
    """ingest_runs UNIQUE(dataset_id, source_id, started_at): bump by 1s."""
    candidate = base
    for _ in range(120):
        hit = conn.execute(
            "SELECT 1 FROM ingest_runs"
            " WHERE dataset_id=? AND source_id=? AND started_at=?",
            (dataset_id, source_id, candidate),
        ).fetchone()
        if not hit:
            return candidate
        ts = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        candidate = (
            (ts + timedelta(seconds=1))
            .astimezone(timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ")
        )
    raise IngestValidationError("could not allocate unique ingest_run.started_at")


# ---------------------------------------------------------------------------
# Identity expansion (new listings / resumed instruments only)
# ---------------------------------------------------------------------------
def resolve_stock_basic_path(conn: sqlite3.Connection) -> Path | None:
    """Find the registered stock_basic FILE artifact path in core.db."""
    row = conn.execute(
        "SELECT local_path_or_reference FROM raw_artifacts"
        " WHERE artifact_type='FILE' AND local_path_or_reference LIKE '%stock_basic%'"
        " ORDER BY artifact_id DESC LIMIT 1"
    ).fetchone()
    if not row or not row[0]:
        return None
    p = Path(row[0])
    return p if p.exists() else None


def parse_stock_basic(path: Path) -> dict[str, dict]:
    """Parse a stock_basic CSV (ts_code header) into {ts_code: info}."""
    import csv

    out: dict[str, dict] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ts = (row.get("ts_code") or "").strip()
            if not ts:
                continue
            out[ts] = {
                "symbol": (row.get("symbol") or "").strip(),
                "name": (row.get("name") or "").strip(),
                "list_date_raw": (row.get("list_date") or "").strip(),
            }
    return out


def create_missing_instruments(
    conn: sqlite3.Connection,
    missing: list[str],
    stock_basic: dict[str, dict],
) -> list[dict]:
    """Create entity+instrument+identifiers for NEW ts_codes (new UUIDs).

    Only called for ts_codes genuinely absent from core identity; existing
    instruments are NEVER touched (stable instrument_uid preserved).
    Mirrors phase2 m3_entities_instruments semantics.
    """
    now = utc_now_iso()
    created: list[dict] = []
    for ts in sorted(missing):
        info = stock_basic.get(ts)
        if info is None:
            raise MappingGateError(f"unknown instrument not in stock_basic: {ts}")
        suffix = ts.split(".")[-1]
        if suffix not in SUFFIX_MIC:
            raise MappingGateError(f"unknown ts_code suffix {suffix!r} for {ts}")
        if not info["symbol"] or not info["name"]:
            raise MappingGateError(f"stock_basic missing fields for {ts}")
        list_date = normalize_date(info["list_date_raw"] or "19700101")

        entity_uid = str(uuid.uuid4())
        cur = conn.execute(
            "INSERT INTO entities"
            "(entity_uid, canonical_name, entity_type, country_code, status,"
            " created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
            (entity_uid, info["name"], "COMPANY", "CN", "ACTIVE", now, now),
        )
        entity_id = cur.lastrowid

        instrument_uid = str(uuid.uuid4())
        cur = conn.execute(
            "INSERT INTO instruments"
            "(instrument_uid, entity_id, instrument_type, primary_symbol,"
            " exchange_code, currency_code, country_code, status, listing_date,"
            " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (instrument_uid, entity_id, "EQUITY", info["symbol"],
             SUFFIX_MIC[suffix], "CNY", "CN", "ACTIVE", list_date, now, now),
        )
        instrument_id = cur.lastrowid

        conn.execute(
            "INSERT INTO instrument_identifiers"
            "(instrument_id, provider, identifier_type, identifier, valid_from,"
            " is_primary, created_at) VALUES (?,?,?,?,?,?,?)",
            (instrument_id, "TUSHARE", "EXCHANGE_SYMBOL", ts, list_date, 1, now),
        )
        conn.execute(
            "INSERT INTO instrument_identifiers"
            "(instrument_id, provider, identifier_type, identifier, valid_from,"
            " is_primary, created_at) VALUES (?,?,?,?,?,?,?)",
            (instrument_id, "STANDARD", "TICKER", info["symbol"],
             list_date, 0, now),
        )
        created.append(
            {"ts_code": ts, "instrument_uid": instrument_uid,
             "instrument_id": instrument_id}
        )
    return created


# ---------------------------------------------------------------------------
# Core write (atomic, DB-D034)
# ---------------------------------------------------------------------------
def ingest_date(
    core_path: Path,
    legacy_path: Path,
    date_str: str,
    *,
    trigger: str = "MANUAL",
    raw_dir: Path = DEFAULT_RAW_DIR,
    allow_production: bool = False,
    stock_basic_path: Path | None = None,
) -> dict:
    """Ingest one canonical trade date; returns a JSON-safe report dict.

    Raises on any failure BEFORE/AFTER writes; bars are atomic with the run.
    New ts_codes (new listings / resumed instruments) are resolved from the
    registered stock_basic artifact when possible; unresolvable instruments
    raise MappingGateError (explicit failure, never silent drops).
    """
    try:
        canonical_date = normalize_date(date_str)
    except DateNormalizationError as exc:
        raise IngestValidationError(f"invalid date: {date_str!r}") from exc

    # --- preflight (no core writes) ---
    rows = load_legacy_day(legacy_path, canonical_date)
    artifact = export_raw_payload(raw_dir, canonical_date, rows)

    core_resolved = core_path.resolve()
    if core_resolved == migrate.PRODUCTION_PATHS["core"] and not (
        allow_production or PRODUCTION_WRITES_ENABLED
    ):
        raise migrate.ProductionWriteNotAuthorizedError(
            f"writing production core.db is not authorized: {core_path} "
            "(pass --allow-production for R3-A authorized ingestion)"
        )

    conn = migrate.connect_db(core_path)
    run_id: int | None = None
    try:
        dataset_id, source_id = resolve_dataset_source(conn)
        ts_map = build_ts_code_map(conn)

        missing = sorted({b["ts_code"] for b in rows} - set(ts_map))
        stock_basic: dict[str, dict] = {}
        identities_created: list[dict] = []
        if missing:
            sb_path = stock_basic_path or resolve_stock_basic_path(conn)
            if sb_path is None:
                raise MappingGateError(
                    f"{len(missing)} unknown instrument(s) for {canonical_date} "
                    f"and no registered stock_basic artifact to resolve them: "
                    f"{missing[:5]}"
                )
            stock_basic = parse_stock_basic(sb_path)
            # fail fast BEFORE any write if unresolvable
            unresolvable = [ts for ts in missing if ts not in stock_basic]
            if unresolvable:
                raise MappingGateError(
                    f"100% mapping gate failed for {canonical_date}: "
                    f"{len(unresolvable)} instrument(s) unknown to stock_basic: "
                    f"{unresolvable[:5]}"
                )

        started_at = _unique_started_at(
            conn, dataset_id, source_id, utc_now_iso()
        )

        conn.execute("BEGIN IMMEDIATE;")
        try:
            cur = conn.execute(
                "INSERT INTO ingest_runs"
                "(dataset_id, source_id, trigger_type, started_at, finished_at,"
                " status, rows_expected, rows_loaded, notes)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    dataset_id, source_id, trigger, started_at, None,
                    "RUNNING", len(rows), None,
                    f"R3-A canonical ingest {canonical_date} from legacy "
                    f"{legacy_path.name}",
                ),
            )
            run_id = cur.lastrowid

            # expand identity for genuinely new instruments (atomic with run)
            if missing:
                identities_created = create_missing_instruments(
                    conn, missing, stock_basic
                )
                ts_map = build_ts_code_map(conn)

            cur = conn.execute(
                "INSERT INTO raw_artifacts"
                "(artifact_uid, dataset_id, source_id, run_id, artifact_type,"
                " local_path_or_reference, content_hash, retrieved_at, metadata,"
                " created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    str(uuid.uuid4()), dataset_id, source_id, run_id, "FILE",
                    artifact["path"], artifact["content_hash"], utc_now_iso(),
                    json.dumps(
                        {
                            "trade_date": canonical_date,
                            "row_count": len(rows),
                            "source_api": "tushare daily",
                            "exported_from_legacy": str(legacy_path),
                        },
                        ensure_ascii=False,
                    ),
                    utc_now_iso(),
                ),
            )
            artifact_id = cur.lastrowid

            ingested_at = utc_now_iso()
            for bar in rows:
                instrument_id = ts_map[bar["ts_code"]]
                conn.execute(
                    "INSERT INTO market_prices_daily"
                    "(instrument_id, trade_date, open, high, low, close,"
                    " volume, volume_unit, turnover, turnover_unit, currency_code,"
                    " adjustment_type, source_id, ingest_run_id, raw_artifact_id,"
                    " ingested_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
                    " ON CONFLICT(instrument_id, trade_date, adjustment_type,"
                    " source_id) DO UPDATE SET"
                    " open=excluded.open, high=excluded.high, low=excluded.low,"
                    " close=excluded.close, volume=excluded.volume,"
                    " turnover=excluded.turnover,"
                    " ingest_run_id=excluded.ingest_run_id,"
                    " raw_artifact_id=excluded.raw_artifact_id,"
                    " ingested_at=excluded.ingested_at",
                    (
                        instrument_id, canonical_date,
                        bar["open"], bar["high"], bar["low"], bar["close"],
                        bar["vol"], VOLUME_UNIT,
                        bar["amount"], TURNOVER_UNIT,
                        CURRENCY_CODE, ADJUSTMENT_TYPE,
                        source_id, run_id, artifact_id, ingested_at,
                    ),
                )

            # post-validation: exact expected == loaded for this date+source
            loaded = conn.execute(
                "SELECT COUNT(*) FROM market_prices_daily"
                " WHERE trade_date=? AND source_id=? AND adjustment_type=?",
                (canonical_date, source_id, ADJUSTMENT_TYPE),
            ).fetchone()[0]
            if loaded != len(rows):
                raise IngestValidationError(
                    f"loaded {loaded} != expected {len(rows)} for "
                    f"{canonical_date} (source {source_id})"
                )

            conn.execute(
                "UPDATE ingest_runs SET status='SUCCESS', finished_at=?,"
                " rows_loaded=? WHERE run_id=?",
                (utc_now_iso(), len(rows), run_id),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            # record a FAILED run for auditability (separate transaction)
            try:
                conn.execute("BEGIN IMMEDIATE;")
                conn.execute(
                    "INSERT INTO ingest_runs"
                    "(dataset_id, source_id, trigger_type, started_at,"
                    " finished_at, status, rows_expected, rows_loaded, notes)"
                    " VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        dataset_id, source_id, trigger, started_at,
                        utc_now_iso(), "FAILED", len(rows), None,
                        f"R3-A ingest failed for {canonical_date}",
                    ),
                )
                conn.commit()
            except Exception:  # noqa: BLE001 — audit best-effort
                conn.rollback()
            raise
    finally:
        conn.close()

    return {
        "run_id": run_id,
        "trade_date": canonical_date,
        "trigger": trigger,
        "rows_expected": len(rows),
        "rows_loaded": len(rows),
        "mapping_coverage": "100%",
        "identities_created": identities_created,
        "raw_artifact": artifact,
        "status": "SUCCESS",
    }


# ---------------------------------------------------------------------------
# Reconciliation: legacy daily_bars <-> canonical market_prices_daily
# ---------------------------------------------------------------------------
def reconcile_date(
    legacy_path: Path, core_path: Path, date_str: str
) -> dict:
    """Full legacy<->canonical reconciliation for one trade date.

    Compares row count, mapping coverage, and per-row OHLC/volume/turnover.
    Returns a JSON-safe report; raises on invalid date.
    """
    try:
        canonical_date = normalize_date(date_str)
    except DateNormalizationError as exc:
        raise IngestValidationError(f"invalid date: {date_str!r}") from exc
    raw_date = canonical_date.replace("-", "")

    legacy: dict[str, dict] = {}
    lconn = connect_ro(legacy_path)
    try:
        for ts, o, h, l, c, vol, amt in lconn.execute(
            "SELECT ts_code, open, high, low, close, vol, amount"
            " FROM daily_bars WHERE trade_date=?",
            (raw_date,),
        ):
            legacy[ts] = {
                "open": o, "high": h, "low": l, "close": c,
                "volume": vol, "turnover": amt,
            }
    finally:
        lconn.close()

    canonical: dict[str, dict] = {}
    cconn = connect_ro(core_path)
    try:
        for ts, o, h, l, c, vol, amt in cconn.execute(
            "SELECT ii.identifier, m.open, m.high, m.low, m.close, m.volume,"
            " m.turnover"
            " FROM market_prices_daily m"
            " JOIN instrument_identifiers ii"
            "   ON ii.instrument_id = m.instrument_id"
            " WHERE m.trade_date=?"
            "   AND ii.provider='TUSHARE'"
            "   AND ii.identifier_type='EXCHANGE_SYMBOL'"
            "   AND ii.valid_to IS NULL"
            " ORDER BY ii.identifier",
            (canonical_date,),
        ):
            canonical[ts] = {
                "open": o, "high": h, "low": l, "close": c,
                "volume": vol, "turnover": amt,
            }
    finally:
        cconn.close()

    mismatches: list[dict] = []
    for ts in sorted(set(legacy) | set(canonical)):
        if ts not in legacy:
            mismatches.append({"ts_code": ts, "issue": "in canonical only"})
            continue
        if ts not in canonical:
            mismatches.append({"ts_code": ts, "issue": "missing in canonical"})
            continue
        for field in ("open", "high", "low", "close", "volume", "turnover"):
            lv, cv = legacy[ts][field], canonical[ts][field]
            if lv != cv:
                mismatches.append(
                    {"ts_code": ts, "field": field,
                     "legacy": lv, "canonical": cv}
                )

    return {
        "trade_date": canonical_date,
        "legacy_rows": len(legacy),
        "canonical_rows": len(canonical),
        "mapping_coverage": "100%" if set(legacy) == set(canonical) else "INCOMPLETE",
        "mismatch_count": len(mismatches),
        "mismatches": mismatches[:20],
        "pass": len(mismatches) == 0 and len(legacy) == len(canonical),
    }


# ---------------------------------------------------------------------------
# Discovery + CLI
# ---------------------------------------------------------------------------
def discover_latest_missing_date(
    legacy_path: Path, core_path: Path
) -> str | None:
    """Newest legacy trade date not yet present in canonical market_prices_daily."""
    lconn = connect_ro(legacy_path)
    try:
        legacy_dates = {
            normalize_date(r[0])
            for r in lconn.execute("SELECT DISTINCT trade_date FROM daily_bars")
        }
    finally:
        lconn.close()
    cconn = connect_ro(core_path)
    try:
        core_dates = {
            r[0]
            for r in cconn.execute("SELECT DISTINCT trade_date FROM market_prices_daily")
        }
    finally:
        cconn.close()
    missing = legacy_dates - core_dates
    return max(missing) if missing else None


def _write_report(report: dict, report_dir: Path) -> Path | None:
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"ingest_{report.get('trade_date', 'report')}.json"
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return path


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="R3-A canonical incremental daily-bar ingestion"
    )
    p.add_argument("--date", help="trade date YYYY-MM-DD (or YYYYMMDD)")
    p.add_argument(
        "--latest", action="store_true",
        help="auto-ingest the newest legacy date missing from core",
    )
    p.add_argument(
        "--reconcile", metavar="DATE",
        help="reconcile legacy <-> canonical for DATE (no writes)",
    )
    p.add_argument("--legacy", type=Path, default=DEFAULT_LEGACY)
    p.add_argument("--core", type=Path, default=DEFAULT_CORE)
    p.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    p.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    p.add_argument(
        "--stock-basic", type=Path, default=None,
        help="stock_basic CSV for identity expansion of new instruments "
        "(default: registered stock_basic FILE artifact in core.db)",
    )
    p.add_argument("--trigger", default="MANUAL",
                   choices=["MANUAL", "SCHEDULED", "BACKFILL"])
    p.add_argument(
        "--allow-production", action="store_true",
        help="authorize writing production core.db (R3-A)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.reconcile:
        report = reconcile_date(args.legacy, args.core, args.reconcile)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["pass"] else 1

    if not args.date and not args.latest:
        print("error: --date or --latest required", file=sys.stderr)
        return 2

    if args.latest:
        date_str = discover_latest_missing_date(args.legacy, args.core)
        if date_str is None:
            print("nothing to ingest: core is up to date with legacy")
            return 0
    else:
        date_str = args.date

    try:
        report = ingest_date(
            args.core, args.legacy, date_str,
            trigger=args.trigger,
            raw_dir=args.raw_dir,
            allow_production=args.allow_production,
            stock_basic_path=args.stock_basic,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"❌ ingest failed: {exc}", file=sys.stderr)
        return 1

    path = _write_report(report, args.report_dir)
    report["report_file"] = str(path) if path else None
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
