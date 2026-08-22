"""T5 Synthetic legacy migration fixture tests — live -> frozen snapshot ->
mutate live -> migrate frozen. Dynamic baseline, mapping gate, backup
logical validation, timestamp conversion."""

import sqlite3
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import migrate  # noqa: E402
from scripts import legacy_migration_utils as lmu  # noqa: E402
from scripts.timestamp_utils import (  # noqa: E402
    TimestampResolutionError,
    convert_legacy_naive_to_utc,
    utc_now_iso,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS = PROJECT_ROOT / "docs" / "database" / "sql" / "migrations"


def now() -> str:
    return "2026-08-22T04:00:00Z"


# ---------------------------------------------------------------------------
# Fixture data (deterministic, offline)
# ---------------------------------------------------------------------------
TS_CODES = ["600519.SH", "000001.SZ", "830001.BJ", "600000.SH"]
DATES = ["20260814", "20260817", "20260820"]


def make_bars(ts_codes=None, dates=None):
    ts_codes = ts_codes or TS_CODES
    dates = dates or DATES
    bars = []
    for td in dates:
        for ts in ts_codes:
            bars.append(
                (ts, td, 10.0, 11.0, 9.5, 10.5, 10.0, 0.5, 5.0, 1000.0, 10000.0)
            )
    return bars


def make_fetch_log(dates=None):
    dates = dates or DATES
    # deterministic naive local timestamps (legacy semantics: NOT UTC)
    raw = {
        "20260814": "2026-08-16T23:39:29",
        "20260817": "2026-08-17T18:32:14",
        "20260820": "2026-08-20T21:55:33",
    }
    return [(td, raw.get(td, f"2026-08-16T09:30:00"), len(TS_CODES)) for td in dates]


class TestTimestampUtils(unittest.TestCase):
    def test_utc_now_iso_format(self):
        s = utc_now_iso()
        self.assertRegex(s, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        self.assertNotIn("+00:00", s)

    def test_convert_shanghai(self):
        """T-TIMEZONE-01"""
        self.assertEqual(
            convert_legacy_naive_to_utc("2026-08-16T23:39:29", "Asia/Shanghai"),
            "2026-08-16T15:39:29Z",
        )

    def test_unresolved_raises(self):
        """T-TIMEZONE-02: unknown timezone must abort, never guess."""
        with self.assertRaises(TimestampResolutionError):
            convert_legacy_naive_to_utc("2026-08-16T23:39:29", None)
        with self.assertRaises(TimestampResolutionError):
            convert_legacy_naive_to_utc("2026-08-16T23:39:29", "Mars/Olympus")


class TestDynamicBaseline(unittest.TestCase):
    def test_baseline_uses_actual_rows_not_documented(self):
        """T-BASELINE-01: documented baseline says 5 rows, fixture has 6.
        Authoritative baseline comes from the frozen snapshot and must use the
        actual 6 (not the documented reference) without failing."""
        with tempfile.TemporaryDirectory() as td:
            live = Path(td) / "live.db"
            bars = make_bars(["600519.SH", "000001.SZ"], ["20260814", "20260817", "20260820"])
            fetch = [("20260814", "2026-08-16T09:30:00", 2),
                     ("20260817", "2026-08-17T09:30:00", 2),
                     ("20260820", "2026-08-20T09:30:00", 2)]
            lmu.create_legacy_fixture(live, bars, fetch)

            health = lmu.inspect_live_source_health(live)
            self.assertTrue(health["ok"])
            snapshot = Path(td) / "snapshot.db"
            backup_hash = lmu.create_frozen_snapshot(live, snapshot)
            manifest = lmu.capture_snapshot_baseline(snapshot)
            self.assertEqual(manifest["row_count"], 6)  # actual, not 5
            self.assertEqual(manifest["distinct_ts_code"], 2)
            self.assertEqual(manifest["distinct_trade_dates"], 3)
            # documented baseline of 5 is merely a reference; no hard abort
            documented = 5
            self.assertNotEqual(documented, manifest["row_count"])
            # manifest contains all required fields
            for key in ("captured_at", "snapshot_path", "snapshot_sha256", "file_size",
                        "row_count", "trade_date_distribution", "distinct_ts_code",
                        "fetch_log_count", "latest_fetch_time_raw", "ts_code_suffixes",
                        "aggregates"):
                self.assertIn(key, manifest)
            self.assertEqual(backup_hash, manifest["snapshot_sha256"])


class TestSnapshotBaselineAuthority(unittest.TestCase):
    def _make_live(self, td: str, ts_codes=None) -> Path:
        live = Path(td) / "live.db"
        lmu.create_legacy_fixture(
            live,
            make_bars(ts_codes or TS_CODES),
            make_fetch_log(),
        )
        return live

    def _snapshot_and_manifest(self, td: str, live: Path):
        snapshot = Path(td) / "snapshot.db"
        backup_hash = lmu.create_frozen_snapshot(live, snapshot)
        manifest = lmu.capture_snapshot_baseline(snapshot)
        return snapshot, backup_hash, manifest

    def test_snapshot_baseline_authoritative_after_live_mutation(self):
        """T-SNAPSHOT-BASELINE-01: 6-row fixture; mutate live (rows + fetch_log)
        after snapshot; migration still driven by the snapshot manifest (6 rows)."""
        with tempfile.TemporaryDirectory() as td:
            live = self._make_live(td, ts_codes=TS_CODES[:2])  # 2 ts * 3 dates = 6 rows
            health = lmu.inspect_live_source_health(live)
            self.assertTrue(health["ok"])
            snapshot, backup_hash, manifest = self._snapshot_and_manifest(td, live)
            self.assertEqual(manifest["row_count"], 6)

            # mutate live after snapshot: add 1 bar row + 1 fetch_log row
            conn = sqlite3.connect(str(live))
            conn.execute(
                "INSERT INTO daily_bars VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                ("999999.SH", "20260820", 1, 1, 1, 1, 1, 0, 0, 1, 1),
            )
            conn.execute(
                "INSERT INTO fetch_log VALUES ('20260821', '2026-08-21T09:30:00', 1, '')",
            )
            conn.commit()
            conn.close()

            mapping = lmu.build_ts_code_mapping(
                snapshot, lmu.build_stock_basic_fixture(TS_CODES[:2])
            )
            count, val = TestFrozenSnapshotSource()._run_canonical_pipeline(
                td, snapshot, manifest, mapping, backup_hash
            )
            self.assertEqual(count, 6)  # snapshot manifest governs, not live's 7
            self.assertTrue(all(val.values()), msg=val)

    def test_snapshot_hash_is_snapshot_bytes(self):
        """T-SNAPSHOT-HASH-01: manifest snapshot_sha256 == sha256(snapshot file
        bytes), not the live source file hash."""
        with tempfile.TemporaryDirectory() as td:
            live = self._make_live(td)
            snapshot, backup_hash, manifest = self._snapshot_and_manifest(td, live)
            import hashlib
            self.assertEqual(
                manifest["snapshot_sha256"],
                hashlib.sha256(snapshot.read_bytes()).hexdigest(),
            )
            self.assertEqual(backup_hash, manifest["snapshot_sha256"])
            # must not accidentally be the live file hash
            live_hash = hashlib.sha256(live.read_bytes()).hexdigest()
            self.assertNotEqual(manifest["snapshot_sha256"], live_hash)

    def test_validate_snapshot_does_not_open_live(self):
        """validate_snapshot must never reopen the live DB (H1)."""
        with tempfile.TemporaryDirectory() as td:
            live = self._make_live(td)
            snapshot, _, manifest = self._snapshot_and_manifest(td, live)
            # delete the live DB entirely; validation must still pass on snapshot
            live.unlink()
            validation = lmu.validate_snapshot(snapshot, manifest)
            self.assertTrue(all(validation.values()), msg=validation)


class TestStockBasicInputValidation(unittest.TestCase):
    def _snapshot_for(self, td: str, bars=None, fetch=None) -> Path:
        live = Path(td) / "live.db"
        lmu.create_legacy_fixture(live, bars or make_bars(), fetch or make_fetch_log())
        snapshot = Path(td) / "snapshot.db"
        lmu.create_frozen_snapshot(live, snapshot)
        return snapshot

    def test_duplicate_stock_basic_ts_code_fails_fast(self):
        """T-MAPPING-DUPLICATE-01"""
        with tempfile.TemporaryDirectory() as td:
            snapshot = self._snapshot_for(td)
            duplicate = [
                {"ts_code": "600519.SH", "name": "Co A", "list_date": "2001-01-01"},
                {"ts_code": "600519.SH", "name": "Co B", "list_date": "2002-01-01"},
            ]
            with self.assertRaises(lmu.MappingGateError) as ctx:
                lmu.build_ts_code_mapping(snapshot, duplicate)
            self.assertIn("duplicate", str(ctx.exception).lower())
            self.assertIn("600519.SH", str(ctx.exception))

    def test_missing_required_field_fails_fast(self):
        """T-MAPPING-MISSING-FIELD-01: missing ts_code / name / list_date abort."""
        with tempfile.TemporaryDirectory() as td:
            snapshot = self._snapshot_for(td)
            rows = lmu.build_stock_basic_fixture(TS_CODES)
            for field in ("ts_code", "name", "list_date"):
                bad = [dict(r) for r in rows]
                del bad[0][field]
                with self.assertRaises(lmu.MappingGateError) as ctx:
                    lmu.build_ts_code_mapping(snapshot, bad)
                self.assertIn(field, str(ctx.exception))

    def test_empty_ts_code_fails_fast(self):
        with tempfile.TemporaryDirectory() as td:
            snapshot = self._snapshot_for(td)
            bad = lmu.build_stock_basic_fixture(TS_CODES)
            bad[0]["ts_code"] = "   "
            with self.assertRaises(lmu.MappingGateError):
                lmu.build_ts_code_mapping(snapshot, bad)

    def test_validate_stock_basic_input_standalone(self):
        dup = [
            {"ts_code": "000001.SZ", "name": "A", "list_date": "1991-01-01"},
            {"ts_code": "000001.SZ", "name": "B", "list_date": "1991-01-01"},
        ]
        with self.assertRaises(lmu.MappingGateError):
            lmu.validate_stock_basic_input(dup)
        lmu.validate_stock_basic_input(
            [{"ts_code": "000001.SZ", "name": "A", "list_date": "1991-01-01"}]
        )

    def test_invalid_list_date_calendar_fails_fast(self):
        """T-STOCK-BASIC-DATE-INVALID-01: 20260230 is not a real date."""
        with tempfile.TemporaryDirectory() as td:
            snapshot = self._snapshot_for(td)
            bad = lmu.build_stock_basic_fixture(TS_CODES)
            bad[0]["list_date"] = "20260230"
            with self.assertRaises(lmu.MappingGateError) as ctx:
                lmu.build_ts_code_mapping(snapshot, bad)
            self.assertIn("list_date", str(ctx.exception))
            self.assertIn("600519.SH", str(ctx.exception))

    def test_invalid_list_date_alpha_fails_fast(self):
        """T-STOCK-BASIC-DATE-INVALID-02: 'abc' is not a date."""
        with tempfile.TemporaryDirectory() as td:
            snapshot = self._snapshot_for(td)
            bad = lmu.build_stock_basic_fixture(TS_CODES)
            bad[0]["list_date"] = "abc"
            with self.assertRaises(lmu.MappingGateError):
                lmu.build_ts_code_mapping(snapshot, bad)

    def test_valid_compact_list_date_accepted(self):
        """Provider-raw compact list_date (e.g. 19910403) is accepted and
        normalized to canonical YYYY-MM-DD in the mapping."""
        with tempfile.TemporaryDirectory() as td:
            snapshot = self._snapshot_for(td)
            basic = lmu.build_stock_basic_fixture(TS_CODES)
            basic[0]["list_date"] = "19910403"
            mapping = lmu.build_ts_code_mapping(snapshot, basic)
            self.assertEqual(mapping[TS_CODES[0]]["list_date"], "1991-04-03")
            self.assertEqual(
                mapping[TS_CODES[0]]["provider_list_date_raw"], "19910403"
            )


class TestCanonicalDateContract(unittest.TestCase):
    """R1C Phase 1.2: canonical date fields are strictly YYYY-MM-DD."""

    def _run_pipeline(self, td, snapshot, manifest, mapping, backup_hash):
        return TestFrozenSnapshotSource()._run_canonical_pipeline(
            td, snapshot, manifest, mapping, backup_hash
        )

    def test_canonical_trade_date(self):
        """T-CANONICAL-TRADE-DATE-01: legacy 20260814 -> canonical 2026-08-14."""
        with tempfile.TemporaryDirectory() as td:
            live = Path(td) / "live.db"
            lmu.create_legacy_fixture(live, make_bars(), make_fetch_log())
            snapshot = Path(td) / "snapshot.db"
            backup_hash = lmu.create_frozen_snapshot(live, snapshot)
            manifest = lmu.capture_snapshot_baseline(snapshot)
            mapping = lmu.build_ts_code_mapping(
                snapshot, lmu.build_stock_basic_fixture(TS_CODES)
            )
            _, val = self._run_pipeline(td, snapshot, manifest, mapping, backup_hash)
            self.assertTrue(all(val.values()), msg=val)

            core_db = Path(td) / "core.db"
            conn = migrate.connect_db(core_db)
            try:
                dates = {
                    r[0]
                    for r in conn.execute(
                        "SELECT DISTINCT trade_date FROM market_prices_daily"
                    )
                }
            finally:
                conn.close()
            self.assertEqual(
                dates, {"2026-08-14", "2026-08-17", "2026-08-20"}
            )
            self.assertNotIn("20260814", dates)  # raw compact must not leak

    def test_canonical_list_date(self):
        """T-CANONICAL-LIST-DATE-01: provider 20010827 -> canonical 2001-08-27
        in mapping, instruments.listing_date and identifiers.valid_from."""
        with tempfile.TemporaryDirectory() as td:
            live = Path(td) / "live.db"
            lmu.create_legacy_fixture(live, make_bars(), make_fetch_log())
            snapshot = Path(td) / "snapshot.db"
            backup_hash = lmu.create_frozen_snapshot(live, snapshot)
            manifest = lmu.capture_snapshot_baseline(snapshot)

            stock_basic = lmu.build_stock_basic_fixture(TS_CODES)
            # provider-raw compact list_date (Tushare style)
            stock_basic[0]["list_date"] = "20010827"
            mapping = lmu.build_ts_code_mapping(snapshot, stock_basic)
            self.assertEqual(mapping[TS_CODES[0]]["list_date"], "2001-08-27")
            self.assertEqual(
                mapping[TS_CODES[0]]["provider_list_date_raw"], "20010827"
            )

            _, val = self._run_pipeline(td, snapshot, manifest, mapping, backup_hash)
            self.assertTrue(all(val.values()), msg=val)

            core_db = Path(td) / "core.db"
            conn = migrate.connect_db(core_db)
            try:
                listing = conn.execute(
                    "SELECT listing_date FROM instruments WHERE primary_symbol=?",
                    (TS_CODES[0].split(".")[0],),
                ).fetchone()[0]
                valid_from = conn.execute(
                    "SELECT valid_from FROM instrument_identifiers "
                    "WHERE identifier=?",
                    (TS_CODES[0],),
                ).fetchone()[0]
            finally:
                conn.close()
            self.assertEqual(listing, "2001-08-27")
            self.assertEqual(valid_from, "2001-08-27")

    def test_manifest_json_serializable(self):
        """T-MANIFEST-JSON-01: json.dumps(snapshot manifest) must succeed."""
        import json
        with tempfile.TemporaryDirectory() as td:
            live = Path(td) / "live.db"
            lmu.create_legacy_fixture(live, make_bars(), make_fetch_log())
            snapshot = Path(td) / "snapshot.db"
            lmu.create_frozen_snapshot(live, snapshot)
            manifest = lmu.capture_snapshot_baseline(snapshot)
            s = json.dumps(manifest, sort_keys=True)
            self.assertIsInstance(s, str)
            self.assertIn("aggregates", s)


class TestFrozenSnapshotSource(unittest.TestCase):
    def _run_canonical_pipeline(self, td, snapshot, manifest, mapping,
                                backup_hash, timezone_name="Asia/Shanghai"):
        """M2..M7 mini pipeline into a temp canonical core.db (fixture level).
        The frozen snapshot is passed in (already created & validated);
        this method must NOT re-backup the live DB (P0-3)."""
        core_db = Path(td) / "core.db"
        migrate.run_migrations(core_db, MIGRATIONS / "core", "C",
                               db_label="core", no_backup_gate=True)
        conn = migrate.connect_db(core_db)
        try:
            # M2: source/dataset bootstrap
            cur = conn.execute(
                "INSERT INTO data_sources(source_code, source_name, source_type,"
                " status, created_at, updated_at)"
                " VALUES ('TUSHARE', 'Tushare', 'MARKET_DATA', 'ACTIVE', ?, ?)",
                (now(), now()),
            )
            source_id = cur.lastrowid
            cur = conn.execute(
                "INSERT INTO datasets(dataset_code, dataset_name, dataset_type,"
                " granularity, write_mode, status, created_at, updated_at)"
                " VALUES ('CN_EQUITY_DAILY', 'A股日线', 'PRICE_DAILY', 'DAILY',"
                " 'UPSERT', 'ACTIVE', ?, ?)",
                (now(), now()),
            )
            dataset_id = cur.lastrowid
            conn.execute(
                "INSERT INTO dataset_sources(dataset_id, source_id, role,"
                " priority_rank, is_active, created_at, updated_at)"
                " VALUES (?, ?, 'PRIMARY', 1, 1, ?, ?)",
                (dataset_id, source_id, now(), now()),
            )
            # M2B: register frozen snapshot as raw_artifact (hash already computed)
            cur = conn.execute(
                "INSERT INTO raw_artifacts(artifact_uid, dataset_id, source_id,"
                " artifact_type, local_path_or_reference, content_hash, retrieved_at,"
                " created_at) VALUES (?, ?, ?, 'DB_SNAPSHOT', ?, ?, ?, ?)",
                ("a1b2c3d4-1111-4222-8333-444455556666", dataset_id, source_id,
                 str(snapshot), backup_hash, now(), now()),
            )
            artifact_id = cur.lastrowid
            # M3/M4: entities + instruments + identifiers from stock_basic fixture
            stock_basic = lmu.build_stock_basic_fixture(sorted(mapping.keys()))
            entity_ids = {}
            for row in stock_basic:
                cur = conn.execute(
                    "INSERT INTO entities(entity_uid, canonical_name, entity_type,"
                    " created_at, updated_at) VALUES (?, ?, 'COMPANY', ?, ?)",
                    (str(uuid.uuid4()), row["name"], now(), now()),
                )
                entity_ids[row["ts_code"]] = cur.lastrowid
            for ts, m in mapping.items():
                cur = conn.execute(
                    "INSERT INTO instruments(instrument_uid, entity_id, instrument_type,"
                    " primary_symbol, exchange_code, currency_code, country_code,"
                    " status, listing_date, created_at, updated_at)"
                    " VALUES (?, ?, 'EQUITY', ?, ?, 'CNY', 'CN', 'ACTIVE', ?, ?, ?)",
                    (str(uuid.uuid4()), entity_ids[ts], m["symbol"], m["mic"],
                     m["list_date"], now(), now()),
                )
                m["instrument_id"] = cur.lastrowid
                conn.execute(
                    "INSERT INTO instrument_identifiers(instrument_id, provider,"
                    " identifier_type, identifier, valid_from, is_primary, created_at)"
                    " VALUES (?, 'TUSHARE', 'EXCHANGE_SYMBOL', ?, ?, 1, ?)",
                    (m["instrument_id"], ts, m["list_date"], now()),
                )
            # M5: ingest run backfill from fetch_log (in frozen snapshot)
            runs = lmu.backfill_runs(snapshot, timezone_name)
            run_by_date = {}
            for trade_date, info in runs.items():
                cur = conn.execute(
                    "INSERT INTO ingest_runs(dataset_id, source_id, trigger_type,"
                    " started_at, finished_at, status, rows_loaded, notes)"
                    " VALUES (?, ?, 'BACKFILL', ?, ?, 'SUCCESS', ?, ?)",
                    (dataset_id, source_id, info["started_at_utc"], now(),
                     info["rows"], info["legacy_fetched_at_raw"]),
                )
                run_by_date[trade_date] = cur.lastrowid
            # M6: copy bars FROM FROZEN SNAPSHOT only
            count = lmu.migrate_bars_from_snapshot(
                snapshot, mapping, conn, source_id=source_id,
                run_by_date=run_by_date, raw_artifact_id=artifact_id,
            )
            # M7: validation
            validation = lmu.validate_migration(conn, snapshot, manifest, mapping)
            conn.commit()
            return count, validation
        finally:
            conn.close()

    def test_live_mutation_does_not_pollute_frozen_migration(self):
        """T-FROZEN-SOURCE-01"""
        with tempfile.TemporaryDirectory() as td:
            live = Path(td) / "live.db"
            lmu.create_legacy_fixture(live, make_bars(), make_fetch_log())
            health = lmu.inspect_live_source_health(live)
            self.assertTrue(health["ok"])
            snapshot = Path(td) / "snapshot.db"
            backup_hash = lmu.create_frozen_snapshot(live, snapshot)
            manifest = lmu.capture_snapshot_baseline(snapshot)
            validation = lmu.validate_snapshot(snapshot, manifest)
            self.assertTrue(all(validation.values()), msg=validation)

            # MUTATE live after the frozen snapshot was taken
            live_conn = sqlite3.connect(str(live))
            live_conn.execute(
                "INSERT INTO daily_bars VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                ("999999.SH", "20260820", 1, 1, 1, 1, 1, 0, 0, 1, 1),
            )
            live_conn.commit()
            live_conn.close()

            # canonical pipeline reads ONLY the frozen snapshot
            mapping = lmu.build_ts_code_mapping(
                snapshot, lmu.build_stock_basic_fixture(TS_CODES)
            )
            count, val = self._run_canonical_pipeline(
                td, snapshot, manifest, mapping, backup_hash
            )

            # migration input = frozen snapshot row count (12 bars), NOT the
            # post-backup live mutation (13 bars)
            self.assertEqual(count, manifest["row_count"])
            self.assertTrue(all(val.values()), msg=val)

    def test_backup_logical_validation_type_b(self):
        """T-BACKUP-01: logical backup bytes may differ from source; validation
        is based on integrity/schema/rows/aggregates, not byte equality.
        H1: the live DB is never reopened for validation."""
        with tempfile.TemporaryDirectory() as td:
            live = Path(td) / "live.db"
            lmu.create_legacy_fixture(live, make_bars(), make_fetch_log())
            health = lmu.inspect_live_source_health(live)
            self.assertTrue(health["ok"])
            snapshot = Path(td) / "snapshot.db"
            backup_hash = lmu.create_frozen_snapshot(live, snapshot)
            manifest = lmu.capture_snapshot_baseline(snapshot)
            # snapshot hash and live hash may differ — that is ALLOWED
            live_hash = health["live_source_file_hash_observed"]
            self.assertEqual(len(backup_hash), 64)
            self.assertEqual(len(live_hash), 64)
            validation = lmu.validate_snapshot(snapshot, manifest)
            self.assertTrue(all(validation.values()), msg=validation)
            # note: we do NOT assert hashes are equal; byte identity is not required

    def test_mapping_gate_missing_ts_code_aborts(self):
        """T-MAPPING-01: 100% mapping required; missing -> abort."""
        with tempfile.TemporaryDirectory() as td:
            live = Path(td) / "live.db"
            lmu.create_legacy_fixture(live, make_bars(), make_fetch_log())
            snapshot = Path(td) / "snapshot.db"
            lmu.create_frozen_snapshot(live, snapshot)
            incomplete_basic = lmu.build_stock_basic_fixture(TS_CODES[:-1])
            with self.assertRaises(lmu.MappingGateError):
                lmu.build_ts_code_mapping(snapshot, incomplete_basic)

    def test_mapping_gate_unknown_suffix_aborts(self):
        """Unknown suffix .XX -> abort before bar copy."""
        with tempfile.TemporaryDirectory() as td:
            live = Path(td) / "live.db"
            bars = make_bars(["600519.SH", "12345.XX"], ["20260814"])
            fetch = [("20260814", "2026-08-16T09:30:00", 2)]
            lmu.create_legacy_fixture(live, bars, fetch)
            snapshot = Path(td) / "snapshot.db"
            lmu.create_frozen_snapshot(live, snapshot)
            basic = lmu.build_stock_basic_fixture(["600519.SH", "12345.XX"])
            with self.assertRaises(lmu.MappingGateError):
                lmu.build_ts_code_mapping(snapshot, basic)

    def test_backfill_runs_requires_timezone(self):
        with tempfile.TemporaryDirectory() as td:
            live = Path(td) / "live.db"
            lmu.create_legacy_fixture(live, make_bars(), make_fetch_log())
            snapshot = Path(td) / "snapshot.db"
            lmu.create_frozen_snapshot(live, snapshot)
            with self.assertRaises(TimestampResolutionError):
                lmu.backfill_runs(snapshot, None)
            runs = lmu.backfill_runs(snapshot, "Asia/Shanghai")
            self.assertEqual(len(runs), 3)
            for info in runs.values():
                self.assertRegex(
                    info["started_at_utc"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"
                )
                self.assertIn("legacy_fetched_at_raw", info)


if __name__ == "__main__":
    unittest.main()
