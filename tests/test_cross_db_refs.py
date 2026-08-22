"""T4 Cross-db UID validators tests — ensure_*_uid against temp core.db."""

import sqlite3
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import db_validators, migrate  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS = PROJECT_ROOT / "docs" / "database" / "sql" / "migrations"


def now() -> str:
    return "2026-08-22T04:00:00Z"


def uid() -> str:
    return str(uuid.uuid4())


def build_core(td: str) -> tuple[sqlite3.Connection, Path]:
    db = Path(td) / "core.db"
    migrate.run_migrations(db, MIGRATIONS / "core", "C", db_label="core",
                           no_backup_gate=True)
    conn = migrate.connect_db(db)
    return conn, db


def seed_entity(conn):
    cur = conn.execute(
        "INSERT INTO entities(entity_uid, canonical_name, entity_type,"
        " created_at, updated_at) VALUES (?, 'Co', 'COMPANY', ?, ?)",
        (uid(), now(), now()),
    )
    return cur.lastrowid


def seed_instrument(conn):
    cur = conn.execute(
        "INSERT INTO instruments(instrument_uid, instrument_type, primary_symbol,"
        " exchange_code, currency_code, status, created_at, updated_at)"
        " VALUES (?, 'EQUITY', '600519', 'XSHG', 'CNY', 'ACTIVE', ?, ?)",
        (uid(), now(), now()),
    )
    return cur.lastrowid


def seed_event(conn):
    cur = conn.execute(
        "INSERT INTO events(event_uid, fingerprint, event_type, title, status,"
        " created_at, updated_at) VALUES (?, ?, 'EARNINGS', 'E', 'NEW', ?, ?)",
        (uid(), "fp-" + uid(), now(), now()),
    )
    return cur.lastrowid


def seed_analysis(conn):
    ev = seed_event(conn)
    cur = conn.execute(
        "INSERT INTO event_analysis(analysis_uid, event_id, model_provider, model_id,"
        " prompt_version, analysis_version, created_at)"
        " VALUES (?, ?, 'test', 'm1', 'p1', 'a1', ?)",
        (uid(), ev, now()),
    )
    return cur.lastrowid


class TestEntityUidValidator(unittest.TestCase):
    def test_valid_uid_returns_true(self):
        with tempfile.TemporaryDirectory() as td:
            conn, _ = build_core(td)
            try:
                e = seed_entity(conn)
                e_uid = conn.execute(
                    "SELECT entity_uid FROM entities WHERE entity_id=?", (e,)
                ).fetchone()[0]
                self.assertTrue(db_validators.ensure_entity_uid(conn, e_uid))
            finally:
                conn.close()

    def test_missing_uid_raises(self):
        with tempfile.TemporaryDirectory() as td:
            conn, _ = build_core(td)
            try:
                with self.assertRaises(db_validators.CrossDbReferenceError):
                    db_validators.ensure_entity_uid(conn, uid())
            finally:
                conn.close()

    def test_invalid_format_raises(self):
        with tempfile.TemporaryDirectory() as td:
            conn, _ = build_core(td)
            try:
                with self.assertRaises(db_validators.CrossDbReferenceError):
                    db_validators.ensure_entity_uid(conn, "not-a-uuid")
            finally:
                conn.close()


class TestInstrumentUidValidator(unittest.TestCase):
    def test_valid_and_missing(self):
        with tempfile.TemporaryDirectory() as td:
            conn, _ = build_core(td)
            try:
                i = seed_instrument(conn)
                i_uid = conn.execute(
                    "SELECT instrument_uid FROM instruments WHERE instrument_id=?",
                    (i,),
                ).fetchone()[0]
                self.assertTrue(db_validators.ensure_instrument_uid(conn, i_uid))
                with self.assertRaises(db_validators.CrossDbReferenceError):
                    db_validators.ensure_instrument_uid(conn, uid())
            finally:
                conn.close()


class TestEventUidValidator(unittest.TestCase):
    def test_valid_and_missing(self):
        with tempfile.TemporaryDirectory() as td:
            conn, _ = build_core(td)
            try:
                ev = seed_event(conn)
                ev_uid = conn.execute(
                    "SELECT event_uid FROM events WHERE event_id=?", (ev,)
                ).fetchone()[0]
                self.assertTrue(db_validators.ensure_event_uid(conn, ev_uid))
                with self.assertRaises(db_validators.CrossDbReferenceError):
                    db_validators.ensure_event_uid(conn, uid())
            finally:
                conn.close()


class TestAnalysisUidValidator(unittest.TestCase):
    def test_valid_and_missing(self):
        with tempfile.TemporaryDirectory() as td:
            conn, _ = build_core(td)
            try:
                a = seed_analysis(conn)
                a_uid = conn.execute(
                    "SELECT analysis_uid FROM event_analysis WHERE analysis_id=?",
                    (a,),
                ).fetchone()[0]
                self.assertTrue(db_validators.ensure_analysis_uid(conn, a_uid))
                with self.assertRaises(db_validators.CrossDbReferenceError):
                    db_validators.ensure_analysis_uid(conn, uid())
            finally:
                conn.close()


class TestUidStableAcrossRebuild(unittest.TestCase):
    def test_uid_survives_core_rebuild(self):
        """Export core, rebuild from dump, same uids resolve (B3 rebuild safety)."""
        with tempfile.TemporaryDirectory() as td:
            conn, db = build_core(td)
            try:
                e_uid = uid()
                conn.execute(
                    "INSERT INTO entities(entity_uid, canonical_name, entity_type,"
                    " created_at, updated_at) VALUES (?, 'Co', 'COMPANY', ?, ?)",
                    (e_uid, now(), now()),
                )
                conn.commit()
                dump = "\n".join(conn.iterdump())
            finally:
                conn.close()

            # rebuild
            db2 = Path(td) / "core2.db"
            conn2 = sqlite3.connect(str(db2))
            conn2.executescript(dump)
            conn2.commit()
            try:
                self.assertTrue(db_validators.ensure_entity_uid(conn2, e_uid))
            finally:
                conn2.close()


if __name__ == "__main__":
    unittest.main()
