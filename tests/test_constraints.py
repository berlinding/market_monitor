"""T2 Schema constraint tests — 17 business constraint cases (R1B test plan §3
+ R1B.1 T-EVIDENCE-01/02). All against temp DBs."""

import sqlite3
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import migrate  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS = PROJECT_ROOT / "docs" / "database" / "sql" / "migrations"


def uid() -> str:
    return str(uuid.uuid4())


def now() -> str:
    return "2026-08-22T04:00:00Z"


def build_core(td: str) -> sqlite3.Connection:
    db = Path(td) / "core.db"
    migrate.run_migrations(db, MIGRATIONS / "core", "C", db_label="core",
                           no_backup_gate=True)
    return migrate.connect_db(db)


def build_private(td: str) -> sqlite3.Connection:
    db = Path(td) / "private.db"
    migrate.run_migrations(db, MIGRATIONS / "private", "P", db_label="private",
                           no_backup_gate=True)
    return migrate.connect_db(db)


def seed_source_dataset(conn, source_code="TUSHARE", dataset_code="CN_EQUITY_DAILY"):
    cur = conn.execute(
        "INSERT INTO data_sources(source_code, source_name, source_type, status,"
        " created_at, updated_at) VALUES (?, ?, 'MARKET_DATA', 'ACTIVE', ?, ?)",
        (source_code, source_code, now(), now()),
    )
    source_id = cur.lastrowid
    cur = conn.execute(
        "INSERT INTO datasets(dataset_code, dataset_name, dataset_type, granularity,"
        " write_mode, status, created_at, updated_at)"
        " VALUES (?, ?, 'PRICE_DAILY', 'DAILY', 'UPSERT', 'ACTIVE', ?, ?)",
        (dataset_code, dataset_code, now(), now()),
    )
    dataset_id = cur.lastrowid
    return source_id, dataset_id


class TestEntityUidUnique(unittest.TestCase):
    def test_duplicate_entity_uid_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            conn = build_core(td)
            try:
                e = uid()
                conn.execute(
                    "INSERT INTO entities(entity_uid, canonical_name, entity_type,"
                    " created_at, updated_at) VALUES (?, ?, 'COMPANY', ?, ?)",
                    (e, "A", now(), now()),
                )
                with self.assertRaises(sqlite3.IntegrityError):
                    conn.execute(
                        "INSERT INTO entities(entity_uid, canonical_name, entity_type,"
                        " created_at, updated_at) VALUES (?, ?, 'COMPANY', ?, ?)",
                        (e, "B", now(), now()),
                    )
            finally:
                conn.close()


class TestTickerReuse(unittest.TestCase):
    def _seed_instrument(self, conn, symbol, exchange):
        cur = conn.execute(
            "INSERT INTO instruments(instrument_uid, instrument_type, primary_symbol,"
            " exchange_code, currency_code, status, created_at, updated_at)"
            " VALUES (?, 'EQUITY', ?, ?, 'CNY', 'ACTIVE', ?, ?)",
            (uid(), symbol, exchange, now(), now()),
        )
        return cur.lastrowid

    def test_duplicate_current_ticker_mapping_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            conn = build_core(td)
            try:
                inst = self._seed_instrument(conn, "600519", "XSHG")
                conn.execute(
                    "INSERT INTO instrument_identifiers(instrument_id, provider,"
                    " identifier_type, identifier, valid_from, is_primary, created_at)"
                    " VALUES (?, 'TUSHARE', 'EXCHANGE_SYMBOL', '600519.SH',"
                    " '2004-01-01', 1, ?)",
                    (inst, now()),
                )
                with self.assertRaises(sqlite3.IntegrityError):
                    conn.execute(
                        "INSERT INTO instrument_identifiers(instrument_id, provider,"
                        " identifier_type, identifier, valid_from, is_primary, created_at)"
                        " VALUES (?, 'TUSHARE', 'EXCHANGE_SYMBOL', '600519.SH',"
                        " '2005-01-01', 1, ?)",
                        (inst, now()),
                    )
            finally:
                conn.close()

    def test_historical_ticker_reuse_allowed(self):
        with tempfile.TemporaryDirectory() as td:
            conn = build_core(td)
            try:
                inst_a = self._seed_instrument(conn, "ABC", "XNAS")
                conn.execute(
                    "INSERT INTO instrument_identifiers(instrument_id, provider,"
                    " identifier_type, identifier, valid_from, valid_to, is_primary,"
                    " created_at) VALUES (?, 'STANDARD', 'TICKER', 'ABC',"
                    " '2015-01-01', '2020-12-31', 1, ?)",
                    (inst_a, now()),
                )
                inst_b = self._seed_instrument(conn, "ABC", "XNAS")
                # same ticker, new company, current mapping valid_to NULL -> allowed
                conn.execute(
                    "INSERT INTO instrument_identifiers(instrument_id, provider,"
                    " identifier_type, identifier, valid_from, is_primary, created_at)"
                    " VALUES (?, 'STANDARD', 'TICKER', 'ABC', '2025-01-01', 1, ?)",
                    (inst_b, now()),
                )
                # but two current mappings still rejected
                with self.assertRaises(sqlite3.IntegrityError):
                    conn.execute(
                        "INSERT INTO instrument_identifiers(instrument_id, provider,"
                        " identifier_type, identifier, valid_from, is_primary, created_at)"
                        " VALUES (?, 'STANDARD', 'TICKER', 'ABC', '2026-01-01', 1, ?)",
                        (inst_b, now()),
                    )
            finally:
                conn.close()


class TestDatasetSources(unittest.TestCase):
    def test_two_active_primary_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            conn = build_core(td)
            try:
                s1, d1 = seed_source_dataset(conn, "TUSHARE", "CN_EQUITY_DAILY")
                cur = conn.execute(
                    "INSERT INTO data_sources(source_code, source_name, source_type,"
                    " status, created_at, updated_at)"
                    " VALUES ('FMP', 'FMP', 'MARKET_DATA', 'ACTIVE', ?, ?)",
                    (now(), now()),
                )
                s2 = cur.lastrowid
                conn.execute(
                    "INSERT INTO dataset_sources(dataset_id, source_id, role,"
                    " priority_rank, is_active, created_at, updated_at)"
                    " VALUES (?, ?, 'PRIMARY', 1, 1, ?, ?)",
                    (d1, s1, now(), now()),
                )
                with self.assertRaises(sqlite3.IntegrityError):
                    conn.execute(
                        "INSERT INTO dataset_sources(dataset_id, source_id, role,"
                        " priority_rank, is_active, created_at, updated_at)"
                        " VALUES (?, ?, 'PRIMARY', 2, 1, ?, ?)",
                        (d1, s2, now(), now()),
                    )
            finally:
                conn.close()

    def test_fallback_rank_duplicate_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            conn = build_core(td)
            try:
                s1, d1 = seed_source_dataset(conn, "TUSHARE", "CN_EQUITY_DAILY")
                conn.execute(
                    "INSERT INTO data_sources(source_code, source_name, source_type,"
                    " status, created_at, updated_at)"
                    " VALUES ('FMP', 'FMP', 'MARKET_DATA', 'ACTIVE', ?, ?)",
                    (now(), now()),
                )
                conn.execute(
                    "INSERT INTO data_sources(source_code, source_name, source_type,"
                    " status, created_at, updated_at)"
                    " VALUES ('YAHOO', 'Yahoo', 'MARKET_DATA', 'ACTIVE', ?, ?)",
                    (now(), now()),
                )
                fmp = conn.execute(
                    "SELECT source_id FROM data_sources WHERE source_code='FMP'"
                ).fetchone()[0]
                yahoo = conn.execute(
                    "SELECT source_id FROM data_sources WHERE source_code='YAHOO'"
                ).fetchone()[0]
                conn.execute(
                    "INSERT INTO dataset_sources(dataset_id, source_id, role,"
                    " priority_rank, is_active, created_at, updated_at)"
                    " VALUES (?, ?, 'FALLBACK', 2, 1, ?, ?)",
                    (d1, fmp, now(), now()),
                )
                with self.assertRaises(sqlite3.IntegrityError):
                    conn.execute(
                        "INSERT INTO dataset_sources(dataset_id, source_id, role,"
                        " priority_rank, is_active, created_at, updated_at)"
                        " VALUES (?, ?, 'FALLBACK', 2, 1, ?, ?)",
                        (d1, yahoo, now(), now()),
                    )
            finally:
                conn.close()


class TestRawArtifactHash(unittest.TestCase):
    def _seed(self, conn):
        s1, d1 = seed_source_dataset(conn)
        cur = conn.execute(
            "INSERT INTO ingest_runs(dataset_id, source_id, trigger_type, started_at,"
            " status) VALUES (?, ?, 'MANUAL', ?, 'SUCCESS')",
            (d1, s1, "2026-08-22T01:00:00Z"),
        )
        run1 = cur.lastrowid
        cur = conn.execute(
            "INSERT INTO ingest_runs(dataset_id, source_id, trigger_type, started_at,"
            " status) VALUES (?, ?, 'MANUAL', ?, 'SUCCESS')",
            (d1, s1, "2026-08-22T02:00:00Z"),
        )
        run2 = cur.lastrowid
        return d1, s1, run1, run2

    def test_same_hash_different_runs_allowed(self):
        with tempfile.TemporaryDirectory() as td:
            conn = build_core(td)
            try:
                d1, s1, run1, run2 = self._seed(conn)
                h = "a" * 64
                for run in (run1, run2):
                    conn.execute(
                        "INSERT INTO raw_artifacts(artifact_uid, dataset_id, source_id,"
                        " run_id, artifact_type, content_hash, retrieved_at, created_at)"
                        " VALUES (?, ?, ?, ?, 'FILE', ?, ?, ?)",
                        (uid(), d1, s1, run, h, now(), now()),
                    )
                conn.commit()
            finally:
                conn.close()

    def test_same_hash_same_run_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            conn = build_core(td)
            try:
                d1, s1, run1, _ = self._seed(conn)
                h = "b" * 64
                conn.execute(
                    "INSERT INTO raw_artifacts(artifact_uid, dataset_id, source_id,"
                    " run_id, artifact_type, content_hash, retrieved_at, created_at)"
                    " VALUES (?, ?, ?, ?, 'FILE', ?, ?, ?)",
                    (uid(), d1, s1, run1, h, now(), now()),
                )
                with self.assertRaises(sqlite3.IntegrityError):
                    conn.execute(
                        "INSERT INTO raw_artifacts(artifact_uid, dataset_id, source_id,"
                        " run_id, artifact_type, content_hash, retrieved_at, created_at)"
                        " VALUES (?, ?, ?, ?, 'FILE', ?, ?, ?)",
                        (uid(), d1, s1, run1, h, now(), now()),
                    )
            finally:
                conn.close()

    def test_manual_artifact_duplicate_hash_allowed(self):
        with tempfile.TemporaryDirectory() as td:
            conn = build_core(td)
            try:
                d1, s1, _, _ = self._seed(conn)
                h = "c" * 64
                for _ in range(2):  # run_id NULL -> allowed duplicates
                    conn.execute(
                        "INSERT INTO raw_artifacts(artifact_uid, dataset_id, source_id,"
                        " artifact_type, content_hash, retrieved_at, created_at)"
                        " VALUES (?, ?, ?, 'FILE', ?, ?, ?)",
                        (uid(), d1, s1, h, now(), now()),
                    )
                conn.commit()
            finally:
                conn.close()


class TestEventModel(unittest.TestCase):
    def _seed_event(self, conn):
        s1, _ = seed_source_dataset(conn)
        cur = conn.execute(
            "INSERT INTO events(event_uid, fingerprint, discovered_by_source_id,"
            " event_type, title, status, created_at, updated_at)"
            " VALUES (?, ?, ?, 'EARNINGS', 'E', 'NEW', ?, ?)",
            (uid(), "fp-" + uid(), s1, now(), now()),
        )
        return cur.lastrowid, s1

    def _seed_entity(self, conn):
        cur = conn.execute(
            "INSERT INTO entities(entity_uid, canonical_name, entity_type,"
            " created_at, updated_at) VALUES (?, 'Co', 'COMPANY', ?, ?)",
            (uid(), now(), now()),
        )
        return cur.lastrowid

    def test_event_multi_entity_allowed(self):
        with tempfile.TemporaryDirectory() as td:
            conn = build_core(td)
            try:
                eid, _ = self._seed_event(conn)
                e1 = self._seed_entity(conn)
                e2 = self._seed_entity(conn)
                conn.execute(
                    "INSERT INTO event_entities(event_id, entity_id, role, created_at)"
                    " VALUES (?, ?, 'PRIMARY', ?)", (eid, e1, now())
                )
                conn.execute(
                    "INSERT INTO event_entities(event_id, entity_id, role, created_at)"
                    " VALUES (?, ?, 'TARGET', ?)", (eid, e2, now())
                )
                conn.commit()
            finally:
                conn.close()

    def test_event_evidence_same_key_different_source_allowed(self):
        """T-EVIDENCE-01"""
        with tempfile.TemporaryDirectory() as td:
            conn = build_core(td)
            try:
                eid, s1 = self._seed_event(conn)
                cur = conn.execute(
                    "INSERT INTO data_sources(source_code, source_name, source_type,"
                    " status, created_at, updated_at)"
                    " VALUES ('REUTERS', 'Reuters', 'NEWS', 'ACTIVE', ?, ?)",
                    (now(), now()),
                )
                s2 = cur.lastrowid
                for src in (s1, s2):
                    conn.execute(
                        "INSERT INTO event_evidence(evidence_uid, event_id, source_id,"
                        " evidence_key, evidence_type, detected_at, content_hash,"
                        " is_primary, created_at)"
                        " VALUES (?, ?, ?, 'native:12345', 'NEWS', ?, ?, 0, ?)",
                        (uid(), eid, src, now(), "d" * 64, now()),
                    )
                conn.commit()
            finally:
                conn.close()

    def test_event_evidence_same_source_same_key_rejected(self):
        """T-EVIDENCE-02"""
        with tempfile.TemporaryDirectory() as td:
            conn = build_core(td)
            try:
                eid, s1 = self._seed_event(conn)
                conn.execute(
                    "INSERT INTO event_evidence(evidence_uid, event_id, source_id,"
                    " evidence_key, evidence_type, detected_at, content_hash,"
                    " is_primary, created_at)"
                    " VALUES (?, ?, ?, 'native:999', 'NEWS', ?, ?, 0, ?)",
                    (uid(), eid, s1, now(), "e" * 64, now()),
                )
                with self.assertRaises(sqlite3.IntegrityError):
                    conn.execute(
                        "INSERT INTO event_evidence(evidence_uid, event_id, source_id,"
                        " evidence_key, evidence_type, detected_at, content_hash,"
                        " is_primary, created_at)"
                        " VALUES (?, ?, ?, 'native:999', 'NEWS', ?, ?, 0, ?)",
                        (uid(), eid, s1, now(), "e" * 64, now()),
                    )
            finally:
                conn.close()

    def test_event_single_primary_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            conn = build_core(td)
            try:
                eid, s1 = self._seed_event(conn)
                conn.execute(
                    "INSERT INTO event_evidence(evidence_uid, event_id, source_id,"
                    " evidence_key, evidence_type, detected_at, content_hash,"
                    " is_primary, created_at)"
                    " VALUES (?, ?, ?, 'k1', 'NEWS', ?, ?, 1, ?)",
                    (uid(), eid, s1, now(), "f" * 64, now()),
                )
                with self.assertRaises(sqlite3.IntegrityError):
                    conn.execute(
                        "INSERT INTO event_evidence(evidence_uid, event_id, source_id,"
                        " evidence_key, evidence_type, detected_at, content_hash,"
                        " is_primary, created_at)"
                        " VALUES (?, ?, ?, 'k2', 'NEWS', ?, ?, 1, ?)",
                        (uid(), eid, s1, now(), "g" * 64, now()),
                    )
            finally:
                conn.close()


class TestWatchlistXor(unittest.TestCase):
    def test_xor_enforced(self):
        with tempfile.TemporaryDirectory() as td:
            conn = build_private(td)
            try:
                conn.execute(
                    "INSERT INTO watchlists(name, created_at, updated_at)"
                    " VALUES ('wl', ?, ?)", (now(), now())
                )
                wl = conn.execute(
                    "SELECT watchlist_id FROM watchlists"
                ).fetchone()[0]
                # both set -> rejected
                with self.assertRaises(sqlite3.IntegrityError):
                    conn.execute(
                        "INSERT INTO watchlist_items(watchlist_id, entity_uid,"
                        " instrument_uid, status, created_at, updated_at)"
                        " VALUES (?, ?, ?, 'ACTIVE', ?, ?)",
                        (wl, uid(), uid(), now(), now()),
                    )
                # both null -> rejected
                with self.assertRaises(sqlite3.IntegrityError):
                    conn.execute(
                        "INSERT INTO watchlist_items(watchlist_id, status, created_at,"
                        " updated_at) VALUES (?, 'ACTIVE', ?, ?)",
                        (wl, now(), now()),
                    )
                # exactly one -> allowed
                conn.execute(
                    "INSERT INTO watchlist_items(watchlist_id, entity_uid, status,"
                    " created_at, updated_at) VALUES (?, ?, 'ACTIVE', ?, ?)",
                    (wl, uid(), now(), now()),
                )
                conn.commit()
            finally:
                conn.close()

    def test_duplicate_entity_in_watchlist_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            conn = build_private(td)
            try:
                conn.execute(
                    "INSERT INTO watchlists(name, created_at, updated_at)"
                    " VALUES ('wl', ?, ?)", (now(), now())
                )
                wl = conn.execute(
                    "SELECT watchlist_id FROM watchlists"
                ).fetchone()[0]
                e = uid()
                conn.execute(
                    "INSERT INTO watchlist_items(watchlist_id, entity_uid, status,"
                    " created_at, updated_at) VALUES (?, ?, 'ACTIVE', ?, ?)",
                    (wl, e, now(), now()),
                )
                with self.assertRaises(sqlite3.IntegrityError):
                    conn.execute(
                        "INSERT INTO watchlist_items(watchlist_id, entity_uid, status,"
                        " created_at, updated_at) VALUES (?, ?, 'ACTIVE', ?, ?)",
                        (wl, e, now(), now()),
                    )
            finally:
                conn.close()


class TestPositions(unittest.TestCase):
    def _seed(self, conn):
        cur = conn.execute(
            "INSERT INTO accounts(account_uid, account_name, account_type,"
            " base_currency, status, created_at, updated_at)"
            " VALUES (?, 'acc1', 'MARGIN', 'USD', 'ACTIVE', ?, ?)",
            (uid(), now(), now()),
        )
        acc = cur.lastrowid
        cur = conn.execute(
            "INSERT INTO accounts(account_uid, account_name, account_type,"
            " base_currency, status, created_at, updated_at)"
            " VALUES (?, 'acc2', 'CASH', 'USD', 'ACTIVE', ?, ?)",
            (uid(), now(), now()),
        )
        acc2 = cur.lastrowid
        return acc, acc2

    def test_duplicate_open_position_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            conn = build_private(td)
            try:
                acc, _ = self._seed(conn)
                inst = uid()
                conn.execute(
                    "INSERT INTO positions(account_id, instrument_uid, quantity,"
                    " currency_code, as_of_date, status, created_at, updated_at)"
                    " VALUES (?, ?, 10, 'USD', '2026-08-22', 'OPEN', ?, ?)",
                    (acc, inst, now(), now()),
                )
                with self.assertRaises(sqlite3.IntegrityError):
                    conn.execute(
                        "INSERT INTO positions(account_id, instrument_uid, quantity,"
                        " currency_code, as_of_date, status, created_at, updated_at)"
                        " VALUES (?, ?, 10, 'USD', '2026-08-22', 'OPEN', ?, ?)",
                        (acc, inst, now(), now()),
                    )
            finally:
                conn.close()

    def test_same_instrument_different_accounts_allowed(self):
        with tempfile.TemporaryDirectory() as td:
            conn = build_private(td)
            try:
                acc, acc2 = self._seed(conn)
                inst = uid()
                for a in (acc, acc2):
                    conn.execute(
                        "INSERT INTO positions(account_id, instrument_uid, quantity,"
                        " currency_code, as_of_date, status, created_at, updated_at)"
                        " VALUES (?, ?, 10, 'USD', '2026-08-22', 'OPEN', ?, ?)",
                        (a, inst, now(), now()),
                    )
                conn.commit()
            finally:
                conn.close()

    def test_closed_position_does_not_block_new_open(self):
        with tempfile.TemporaryDirectory() as td:
            conn = build_private(td)
            try:
                acc, _ = self._seed(conn)
                inst = uid()
                conn.execute(
                    "INSERT INTO positions(account_id, instrument_uid, quantity,"
                    " currency_code, as_of_date, status, created_at, updated_at)"
                    " VALUES (?, ?, 10, 'USD', '2026-08-20', 'CLOSED', ?, ?)",
                    (acc, inst, now(), now()),
                )
                conn.execute(
                    "INSERT INTO positions(account_id, instrument_uid, quantity,"
                    " currency_code, as_of_date, status, created_at, updated_at)"
                    " VALUES (?, ?, 10, 'USD', '2026-08-22', 'OPEN', ?, ?)",
                    (acc, inst, now(), now()),
                )
                conn.commit()
            finally:
                conn.close()


class TestCrossDbUidStorage(unittest.TestCase):
    def test_private_can_store_core_uid_reference(self):
        """private DB can hold a core uid TEXT reference (no pseudo-FK)."""
        with tempfile.TemporaryDirectory() as td:
            conn = build_private(td)
            try:
                cur = conn.execute(
                    "INSERT INTO accounts(account_uid, account_name, account_type,"
                    " base_currency, status, created_at, updated_at)"
                    " VALUES (?, 'acc1', 'CASH', 'USD', 'ACTIVE', ?, ?)",
                    (uid(), now(), now()),
                )
                acc = cur.lastrowid
                conn.execute(
                    "INSERT INTO positions(account_id, instrument_uid, quantity,"
                    " currency_code, as_of_date, status, created_at, updated_at)"
                    " VALUES (?, ?, 5, 'USD', '2026-08-22', 'OPEN', ?, ?)",
                    (acc, uid(), now(), now()),
                )
                conn.commit()
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
