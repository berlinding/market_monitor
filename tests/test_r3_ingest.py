"""T10 R3-A canonical incremental ingestion tests (temp DBs only).

Covers:
  T-R3A-LOAD-01       new date ingest: expected == loaded, values correct
  T-R3A-IDEMPOTENT-01 re-run same date: row count unchanged, no duplicates
  T-R3A-UNKNOWN-01    unknown ts_code -> MappingGateError, zero rows written
  T-R3A-BADDATE-01    date with no legacy data -> NoDataForDateError
  T-R3A-PARTIAL-01    NULL required field -> IngestValidationError, no write
  T-R3A-MAPPING-01    incomplete mapping -> MappingGateError, no partial bars
  T-R3A-STABLEUID-01  instrument_uid unchanged after ingest (no new identity)
  T-R3A-LINEAGE-01    raw_artifact hash == file sha256; run/artifact/source linked
  T-R3A-RECONCILE-01  legacy <-> canonical reconciliation: 0 mismatch
  T-R3A-GUARD-01      production core path without authorization -> error
  T-R3A-DISCOVER-01   discover_latest_missing_date finds the newest new day

NEVER touches data/runtime/core.db or data/private/private.db.
"""

import json
import sqlite3
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import migrate  # noqa: E402
from scripts import ingest_daily as ing  # noqa: E402
from scripts import legacy_migration_utils as lmu  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS = PROJECT_ROOT / "docs" / "database" / "sql" / "migrations"

TS_CODES = ["600519.SH", "000001.SZ", "830001.BJ", "600000.SH"]
OLD_DATE = "2026-08-24"   # already in core baseline
NEW_DATE = "2026-08-25"   # the new trading day to ingest
NEW_DATE_RAW = "20260825"


def now() -> str:
    return "2026-08-25T00:00:00Z"


def _bars(ts_codes=None, dates=None):
    ts_codes = ts_codes or TS_CODES
    dates = dates or [NEW_DATE_RAW]
    bars = []
    for td in dates:
        for i, ts in enumerate(ts_codes, start=1):
            bars.append(
                (ts, td,
                 10.0 + i, 11.0 + i, 9.5 + i, 10.5 + i,  # o/h/l/c
                 10.0 + i, 0.5, 5.0,  # pre_close/change/pct_chg
                 1000.0 * i, 10000.0 * i)  # vol/amount
            )
    return bars


def build_legacy(td: str, bars=None, fetch_log=None) -> Path:
    db = Path(td) / "market.db"
    if db.exists():
        return db  # idempotent: reuse for re-run scenarios
    bars = bars if bars is not None else _bars()
    fetch_log = fetch_log or [(NEW_DATE_RAW, "2026-08-25T18:31:49", len(TS_CODES))]
    lmu.create_legacy_fixture(db, bars, fetch_log)
    return db


def seed_core_metadata(conn, ts_codes=None):
    """Mirror phase2 m2/m3: source/dataset/dataset_sources + instruments + ids.

    Idempotent: safe to call on an already-seeded core (re-runs reuse rows).
    """
    ts_codes = ts_codes or TS_CODES
    row = conn.execute(
        "SELECT source_id FROM data_sources WHERE source_code='TUSHARE'"
    ).fetchone()
    if row is None:
        cur = conn.execute(
            "INSERT INTO data_sources"
            "(source_code, source_name, source_type, status, notes, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?)",
            ("TUSHARE", "Tushare", "MARKET_DATA", "ACTIVE",
             "A-share market data provider", now(), now()),
        )
        source_id = cur.lastrowid
        cur = conn.execute(
            "INSERT INTO datasets"
            "(dataset_code, dataset_name, dataset_type, granularity, target_table,"
            " write_mode, status, notes, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            ("CN_EQUITY_DAILY", "China equity daily bars", "PRICE_DAILY", "DAILY",
             "market_prices_daily", "UPSERT", "ACTIVE",
             "Canonical daily price history (R1B)", now(), now()),
        )
        dataset_id = cur.lastrowid
        conn.execute(
            "INSERT INTO dataset_sources"
            "(dataset_id, source_id, role, priority_rank, is_active, notes,"
            " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (dataset_id, source_id, "PRIMARY", 1, 1, "Primary source", now(), now()),
        )
    else:
        source_id = row[0]
        dataset_id = conn.execute(
            "SELECT dataset_id FROM datasets WHERE dataset_code='CN_EQUITY_DAILY'"
        ).fetchone()[0]

    existing = set(
        r[0] for r in conn.execute(
            "SELECT identifier FROM instrument_identifiers"
            " WHERE provider='TUSHARE' AND identifier_type='EXCHANGE_SYMBOL'"
        )
    )
    for ts in ts_codes:
        if ts in existing:
            continue
        entity_uid = str(uuid.uuid4())
        cur = conn.execute(
            "INSERT INTO entities"
            "(entity_uid, canonical_name, entity_type, country_code, status,"
            " created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
            (entity_uid, f"Co {ts}", "COMPANY", "CN", "ACTIVE", now(), now()),
        )
        entity_id = cur.lastrowid
        instrument_uid = str(uuid.uuid4())
        symbol, suffix = ts.split(".")
        cur = conn.execute(
            "INSERT INTO instruments"
            "(instrument_uid, entity_id, instrument_type, primary_symbol,"
            " exchange_code, currency_code, country_code, status, listing_date,"
            " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (instrument_uid, entity_id, "EQUITY", symbol,
             lmu.SUFFIX_MIC[suffix], "CNY", "CN", "ACTIVE", "2010-01-01",
             now(), now()),
        )
        instrument_id = cur.lastrowid
        conn.execute(
            "INSERT INTO instrument_identifiers"
            "(instrument_id, provider, identifier_type, identifier, valid_from,"
            " is_primary, created_at) VALUES (?,?,?,?,?,?,?)",
            (instrument_id, "TUSHARE", "EXCHANGE_SYMBOL", ts, "2010-01-01", 1, now()),
        )
        conn.execute(
            "INSERT INTO instrument_identifiers"
            "(instrument_id, provider, identifier_type, identifier, valid_from,"
            " is_primary, created_at) VALUES (?,?,?,?,?,?,?)",
            (instrument_id, "STANDARD", "TICKER", symbol, "2010-01-01", 0, now()),
        )
    conn.commit()
    return source_id, dataset_id


def build_core(td: str, ts_codes=None) -> sqlite3.Connection:
    db = Path(td) / "core.db"
    migrate.run_migrations(db, MIGRATIONS / "core", "C", db_label="core",
                           no_backup_gate=True)
    conn = migrate.connect_db(db)
    seed_core_metadata(conn, ts_codes)
    return conn


def _run_ingest(td: str, date_str=NEW_DATE, trigger="MANUAL", legacy=None):
    legacy = legacy or build_legacy(td)
    core = build_core(td)
    core.close()
    raw_dir = Path(td) / "raw"
    return ing.ingest_date(
        Path(td) / "core.db", legacy, date_str,
        trigger=trigger, raw_dir=raw_dir,
    )


class TestR3AIngestLoad(unittest.TestCase):
    def test_load_new_date(self):
        """T-R3A-LOAD-01"""
        with tempfile.TemporaryDirectory() as td:
            rep = _run_ingest(td)
            self.assertEqual(rep["status"], "SUCCESS")
            self.assertEqual(rep["rows_expected"], len(TS_CODES))
            self.assertEqual(rep["rows_loaded"], len(TS_CODES))
            self.assertEqual(rep["mapping_coverage"], "100%")
            self.assertEqual(rep["trade_date"], NEW_DATE)

            conn = sqlite3.connect(f"file:{Path(td) / 'core.db'}?mode=ro", uri=True)
            try:
                rows = conn.execute(
                    "SELECT instrument_id, trade_date, open, close, volume,"
                    " turnover, volume_unit, turnover_unit, currency_code,"
                    " adjustment_type, source_id, ingest_run_id, raw_artifact_id"
                    " FROM market_prices_daily WHERE trade_date=? ORDER BY instrument_id",
                    (NEW_DATE,),
                ).fetchall()
                self.assertEqual(len(rows), len(TS_CODES))
                for r in rows:
                    self.assertEqual(r[1], NEW_DATE)
                    self.assertEqual(r[6], "LOTS")
                    self.assertEqual(r[7], "THOUSAND_CNY")
                    self.assertEqual(r[8], "CNY")
                    self.assertEqual(r[9], "RAW")
                    self.assertIsNotNone(r[10])  # source_id
                    self.assertIsNotNone(r[11])  # ingest_run_id
                    self.assertIsNotNone(r[12])  # raw_artifact_id
                run = conn.execute(
                    "SELECT status, rows_expected, rows_loaded FROM ingest_runs"
                    " WHERE run_id=?", (rep["run_id"],),
                ).fetchone()
                self.assertEqual(run[0], "SUCCESS")
                self.assertEqual(run[1], len(TS_CODES))
                self.assertEqual(run[2], len(TS_CODES))
            finally:
                conn.close()


class TestR3AIdempotent(unittest.TestCase):
    def test_rerun_same_date_no_duplicates(self):
        """T-R3A-IDEMPOTENT-01"""
        with tempfile.TemporaryDirectory() as td:
            _run_ingest(td)
            first = sqlite3.connect(
                f"file:{Path(td) / 'core.db'}?mode=ro", uri=True
            ).execute(
                "SELECT COUNT(*) FROM market_prices_daily WHERE trade_date=?",
                (NEW_DATE,),
            ).fetchone()[0]
            _run_ingest(td)  # re-run same date
            second = sqlite3.connect(
                f"file:{Path(td) / 'core.db'}?mode=ro", uri=True
            ).execute(
                "SELECT COUNT(*) FROM market_prices_daily WHERE trade_date=?",
                (NEW_DATE,),
            ).fetchone()[0]
            self.assertEqual(second, first)
            self.assertEqual(second, len(TS_CODES))


class TestR3AFailures(unittest.TestCase):
    def test_unknown_instrument(self):
        """T-R3A-UNKNOWN-01: ts_code not in identifiers -> abort, zero rows."""
        with tempfile.TemporaryDirectory() as td:
            legacy = build_legacy(td)
            core = build_core(td)
            core.close()
            # inject an extra legacy bar for an unknown ts_code
            conn = sqlite3.connect(str(legacy))
            conn.execute(
                "INSERT INTO daily_bars VALUES"
                " ('999999.SZ','20260825',1,2,1,1.5,1,0.5,50.0,100.0,200.0)"
            )
            conn.commit()
            conn.close()
            with self.assertRaises(lmu.MappingGateError):
                ing.ingest_date(
                    Path(td) / "core.db", legacy, NEW_DATE,
                    raw_dir=Path(td) / "raw",
                )
            count = sqlite3.connect(
                f"file:{Path(td) / 'core.db'}?mode=ro", uri=True
            ).execute(
                "SELECT COUNT(*) FROM market_prices_daily WHERE trade_date=?",
                (NEW_DATE,),
            ).fetchone()[0]
            self.assertEqual(count, 0, "no partial bars on mapping failure")

    def test_bad_date_no_legacy_data(self):
        """T-R3A-BADDATE-01"""
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ing.NoDataForDateError):
                _run_ingest(td, date_str="2026-08-26")

    def test_null_required_field(self):
        """T-R3A-PARTIAL-01: NULL close -> validation error, no write."""
        with tempfile.TemporaryDirectory() as td:
            bars = list(_bars())
            bars[0] = (bars[0][0], bars[0][1], 10.0, 11.0, 9.5, None,
                       10.0, 0.5, 5.0, 1000.0, 10000.0)
            legacy = build_legacy(td, bars=bars)
            with self.assertRaises(ing.IngestValidationError):
                _run_ingest(td, legacy=legacy)
            count = sqlite3.connect(
                f"file:{Path(td) / 'core.db'}?mode=ro", uri=True
            ).execute(
                "SELECT COUNT(*) FROM market_prices_daily"
            ).fetchone()[0]
            self.assertEqual(count, 0)

    def test_incomplete_mapping(self):
        """T-R3A-MAPPING-01: core lacks one instrument -> abort, no bars."""
        with tempfile.TemporaryDirectory() as td:
            legacy = build_legacy(td)
            core = build_core(td, ts_codes=TS_CODES[:3])  # one missing
            core.close()
            with self.assertRaises(lmu.MappingGateError):
                ing.ingest_date(
                    Path(td) / "core.db", legacy, NEW_DATE,
                    raw_dir=Path(td) / "raw",
                )
            count = sqlite3.connect(
                f"file:{Path(td) / 'core.db'}?mode=ro", uri=True
            ).execute(
                "SELECT COUNT(*) FROM market_prices_daily WHERE trade_date=?",
                (NEW_DATE,),
            ).fetchone()[0]
            self.assertEqual(count, 0)


class TestR3AStableUid(unittest.TestCase):
    def test_no_new_identity(self):
        """T-R3A-STABLEUID-01: uid set unchanged, no new instruments."""
        with tempfile.TemporaryDirectory() as td:
            core = build_core(td)
            before = set(
                r[0] for r in core.execute(
                    "SELECT instrument_uid FROM instruments ORDER BY instrument_uid"
                )
            )
            before_ids = set(
                r[0] for r in core.execute(
                    "SELECT identifier_id FROM instrument_identifiers"
                )
            )
            core.close()
            _run_ingest(td)
            conn = sqlite3.connect(f"file:{Path(td) / 'core.db'}?mode=ro", uri=True)
            try:
                after = set(
                    r[0] for r in conn.execute(
                        "SELECT instrument_uid FROM instruments ORDER BY instrument_uid"
                    )
                )
                after_ids = set(
                    r[0] for r in conn.execute(
                        "SELECT identifier_id FROM instrument_identifiers"
                    )
                )
            finally:
                conn.close()
            self.assertEqual(after, before, "instrument_uid must not change")
            self.assertEqual(after_ids, before_ids, "no new identifiers")


class TestR3ALineage(unittest.TestCase):
    def test_raw_artifact_lineage(self):
        """T-R3A-LINEAGE-01: artifact hash == file sha256; links present."""
        with tempfile.TemporaryDirectory() as td:
            rep = _run_ingest(td)
            artifact_path = Path(rep["raw_artifact"]["path"])
            self.assertTrue(artifact_path.exists())
            self.assertEqual(
                rep["raw_artifact"]["content_hash"],
                ing.sha256_file(artifact_path),
            )
            conn = sqlite3.connect(f"file:{Path(td) / 'core.db'}?mode=ro", uri=True)
            try:
                art = conn.execute(
                    "SELECT artifact_uid, run_id, artifact_type, content_hash,"
                    " dataset_id, source_id FROM raw_artifacts"
                ).fetchone()
                self.assertIsNotNone(art)
                self.assertEqual(art[2], "FILE")
                self.assertEqual(art[3], rep["raw_artifact"]["content_hash"])
                self.assertEqual(art[4], 1)  # CN_EQUITY_DAILY
                self.assertEqual(art[5], 1)  # TUSHARE
                # every bar links to run + artifact + source
                orphan = conn.execute(
                    "SELECT COUNT(*) FROM market_prices_daily"
                    " WHERE ingest_run_id IS NULL OR raw_artifact_id IS NULL"
                    " OR source_id IS NULL"
                ).fetchone()[0]
                self.assertEqual(orphan, 0)
                # dataset_sources PRIMARY lineage exists
                ds = conn.execute(
                    "SELECT COUNT(*) FROM dataset_sources"
                    " WHERE role='PRIMARY' AND is_active=1"
                ).fetchone()[0]
                self.assertEqual(ds, 1)
            finally:
                conn.close()


class TestR3AReconcile(unittest.TestCase):
    def test_reconcile_zero_mismatch(self):
        """T-R3A-RECONCILE-01"""
        with tempfile.TemporaryDirectory() as td:
            legacy = build_legacy(td)
            _run_ingest(td, legacy=legacy)
            rep = ing.reconcile_date(
                legacy, Path(td) / "core.db", NEW_DATE
            )
            self.assertTrue(rep["pass"])
            self.assertEqual(rep["mismatch_count"], 0)
            self.assertEqual(rep["legacy_rows"], len(TS_CODES))
            self.assertEqual(rep["canonical_rows"], len(TS_CODES))
            self.assertEqual(rep["mapping_coverage"], "100%")


class TestR3AProductionGuard(unittest.TestCase):
    def test_production_path_requires_authorization(self):
        """T-R3A-GUARD-01"""
        with tempfile.TemporaryDirectory() as td:
            legacy = build_legacy(td)
            with self.assertRaises(migrate.ProductionWriteNotAuthorizedError):
                ing.ingest_date(
                    migrate.PRODUCTION_PATHS["core"], legacy, NEW_DATE,
                    raw_dir=Path(td) / "raw",
                    allow_production=False,
                )


class TestR3ADiscover(unittest.TestCase):
    def test_discover_latest_missing_date(self):
        """T-R3A-DISCOVER-01"""
        with tempfile.TemporaryDirectory() as td:
            legacy = build_legacy(td, bars=_bars(dates=[NEW_DATE_RAW]))
            core = build_core(td)
            core.close()
            found = ing.discover_latest_missing_date(
                legacy, Path(td) / "core.db"
            )
            self.assertEqual(found, NEW_DATE)
            # after ingest -> nothing missing
            _run_ingest(td, legacy=legacy)
            found2 = ing.discover_latest_missing_date(
                legacy, Path(td) / "core.db"
            )
            self.assertIsNone(found2)


# ---------------------------------------------------------------------------
# Identity expansion tests (new listings / resumed instruments)
# ---------------------------------------------------------------------------
STOCK_BASIC_HEADER = (
    "ts_code,symbol,name,area,industry,market,exchange,curr_type,"
    "list_status,list_date,delist_date"
)


def _write_stock_basic(td: str, rows: list[str]) -> Path:
    p = Path(td) / "stock_basic.csv"
    p.write_text(
        STOCK_BASIC_HEADER + "\n" + "\n".join(rows) + "\n",
        encoding="utf-8",
    )
    return p


class TestR3AIdentityExpansion(unittest.TestCase):
    def test_new_listing_identity_created_and_ingested(self):
        """T-R3A-SYNC-01: new ts_code resolved from stock_basic."""
        with tempfile.TemporaryDirectory() as td:
            legacy = build_legacy(td)  # 4 known ts_codes
            core = build_core(td, ts_codes=TS_CODES[:3])  # 3 known
            core.close()
            # the 4th ts_code exists in legacy but not in core identity;
            # add it to a stock_basic CSV (mirrors registered artifact)
            sb = _write_stock_basic(td, [
                "600519.SH,600519,贵州茅台,贵州,酿酒,主板,SSE,CNY,L,20010827,",
                "000001.SZ,000001,平安银行,广东,银行,主板,SZSE,CNY,L,19910403,",
                "830001.BJ,830001,德源药业,江苏,医药,北交所,BSE,CNY,L,20210714,",
                "600000.SH,600000,浦发银行,上海,银行,主板,SSE,CNY,L,19991110,",
            ])
            rep = ing.ingest_date(
                Path(td) / "core.db", legacy, NEW_DATE,
                raw_dir=Path(td) / "raw",
                stock_basic_path=sb,
            )
            self.assertEqual(rep["status"], "SUCCESS")
            self.assertEqual(rep["rows_loaded"], len(TS_CODES))
            self.assertEqual(len(rep["identities_created"]), 1)
            self.assertEqual(
                rep["identities_created"][0]["ts_code"], "600000.SH"
            )
            # new instrument + identifiers exist in core
            conn = sqlite3.connect(
                f"file:{Path(td) / 'core.db'}?mode=ro", uri=True
            )
            try:
                inst = conn.execute(
                    "SELECT i.instrument_id, i.primary_symbol, i.exchange_code"
                    " FROM instruments i"
                    " JOIN instrument_identifiers ii ON ii.instrument_id=i.instrument_id"
                    " WHERE ii.identifier='600000.SH'"
                ).fetchone()
                self.assertIsNotNone(inst)
                self.assertEqual(inst[1], "600000")
                self.assertEqual(inst[2], "XSHG")
                n_identifiers = conn.execute(
                    "SELECT COUNT(*) FROM instrument_identifiers"
                    " WHERE instrument_id=?", (inst[0],),
                ).fetchone()[0]
                self.assertEqual(n_identifiers, 2)  # EXCHANGE_SYMBOL + TICKER
            finally:
                conn.close()

    def test_unresolvable_instrument_fails(self):
        """T-R3A-SYNC-02: ts_code unknown to core AND stock_basic -> fail."""
        with tempfile.TemporaryDirectory() as td:
            legacy = build_legacy(td)
            core = build_core(td, ts_codes=TS_CODES[:3])
            core.close()
            sb = _write_stock_basic(td, [  # does NOT contain 600000.SH
                "600519.SH,600519,贵州茅台,贵州,酿酒,主板,SSE,CNY,L,20010827,",
                "000001.SZ,000001,平安银行,广东,银行,主板,SZSE,CNY,L,19910403,",
                "830001.BJ,830001,德源药业,江苏,医药,北交所,BSE,CNY,L,20210714,",
            ])
            with self.assertRaises(lmu.MappingGateError):
                ing.ingest_date(
                    Path(td) / "core.db", legacy, NEW_DATE,
                    raw_dir=Path(td) / "raw",
                    stock_basic_path=sb,
                )
            # nothing written
            conn = sqlite3.connect(
                f"file:{Path(td) / 'core.db'}?mode=ro", uri=True
            )
            try:
                self.assertEqual(
                    conn.execute(
                        "SELECT COUNT(*) FROM market_prices_daily WHERE trade_date=?",
                        (NEW_DATE,),
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    conn.execute("SELECT COUNT(*) FROM instruments").fetchone()[0],
                    3,
                )
            finally:
                conn.close()

    def test_no_stock_basic_artifact_fails(self):
        """T-R3A-SYNC-03: missing ts_code and no stock_basic source -> fail."""
        with tempfile.TemporaryDirectory() as td:
            legacy = build_legacy(td)
            core = build_core(td, ts_codes=TS_CODES[:3])
            core.close()
            # no raw_artifacts registered, no --stock-basic passed
            with self.assertRaises(lmu.MappingGateError):
                ing.ingest_date(
                    Path(td) / "core.db", legacy, NEW_DATE,
                    raw_dir=Path(td) / "raw",
                )

    def test_existing_uid_unchanged_after_expansion(self):
        """T-R3A-SYNC-04: existing UIDs preserved; only new ones added."""
        with tempfile.TemporaryDirectory() as td:
            legacy = build_legacy(td)
            core = build_core(td, ts_codes=TS_CODES[:3])
            core_uids_before = set(
                r[0] for r in core.execute(
                    "SELECT instrument_uid FROM instruments ORDER BY instrument_uid"
                )
            )
            core.close()
            sb = _write_stock_basic(td, [
                "600519.SH,600519,贵州茅台,贵州,酿酒,主板,SSE,CNY,L,20010827,",
                "000001.SZ,000001,平安银行,广东,银行,主板,SZSE,CNY,L,19910403,",
                "830001.BJ,830001,德源药业,江苏,医药,北交所,BSE,CNY,L,20210714,",
                "600000.SH,600000,浦发银行,上海,银行,主板,SSE,CNY,L,19991110,",
            ])
            rep = ing.ingest_date(
                Path(td) / "core.db", legacy, NEW_DATE,
                raw_dir=Path(td) / "raw",
                stock_basic_path=sb,
            )
            conn = sqlite3.connect(
                f"file:{Path(td) / 'core.db'}?mode=ro", uri=True
            )
            try:
                core_uids_after = set(
                    r[0] for r in conn.execute(
                        "SELECT instrument_uid FROM instruments ORDER BY instrument_uid"
                    )
                )
            finally:
                conn.close()
            self.assertTrue(core_uids_before <= core_uids_after)
            self.assertEqual(
                len(core_uids_after - core_uids_before), 1,
                "exactly one NEW uid added",
            )
            self.assertEqual(len(rep["identities_created"]), 1)


if __name__ == "__main__":
    sys.exit(unittest.main())
