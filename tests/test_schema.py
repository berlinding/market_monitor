"""T1 Schema execution tests — run C0001/P0001 in temp DBs and verify structure."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import migrate  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS = PROJECT_ROOT / "docs" / "database" / "sql" / "migrations"

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


def apply_sql_to_tempdb(sql_text: str) -> str:
    """Create a temp DB, run SQL (no BEGIN/COMMIT inside), return path."""
    tmp = tempfile.TemporaryDirectory()
    db = Path(tmp.name) / "t.db"
    conn = sqlite3_connect(str(db))
    conn.executescript(sql_text)
    conn.close()
    return db  # note: tempdir must outlive usage; caller keeps ref


import sqlite3  # noqa: E402


def sqlite3_connect(path):
    return sqlite3.connect(path, isolation_level=None)


def table_names(conn) -> set:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    return {r[0] for r in rows}


class TestCoreSchemaExecution(unittest.TestCase):
    def test_c0001_creates_17_core_tables(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "core.db"
            rows = migrate.run_migrations(
                db_path,
                MIGRATIONS / "core",
                "C",
                db_label="core",
                no_backup_gate=True,
            )
            self.assertEqual(rows[0]["status"], "APPLIED")
            conn = migrate.connect_db(db_path)
            try:
                names = table_names(conn)
                self.assertTrue(CORE_TABLES <= names,
                                msg=f"missing: {CORE_TABLES - names}")
            finally:
                conn.close()

    def test_p0001_creates_private_tables(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "private.db"
            rows = migrate.run_migrations(
                db_path,
                MIGRATIONS / "private",
                "P",
                db_label="private",
                no_backup_gate=True,
            )
            self.assertEqual(rows[0]["status"], "APPLIED")
            conn = migrate.connect_db(db_path)
            try:
                names = table_names(conn)
                self.assertTrue(PRIVATE_TABLES <= names,
                                msg=f"missing: {PRIVATE_TABLES - names}")
            finally:
                conn.close()

    def test_foreign_key_check_empty_both(self):
        with tempfile.TemporaryDirectory() as td:
            core_db = Path(td) / "core.db"
            priv_db = Path(td) / "private.db"
            migrate.run_migrations(core_db, MIGRATIONS / "core", "C",
                                   db_label="core", no_backup_gate=True)
            migrate.run_migrations(priv_db, MIGRATIONS / "private", "P",
                                   db_label="private", no_backup_gate=True)
            for db in (core_db, priv_db):
                conn = migrate.connect_db(db)
                try:
                    bad = conn.execute("PRAGMA foreign_key_check").fetchall()
                    self.assertEqual(bad, [], msg=f"FK violations in {db}")
                finally:
                    conn.close()

    def test_indexes_present(self):
        with tempfile.TemporaryDirectory() as td:
            core_db = Path(td) / "core.db"
            migrate.run_migrations(core_db, MIGRATIONS / "core", "C",
                                   db_label="core", no_backup_gate=True)
            conn = migrate.connect_db(core_db)
            try:
                idx = {
                    r[0]
                    for r in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='index'"
                    )
                }
                for required in (
                    "ux_entity_identifiers_current",
                    "ux_instrument_identifiers_current",
                    "ux_dataset_sources_active_primary",
                    "ux_raw_artifacts_run_hash",
                    "ux_event_evidence_primary",
                    "idx_mpd_instrument_date",
                    "idx_event_evidence_hash",
                ):
                    self.assertIn(required, idx)
            finally:
                conn.close()


def normalize_schema(conn) -> dict:
    """Extract normalized table structure (columns + indexes + FKs)."""
    out = {}
    tables = sorted(
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    )
    for t in tables:
        cols = conn.execute(f"PRAGMA table_info('{t}')").fetchall()
        cols_norm = [
            (c[1], c[2], c[3], c[4], c[5]) for c in cols  # name,type,notnull,dflt,pk
        ]
        idx_rows = conn.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type='index' AND tbl_name=? ORDER BY name",
            (t,),
        ).fetchall()
        idx_norm = [(r[0], r[1]) for r in idx_rows]
        out[t] = {"columns": cols_norm, "indexes": idx_norm}
    return out


class TestCanonicalVsSnapshot(unittest.TestCase):
    """DB-D029: migration files are canonical; consolidated files are snapshots.
    Both must produce the same executable schema (not byte-identical files)."""

    def test_core_canonical_matches_snapshot_schema(self):
        with tempfile.TemporaryDirectory() as td:
            canon_db = Path(td) / "canon.db"
            snap_db = Path(td) / "snap.db"
            migrate.run_migrations(canon_db, MIGRATIONS / "core", "C",
                                   db_label="core", no_backup_gate=True)
            snapshot_sql = (
                PROJECT_ROOT / "docs" / "database" / "sql" / "core_schema_v1.sql"
            ).read_text(encoding="utf-8")
            migrate.apply_migration(
                migrate.connect_db(snap_db, create=True),
                "SNAP_C0001",
                snapshot_sql,
                "snapshot equivalence",
            )
            c1 = migrate.connect_db(canon_db)
            c2 = migrate.connect_db(snap_db)
            try:
                self.assertEqual(normalize_schema(c1), normalize_schema(c2))
            finally:
                c1.close()
                c2.close()

    def test_private_canonical_matches_snapshot_schema(self):
        with tempfile.TemporaryDirectory() as td:
            canon_db = Path(td) / "canon.db"
            snap_db = Path(td) / "snap.db"
            migrate.run_migrations(canon_db, MIGRATIONS / "private", "P",
                                   db_label="private", no_backup_gate=True)
            snapshot_sql = (
                PROJECT_ROOT / "docs" / "database" / "sql"
                / "private_schema_v1.sql"
            ).read_text(encoding="utf-8")
            migrate.apply_migration(
                migrate.connect_db(snap_db, create=True),
                "SNAP_P0001",
                snapshot_sql,
                "snapshot equivalence",
            )
            c1 = migrate.connect_db(canon_db)
            c2 = migrate.connect_db(snap_db)
            try:
                self.assertEqual(normalize_schema(c1), normalize_schema(c2))
            finally:
                c1.close()
                c2.close()


if __name__ == "__main__":
    unittest.main()
