#!/usr/bin/env python3
"""
production_init.py — R2 Part A: Canonical Identity Activation (stdlib only)

Berlin-authorized (2026-08-25, R2 §5-§13): create production canonical DBs:
  data/runtime/core.db    (C0001 + real identity + bars)
  data/private/private.db (P0001 schema only, NO real portfolio data)

Semantics:
  * initialize-if-absent / validate-if-present (§30).
  * Initialization is traceable: live preflight -> NEW frozen snapshot ->
    manifest -> real Tushare stock_basic -> 100% mapping -> production
    core.db via the same R1-validated migration semantics (§7/§8).
  * Never copies staging core.db; never reuses staging UUIDs.
  * migrate.PRODUCTION_WRITES_ENABLED is set True ONLY here (explicit Berlin
    authorization, recorded in the report). migrate.py default stays False.
  * dual-write OFF; legacy downloader untouched; NO real portfolio written.

Usage:
  python3 scripts/production_init.py            # initialize (or validate if present)
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts import migrate  # noqa: E402
from scripts import phase2_staging_rehearsal as ph2  # noqa: E402
from scripts.legacy_migration_utils import (  # noqa: E402
    build_ts_code_mapping,
    MappingGateError,
)

CORE_TABLES = {
    "entities", "entity_identifiers", "instruments", "instrument_identifiers",
    "data_sources", "datasets", "dataset_sources", "ingest_runs",
    "raw_artifacts", "data_gaps", "market_prices_daily", "events",
    "event_entities", "event_instruments", "event_evidence", "event_analysis",
    "schema_migrations",
}
PRIVATE_TABLES = {
    "accounts", "positions", "watchlists", "watchlist_items",
    "investment_theses", "event_thesis_analysis", "alerts", "schema_migrations",
}

LEGACY_TZ = "Asia/Shanghai"  # CONFIRMED (DB-D035)


def utc_now_iso() -> str:
    from scripts.timestamp_utils import utc_now_iso as _u
    return _u()


# ---------------------------------------------------------------------------
# Validation helpers (validate-if-present, §30)
# ---------------------------------------------------------------------------
def _table_names(db: Path) -> set[str]:
    conn = sqlite3.connect(f"file:{db.resolve()}?mode=ro", uri=True)
    try:
        return {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    finally:
        conn.close()


def _schema_migrations(db: Path) -> dict[str, str]:
    conn = sqlite3.connect(f"file:{db.resolve()}?mode=ro", uri=True)
    try:
        return dict(
            conn.execute("SELECT migration_id, checksum FROM schema_migrations")
        )
    finally:
        conn.close()


def _fk_check_empty(db: Path) -> bool:
    conn = sqlite3.connect(f"file:{db.resolve()}?mode=ro", uri=True)
    try:
        return len(conn.execute("PRAGMA foreign_key_check").fetchall()) == 0
    finally:
        conn.close()


def validate_production_core(db: Path) -> dict:
    """Prove existing production core.db is our legal canonical DB (no overwrite).

    In addition to schema/migration/FK checks, this RE-RUNS V1–V18 + full-row
    reconciliation against the recorded raw_artifact snapshot (§11 / §30),
    so validate-if-present is a real re-validation, not just a row count.
    """
    if not db.exists():
        return {"valid": False, "reason": "missing"}
    checks = {}
    tables = _table_names(db)
    checks["tables"] = sorted(tables)
    checks["table_count"] = len(tables)
    checks["table_set_ok"] = tables == CORE_TABLES
    applied = _schema_migrations(db)
    checks["schema_migrations"] = applied
    checks["c0001_applied"] = "C0001" in applied
    checks["fk_check_empty"] = _fk_check_empty(db)

    conn = sqlite3.connect(f"file:{db.resolve()}?mode=ro", uri=True)
    try:
        checks["row_counts"] = {
            "entities": conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0],
            "instruments": conn.execute("SELECT COUNT(*) FROM instruments").fetchone()[0],
            "identifiers": conn.execute(
                "SELECT COUNT(*) FROM instrument_identifiers"
            ).fetchone()[0],
            "bars": conn.execute(
                "SELECT COUNT(*) FROM market_prices_daily"
            ).fetchone()[0],
            "ingest_runs": conn.execute("SELECT COUNT(*) FROM ingest_runs").fetchone()[0],
        }
        # recover snapshot artifact + manifest from raw_artifacts (provenance)
        art = conn.execute(
            "SELECT artifact_id, local_path_or_reference, metadata"
            " FROM raw_artifacts WHERE artifact_type='DB_SNAPSHOT'"
            " ORDER BY artifact_id LIMIT 1"
        ).fetchone()
        if art:
            artifact_id, snap_path, meta_json = art
            checks["legacy_artifact_id"] = artifact_id
            checks["snapshot_path"] = snap_path
            try:
                meta = json.loads(meta_json or "{}")
                checks["manifest"] = meta.get("manifest")
            except json.JSONDecodeError:
                checks["manifest"] = None
        # recover source_id + mapping (ts_code -> instrument_id)
        src = conn.execute(
            "SELECT source_id FROM data_sources WHERE source_code='TUSHARE'"
        ).fetchone()
        checks["source_id"] = src[0] if src else None
        mapping = {}
        for ts_code, inst_id in conn.execute(
            "SELECT ii.identifier, i.instrument_id FROM instrument_identifiers ii"
            " JOIN instruments i ON i.instrument_id = ii.instrument_id"
            " WHERE ii.provider='TUSHARE' AND ii.identifier_type='EXCHANGE_SYMBOL'"
        ):
            mapping[ts_code] = {"instrument_id": inst_id}
        checks["mapping_recovered"] = len(mapping)
    finally:
        conn.close()

    checks["valid"] = bool(
        checks["table_set_ok"]
        and checks["c0001_applied"]
        and checks["fk_check_empty"]
        and checks["row_counts"]["bars"] > 0
        and checks["row_counts"]["instruments"] > 0
        and checks["legacy_artifact_id"]
        and checks["manifest"]
    )

    # re-run V1–V18 + full-row reconciliation on the EXISTING production DB
    if checks["valid"] and Path(checks["snapshot_path"]).exists():
        try:
            m7 = ph2.m7_validate(
                db,
                Path(checks["snapshot_path"]),
                checks["manifest"],
                mapping,
                checks["source_id"],
                run_by_date={},  # unused by m7_validate
                legacy_artifact_id=checks["legacy_artifact_id"],
            )
            checks["v1_v18"] = {
                vid: ("PASS" if v["pass"] else f"FAIL: {v['detail']}")
                for vid, v in m7["v_results"].items()
            }
            checks["reconciliation"] = m7["reconciliation"]
            checks["v1_v18_all_pass"] = all(v["pass"] for v in m7["v_results"].values())
            _mismatch_fields = (
                "ohlc_mismatches", "volume_mismatches", "turnover_mismatches",
                "date_mismatches", "mapping_mismatches",
            )
            checks["reconciliation_ok"] = all(
                m7["reconciliation"][f] == 0 for f in _mismatch_fields
            )
            checks["valid"] = bool(
                checks["valid"] and checks["v1_v18_all_pass"] and checks["reconciliation_ok"]
            )
        except Exception as exc:  # noqa: BLE001
            checks["v1_v18_error"] = str(exc)
            checks["valid"] = False
    else:
        checks["v1_v18"] = None
        checks["reconciliation"] = None
        if checks["valid"]:
            checks["valid"] = False
            checks["reason"] = "snapshot artifact missing/unavailable for re-validation"
    return checks


def validate_production_private(db: Path) -> dict:
    if not db.exists():
        return {"valid": False, "reason": "missing"}
    checks = {}
    tables = _table_names(db)
    checks["tables"] = sorted(tables)
    checks["table_count"] = len(tables)
    checks["table_set_ok"] = tables == PRIVATE_TABLES
    applied = _schema_migrations(db)
    checks["schema_migrations"] = applied
    checks["p0001_applied"] = "P0001" in applied
    checks["fk_check_empty"] = _fk_check_empty(db)
    conn = sqlite3.connect(f"file:{db.resolve()}?mode=ro", uri=True)
    try:
        checks["row_counts"] = {
            "accounts": conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0],
            "positions": conn.execute("SELECT COUNT(*) FROM positions").fetchone()[0],
            "watchlists": conn.execute("SELECT COUNT(*) FROM watchlists").fetchone()[0],
            "watchlist_items": conn.execute(
                "SELECT COUNT(*) FROM watchlist_items"
            ).fetchone()[0],
        }
    finally:
        conn.close()
    checks["valid"] = bool(
        checks["table_set_ok"]
        and checks["p0001_applied"]
        and checks["fk_check_empty"]
    )
    return checks


# ---------------------------------------------------------------------------
# Production initialization (§7-§11)
# ---------------------------------------------------------------------------
def initialize_production() -> dict:
    run_id = utc_now_iso().replace("-", "").replace(":", "")
    started_at = utc_now_iso()
    warnings: list[str] = []

    # explicit authorization: this script is the ONLY production writer (§5)
    migrate.PRODUCTION_WRITES_ENABLED = True

    core_db = ph2.PRODUCTION_PATHS["core"]
    private_db = ph2.PRODUCTION_PATHS["private"]

    # ---- M0 live preflight (read-only) ----
    m0 = ph2.m0_live_preflight()
    print(f"[M0] live preflight ok={m0['health']['ok']}")
    if not m0["health"]["ok"]:
        raise RuntimeError(f"M0 failed: {m0['health']}")
    print(
        f"     rows={m0['info']['row_count']} dates={m0['info']['distinct_trade_dates']}"
        f" ts={m0['info']['distinct_ts_code']} hash={m0['health']['live_source_file_hash_observed'][:12]}…"
    )

    # ---- M1 NEW frozen snapshot (never reuse staging snapshot) ----
    m1 = ph2.m1_frozen_snapshot(run_id)
    print(f"[M1] new frozen snapshot -> {m1['snapshot_path']}")
    if not m1["pass"]:
        raise RuntimeError(f"M1 snapshot validation FAIL: {m1['validation']}")
    snapshot_path = Path(m1["snapshot_path"])
    print(
        f"     sha256={m1['snapshot_sha256'][:16]}… row_count={m1['manifest']['row_count']}"
    )

    # ---- M2 real stock_basic (rate-limit aware, coverage-driven) ----
    token = ph2.load_tushare_token()
    if not token:
        raise RuntimeError("TUSHARE_TOKEN not found (env or ~/API.txt)")
    m2 = ph2.m2_stock_basic(run_id, token, snapshot_path, m1["manifest"])
    print(
        f"[M2] stock_basic merged={m2['meta']['merged_row_count']}"
        f" unique={m2['meta']['unique_ts_code_count']}"
        f" sha256={m2['sha256'][:16]}…"
    )

    # ---- M3/M4 100% mapping gate ----
    m3m4 = ph2.m3_m4_mapping(snapshot_path, m2["rows"])
    if m3m4["mapping"] is None:
        raise RuntimeError(f"M3/M4 mapping gate FAIL: {m3m4['coverage']}")
    print(
        f"[M3/M4] mapping PASS: legacy={m1['manifest']['distinct_ts_code']}"
        f" mapped={len(m3m4['mapping'])}"
    )

    # ---- production core.db via R1-validated runner (C0001) ----
    core_rows = migrate.run_migrations(
        core_db, ph2.MIGRATIONS_DIR / "core", "C", db_label="core"
    )
    print(f"[core] migrations: {[r['status'] for r in core_rows]}")
    core_checksums = {r["migration_id"]: r["checksum"] for r in core_rows}
    core_status = {r["migration_id"]: r["status"] for r in core_rows}

    # ---- production private.db via runner (P0001, schema only) ----
    private_rows = migrate.run_migrations(
        private_db, ph2.MIGRATIONS_DIR / "private", "P", db_label="private"
    )
    print(f"[private] migrations: {[r['status'] for r in private_rows]}")
    private_checksums = {r["migration_id"]: r["checksum"] for r in private_rows}
    private_status = {r["migration_id"]: r["status"] for r in private_rows}

    # ---- schema verification ----
    core_checks = ph2.verify_staging_schema(
        core_db, expected_prefix="C", expected_table_count=17
    )
    private_checks = ph2.verify_staging_schema(
        private_db,
        expected_prefix="P",
        expected_table_count=8,
        expected_tables=PRIVATE_TABLES,
    )
    print(
        f"[schema] core tables={core_checks['table_count']} fk_empty="
        f"{core_checks['foreign_key_check_empty']} | private tables="
        f"{private_checks['table_count']} fk_empty={private_checks['foreign_key_check_empty']}"
    )
    if (
        not core_checks["foreign_key_check_empty"]
        or not private_checks["foreign_key_check_empty"]
        or core_checks["table_count"] != 17
        or private_checks["table_count"] != 8
    ):
        raise RuntimeError(f"production schema checks FAIL: {core_checks} {private_checks}")

    # ---- M2 metadata + M2B raw artifacts ----
    core_conn = sqlite3.connect(str(core_db))
    core_conn.execute("PRAGMA foreign_keys = ON;")
    try:
        meta = ph2.m2_metadata(core_conn)
        artifacts = ph2.m2b_raw_artifacts(
            core_conn, meta["dataset_id"], meta["source_id"], m1, m2
        )
        print(
            f"[M2/M2B] source_id={meta['source_id']} dataset_id={meta['dataset_id']}"
            f" legacy_artifact_id={artifacts['legacy_snapshot_artifact_id']}"
        )

        # ---- M3/M4 entities/instruments (stable UIDs, §9) ----
        entities = ph2.m3_entities_instruments(core_conn, m3m4["mapping"])
        print(
            f"[M3/M4] entities={entities['entities_created']}"
            f" instruments={entities['instruments_created']}"
            f" identifiers={entities['identifiers_created']}"
            f" 1:1={entities['one_to_one_ok']}"
        )
        if not entities["one_to_one_ok"]:
            raise RuntimeError("production 1:1 mapping check FAIL")

        # ---- M5 ingest runs ----
        m5 = ph2.m5_ingest_runs(
            core_conn, snapshot_path, m1["manifest"],
            meta["dataset_id"], meta["source_id"],
        )
        print(f"[M5] ingest_runs={m5['runs_created']} gate_ok={m5['gate_ok']}")
        if not m5["gate_ok"]:
            raise RuntimeError(f"M5 FAIL: missing={m5['missing_dates']}")

        # ---- M6 bars ----
        m6 = ph2.m6_migrate_bars(
            core_conn,
            snapshot_path,
            m1["manifest"],
            m3m4["mapping"],
            meta["source_id"],
            artifacts["legacy_snapshot_artifact_id"],
            m5["run_by_date"],
        )
        print(
            f"[M6] bars={m6['bars_inserted']} batches_ok={len(m6['successful_batches'])}"
            f" failed={len(m6['failed_batches'])}"
        )
        if not m6["gate_ok"]:
            raise RuntimeError(f"M6 FAIL: {m6['failed_batches']}")
    finally:
        core_conn.close()

    # ---- M7 validation V1-V18 + full-row reconciliation ----
    m7 = ph2.m7_validate(
        core_db,
        snapshot_path,
        m1["manifest"],
        m3m4["mapping"],
        meta["source_id"],
        m5["run_by_date"],
        artifacts["legacy_snapshot_artifact_id"],
    )
    print("[M7] V1-V18:")
    for vid in sorted(m7["v_results"]):
        v = m7["v_results"][vid]
        print(f"     {vid:<28} {'PASS' if v['pass'] else 'FAIL'}  {v['detail']}")
    print(
        f"     reconciliation: checked={m7['reconciliation']['rows_checked']}"
        f" ohlc={m7['reconciliation']['ohlc_mismatches']}"
        f" vol={m7['reconciliation']['volume_mismatches']}"
        f" turn={m7['reconciliation']['turnover_mismatches']}"
        f" date={m7['reconciliation']['date_mismatches']}"
        f" map={m7['reconciliation']['mapping_mismatches']}"
    )

    staging = {
        "staging_dir": str(core_db.parent),
        "core_db": str(core_db),
        "private_db": str(private_db),
        "core_migrations": core_status,
        "private_migrations": private_status,
        "core_checksums": core_checksums,
        "private_checksums": private_checksums,
        "core_checks": core_checks,
        "private_checks": private_checks,
        "metadata": meta,
        "artifacts": artifacts,
    }

    report = ph2.build_report(
        run_id, started_at, m0, m1, m2, m3m4, staging, meta, artifacts,
        entities, m5, m6, m7, warnings,
    )
    # production-specific additions
    report["initialization"] = {
        "production_core_created": True,
        "production_private_created": True,
        "production_writes_enabled": True,
        "production_writes_authorized_by": "Berlin 2026-08-25 R2 §5-§13",
        "dual_write_enabled": False,
        "legacy_retirement": False,
        "real_portfolio_written": False,
        "validate_mode": False,
    }

    # write report (gitignored, never committed)
    runtime_dir = core_db.parent
    runtime_dir.mkdir(parents=True, exist_ok=True)
    report_path = runtime_dir / f"r1_identity_activation_{run_id}.json"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"[report] {report_path}")
    print(f"== FINAL RESULT: {report['final_result']} ==")

    # live must be untouched
    after = ph2.sha256_bytes(ph2.LIVE_DB.read_bytes())
    before = m0["health"]["live_source_file_hash_observed"]
    print(
        f"live market.db sha256 before={before[:12]}… after={after[:12]}…"
        f" unchanged={before == after}"
    )
    if before != after:
        raise RuntimeError("live market.db changed during initialization!")

    return report


def main() -> int:
    core_db = ph2.PRODUCTION_PATHS["core"]
    private_db = ph2.PRODUCTION_PATHS["private"]

    # §6: if production DB exists, NEVER overwrite — validate instead (§30)
    if core_db.exists() or private_db.exists():
        print("production DB(s) already exist -> validate-if-present mode")
        core_v = validate_production_core(core_db)
        priv_v = validate_production_private(private_db)
        print(f"core validate:   valid={core_v.get('valid')} {core_v.get('reason', '')}")
        print(f"private validate: valid={priv_v.get('valid')} {priv_v.get('reason', '')}")
        if core_v.get("v1_v18"):
            fails = [k for k, v in core_v["v1_v18"].items() if v != "PASS"]
            print(f"core V1-V18: all_pass={core_v.get('v1_v18_all_pass')}"
                  f" fails={fails if fails else 'NONE'}")
            print(f"core reconciliation: {core_v.get('reconciliation')}")
        repro = ph2.get_git_reproducibility_state()
        result = {
            "mode": "VALIDATE",
            "git": repro,
            "core": {k: v for k, v in core_v.items() if k not in ("manifest",)},
            "private": {k: v for k, v in priv_v.items() if k != "row_counts"},
            "private_row_counts": priv_v.get("row_counts"),
        }
        result["final_result"] = (
            "PASS"
            if core_v.get("valid") and priv_v.get("valid") and not repro["git_dirty"]
            else "FAIL"
        )
        (core_db.parent / "production_validate.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        if result["final_result"] != "PASS":
            print("STOP: production DB validate failed or git tree dirty", file=sys.stderr)
            return 1
        print("== VALIDATED: production DB is legal canonical DB; no re-initialization ==")
        return 0

    # absent -> initialize
    report = initialize_production()
    if report["final_result"] != "PASS":
        print(f"initialization FAILED: {report.get('v1_v18_errors')}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
