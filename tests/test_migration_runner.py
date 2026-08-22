"""T3 Migration runner tests — plan/status no-write, atomicity, checksum,
transaction-control detection, production guard, backup gate."""

import io
import shutil
import sqlite3
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import migrate  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS = PROJECT_ROOT / "docs" / "database" / "sql" / "migrations"


def tmp_migrations_dir(td: str, prefix: str, files: dict[str, str]) -> Path:
    d = Path(td) / prefix
    d.mkdir(parents=True)
    for name, sql in files.items():
        (d / name).write_text(sql, encoding="utf-8")
    return d


class TestPlanNoWrite(unittest.TestCase):
    def test_plan_does_not_create_db(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "core.db"
            rows = migrate.run_migrations(
                db, MIGRATIONS / "core", "C", db_label="core", plan_only=True
            )
            self.assertFalse(db.exists(), "plan mode must not create the DB file")
            self.assertEqual(rows[0]["status"], "PENDING")
            self.assertEqual(rows[0]["note"], "DB_NOT_CREATED")
            # no tables were created anywhere
            self.assertEqual(list(Path(td).glob("*.db")), [])

    def test_plan_on_existing_db_shows_pending_applied(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "core.db"
            migrate.run_migrations(db, MIGRATIONS / "core", "C",
                                   db_label="core", no_backup_gate=True)
            before = db.read_bytes()
            rows = migrate.run_migrations(
                db, MIGRATIONS / "core", "C", db_label="core", plan_only=True
            )
            self.assertEqual(rows[0]["status"], "APPLIED")
            self.assertEqual(db.read_bytes(), before, "plan mode must not modify DB")


class TestStatusNoWrite(unittest.TestCase):
    def test_status_not_created_no_db_creation(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "core.db"
            buf = io.StringIO()
            with redirect_stdout(buf):
                migrate.show_status(db, "core", MIGRATIONS / "core", "C")
            self.assertIn("NOT_CREATED", buf.getvalue())
            self.assertFalse(db.exists(), "status must not create the DB file")


class TestApplyIdempotencyChecksum(unittest.TestCase):
    def test_apply_then_skip(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "core.db"
            r1 = migrate.run_migrations(db, MIGRATIONS / "core", "C",
                                        db_label="core", no_backup_gate=True)
            r2 = migrate.run_migrations(db, MIGRATIONS / "core", "C",
                                        db_label="core", no_backup_gate=True)
            self.assertEqual(r1[0]["status"], "APPLIED")
            self.assertEqual(r2[0]["status"], "SKIP")

    def test_checksum_mismatch_hard_error(self):
        with tempfile.TemporaryDirectory() as td:
            d = tmp_migrations_dir(
                td, "core",
                {"C0001_a.sql": "CREATE TABLE t_a(id INTEGER);"},
            )
            db = Path(td) / "core.db"
            migrate.run_migrations(db, d, "C", db_label="core",
                                   no_backup_gate=True)
            (d / "C0001_a.sql").write_text(
                "CREATE TABLE t_a(id INTEGER);\n-- tampered\n", encoding="utf-8"
            )
            with self.assertRaises(migrate.MigrationChecksumError):
                migrate.run_migrations(db, d, "C", db_label="core",
                                       no_backup_gate=True)


class TestTransactionAtomicity(unittest.TestCase):
    """T-RUNNER-ATOMIC-01/02/03 (DB-D034 contract)."""

    def test_atomic_01_invalid_sql_rolls_back_all(self):
        with tempfile.TemporaryDirectory() as td:
            d = tmp_migrations_dir(
                td, "core",
                {
                    "C0001_bad.sql": (
                        "CREATE TABLE test_a(id INTEGER);\n"
                        "CREATE TABLE test_b(id INTEGER);\n"
                        "THIS IS NOT VALID SQL;"
                    )
                },
            )
            db = Path(td) / "core.db"
            with self.assertRaises(sqlite3.Error):
                migrate.run_migrations(db, d, "C", db_label="core",
                                       no_backup_gate=True)
            conn = sqlite3.connect(str(db))
            try:
                tables = {
                    r[0]
                    for r in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                self.assertNotIn("test_a", tables)
                self.assertNotIn("test_b", tables)
                recs = conn.execute(
                    "SELECT COUNT(*) FROM schema_migrations"
                ).fetchone()[0]
                self.assertEqual(recs, 0, "no migration record after rollback")
            finally:
                conn.close()

    def test_atomic_02_record_insert_failure_rolls_back_ddl(self):
        with tempfile.TemporaryDirectory() as td:
            d = tmp_migrations_dir(
                td, "core",
                {"C0001_ok.sql": "CREATE TABLE test_x(id INTEGER);"},
            )
            db = Path(td) / "core.db"
            # Simulate a failure while writing the schema_migrations record:
            # make utc_now_iso() (called while building the INSERT) raise.
            with mock.patch(
                "scripts.migrate.utc_now_iso", side_effect=RuntimeError("record fail")
            ):
                with self.assertRaises(RuntimeError):
                    migrate.run_migrations(db, d, "C", db_label="core",
                                           no_backup_gate=True)
            conn = sqlite3.connect(str(db))
            try:
                tables = {
                    r[0]
                    for r in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                self.assertNotIn("test_x", tables,
                                 "DDL must roll back when record insert fails")
                recs = conn.execute(
                    "SELECT COUNT(*) FROM schema_migrations"
                ).fetchone()[0]
                self.assertEqual(recs, 0)
            finally:
                conn.close()

    def test_atomic_03_normal_migration_commits_ddl_and_record(self):
        with tempfile.TemporaryDirectory() as td:
            d = tmp_migrations_dir(
                td, "core",
                {"C0001_ok.sql": "CREATE TABLE test_y(id INTEGER);"},
            )
            db = Path(td) / "core.db"
            migrate.run_migrations(db, d, "C", db_label="core",
                                   no_backup_gate=True)
            conn = sqlite3.connect(str(db))
            try:
                tables = {
                    r[0]
                    for r in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                self.assertIn("test_y", tables)
                row = conn.execute(
                    "SELECT migration_id, checksum FROM schema_migrations"
                ).fetchone()
                self.assertEqual(row[0], "C0001")
                self.assertEqual(len(row[1]), 64)
            finally:
                conn.close()


class TestMigrationFilePrechecks(unittest.TestCase):
    def test_commit_in_migration_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            d = tmp_migrations_dir(
                td, "core",
                {"C0001_evil.sql": "CREATE TABLE t_a(id INTEGER);\nCOMMIT;"},
            )
            db = Path(td) / "core.db"
            with self.assertRaises(migrate.MigrationFileError):
                migrate.run_migrations(db, d, "C", db_label="core",
                                       no_backup_gate=True)

    def test_begin_in_migration_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            d = tmp_migrations_dir(
                td, "core",
                {"C0001_evil.sql": "BEGIN;\nCREATE TABLE t_a(id INTEGER);"},
            )
            db = Path(td) / "core.db"
            with self.assertRaises(migrate.MigrationFileError):
                migrate.run_migrations(db, d, "C", db_label="core",
                                       no_backup_gate=True)

    def test_comment_commit_not_false_positive(self):
        with tempfile.TemporaryDirectory() as td:
            d = tmp_migrations_dir(
                td, "core",
                {"C0001_ok.sql": (
                    "CREATE TABLE t_a(id INTEGER);\n"
                    "-- note: never COMMIT inside migration files\n"
                )},
            )
            db = Path(td) / "core.db"
            rows = migrate.run_migrations(db, d, "C", db_label="core",
                                          no_backup_gate=True)
            self.assertEqual(rows[0]["status"], "APPLIED")

    def test_invalid_filename_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            d = tmp_migrations_dir(td, "core", {"C0001.sql": "SELECT 1;"})
            db = Path(td) / "core.db"
            with self.assertRaises(migrate.MigrationFileError):
                migrate.run_migrations(db, d, "C", db_label="core",
                                       no_backup_gate=True)

    def test_noncontiguous_numbers_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            d = tmp_migrations_dir(
                td, "core",
                {"C0001_a.sql": "CREATE TABLE t_a(id INTEGER);",
                 "C0003_c.sql": "CREATE TABLE t_c(id INTEGER);"},
            )
            db = Path(td) / "core.db"
            with self.assertRaises(migrate.MigrationFileError):
                migrate.run_migrations(db, d, "C", db_label="core",
                                       no_backup_gate=True)


class TestProductionGuard(unittest.TestCase):
    def test_production_core_path_refused(self):
        with tempfile.TemporaryDirectory() as td:
            d = tmp_migrations_dir(
                td, "core", {"C0001_ok.sql": "CREATE TABLE t_a(id INTEGER);"}
            )
            prod_path = PROJECT_ROOT / "data" / "runtime" / "core.db"
            with self.assertRaises(migrate.ProductionWriteNotAuthorizedError):
                migrate.run_migrations(prod_path, d, "C", db_label="core")
            self.assertFalse(prod_path.exists(),
                             "production DB must not be created")

    def test_production_private_path_refused(self):
        with tempfile.TemporaryDirectory() as td:
            d = tmp_migrations_dir(
                td, "private", {"P0001_ok.sql": "CREATE TABLE t_a(id INTEGER);"}
            )
            prod_path = PROJECT_ROOT / "data" / "private" / "private.db"
            with self.assertRaises(migrate.ProductionWriteNotAuthorizedError):
                migrate.run_migrations(prod_path, d, "P", db_label="private")
            self.assertFalse(prod_path.exists())


class TestBackupGate(unittest.TestCase):
    def test_existing_db_without_backup_marker_refused(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "core.db"
            migrate.run_migrations(db, MIGRATIONS / "core", "C",
                                   db_label="core", no_backup_gate=True)
            with self.assertRaises(migrate.BackupGateError):
                migrate.run_migrations(db, MIGRATIONS / "core", "C",
                                       db_label="core")

    def test_new_db_creation_ok_without_marker(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "core.db"
            rows = migrate.run_migrations(db, MIGRATIONS / "core", "C",
                                          db_label="core")
            self.assertEqual(rows[0]["status"], "APPLIED")


class TestSeparateHistories(unittest.TestCase):
    def test_core_and_private_independent(self):
        with tempfile.TemporaryDirectory() as td:
            core_db = Path(td) / "core.db"
            priv_db = Path(td) / "private.db"
            migrate.run_migrations(core_db, MIGRATIONS / "core", "C",
                                   db_label="core", no_backup_gate=True)
            migrate.run_migrations(priv_db, MIGRATIONS / "private", "P",
                                   db_label="private", no_backup_gate=True)
            c1 = migrate.connect_db(core_db)
            c2 = migrate.connect_db(priv_db)
            try:
                core_recs = c1.execute(
                    "SELECT migration_id FROM schema_migrations"
                ).fetchall()
                priv_recs = c2.execute(
                    "SELECT migration_id FROM schema_migrations"
                ).fetchall()
                self.assertEqual([r[0] for r in core_recs], ["C0001"])
                self.assertEqual([r[0] for r in priv_recs], ["P0001"])
            finally:
                c1.close()
                c2.close()


if __name__ == "__main__":
    unittest.main()
