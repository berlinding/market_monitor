"""T8 R2 Minimal Portfolio & Watchlist tests (temp DBs only).

Covers §28 test list (R2-ACCOUNT-01 ... R2-PRIVACY-01) plus identity
resolution, monitoring universe, and cross-db validation. NEVER touches
data/runtime/core.db or data/private/private.db.
"""

import sqlite3
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import migrate  # noqa: E402
from scripts.portfolio.service import (  # noqa: E402
    AccountNameConflictError,
    CrossDbReferenceError,
    IdentityNotFoundError,
    PortfolioService,
    PositionNotFoundError,
    WatchlistItemError,
    WatchlistNameConflictError,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS = PROJECT_ROOT / "docs" / "database" / "sql" / "migrations"


def uid() -> str:
    return str(uuid.uuid4())


def now() -> str:
    return "2026-08-25T08:00:00Z"


def build_temp_core(db_path: Path, instruments: list[dict] | None = None) -> list[dict]:
    """Create temp core.db with C0001 + synthetic identities."""
    migrate.run_migrations(db_path, MIGRATIONS / "core", "C", db_label="core",
                           no_backup_gate=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON;")
    created = []
    for spec in instruments or [
        {"ts": "600519.SH", "symbol": "600519", "name": "贵州茅台",
         "mic": "XSHG", "list_date": "2001-08-27"},
        {"ts": "000001.SZ", "symbol": "000001", "name": "平安银行",
         "mic": "XSHE", "list_date": "1991-04-03"},
        {"ts": "430047.BJ", "symbol": "430047", "name": "诺思兰德",
         "mic": "XBSE", "list_date": "2021-11-15"},
    ]:
        entity_u = uid()
        inst_u = uid()
        conn.execute(
            "INSERT INTO entities(entity_uid, canonical_name, entity_type,"
            " country_code, status, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (entity_u, spec["name"], "COMPANY", "CN", "ACTIVE", now(), now()),
        )
        entity_id = conn.execute(
            "SELECT entity_id FROM entities WHERE entity_uid = ?", (entity_u,)
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO instruments(instrument_uid, entity_id, instrument_type,"
            " primary_symbol, exchange_code, currency_code, country_code, status,"
            " listing_date, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (inst_u, entity_id, "EQUITY", spec["symbol"], spec["mic"], "CNY",
             "CN", "ACTIVE", spec["list_date"], now(), now()),
        )
        inst_id = conn.execute(
            "SELECT instrument_id FROM instruments WHERE instrument_uid = ?",
            (inst_u,),
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO instrument_identifiers(instrument_id, provider,"
            " identifier_type, identifier, valid_from, valid_to, is_primary,"
            " created_at) VALUES (?,?,?,?,?,?,?,?)",
            (inst_id, "TUSHARE", "EXCHANGE_SYMBOL", spec["ts"],
             spec["list_date"], None, 1, now()),
        )
        conn.execute(
            "INSERT INTO instrument_identifiers(instrument_id, provider,"
            " identifier_type, identifier, valid_from, valid_to, is_primary,"
            " created_at) VALUES (?,?,?,?,?,?,?,?)",
            (inst_id, "STANDARD", "TICKER", spec["symbol"],
             spec["list_date"], None, 0, now()),
        )
        created.append({"ts": spec["ts"], "symbol": spec["symbol"],
                        "name": spec["name"], "entity_uid": entity_u,
                        "instrument_uid": inst_u})
    conn.commit()
    conn.close()
    return created


def build_temp_private(db_path: Path) -> None:
    migrate.run_migrations(db_path, MIGRATIONS / "private", "P", db_label="private",
                           no_backup_gate=True)


class R2TestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        td = Path(self._tmp.name)
        self.core_db = td / "core.db"
        self.private_db = td / "private.db"
        self.identities = build_temp_core(self.core_db)
        build_temp_private(self.private_db)
        self.svc = PortfolioService(self.core_db, self.private_db)

    def tearDown(self):
        self._tmp.cleanup()

    # convenience
    def make_account(self, name="paper"):
        return self.svc.create_account(name, broker="manual",
                                       account_type="PAPER", base_currency="CNY")


class TestAccount(unittest.TestCase):
    def _fresh(self):
        tmp = tempfile.TemporaryDirectory()
        td = Path(tmp.name)
        core_db, private_db = td / "core.db", td / "private.db"
        build_temp_core(core_db)
        build_temp_private(private_db)
        return PortfolioService(core_db, private_db), tmp

    def test_r2_account_01_create_list(self):
        """R2-ACCOUNT-01: create + list account."""
        svc, tmp = self._fresh()
        try:
            acc = svc.create_account("paper", broker="manual", account_type="PAPER",
                                     base_currency="CNY")
            self.assertEqual(acc["account_name"], "paper")
            self.assertEqual(acc["account_type"], "PAPER")
            self.assertEqual(acc["base_currency"], "CNY")
            accounts = svc.list_accounts()
            self.assertEqual(len(accounts), 1)
            self.assertEqual(accounts[0]["account_name"], "paper")
        finally:
            tmp.cleanup()

    def test_r2_account_unique_01(self):
        """R2-ACCOUNT-UNIQUE-01: duplicate account name rejected."""
        svc, tmp = self._fresh()
        try:
            svc.create_account("paper")
            with self.assertRaises(AccountNameConflictError):
                svc.create_account("paper")
        finally:
            tmp.cleanup()

    def test_r2_account_invalid_type(self):
        svc, tmp = self._fresh()
        try:
            with self.assertRaises(Exception):
                svc.create_account("x", account_type="BROKER")
        finally:
            tmp.cleanup()


class TestPosition(unittest.TestCase):
    def _fresh(self):
        tmp = tempfile.TemporaryDirectory()
        td = Path(tmp.name)
        core_db, private_db = td / "core.db", td / "private.db"
        identities = build_temp_core(core_db)
        build_temp_private(private_db)
        svc = PortfolioService(core_db, private_db)
        svc.create_account("paper")
        return svc, identities, tmp

    def test_r2_position_01_create(self):
        """R2-POSITION-01: create OPEN position."""
        svc, ids, tmp = self._fresh()
        try:
            res = svc.set_position("paper", "600519.SH", quantity=100,
                                   average_cost=1500, currency="CNY")
            self.assertEqual(res["action"], "INSERTED")
            self.assertEqual(res["quantity"], 100)
            pos = svc.get_position("paper", "600519.SH")
            self.assertEqual(pos["status"], "OPEN")
            self.assertEqual(pos["display_symbol"], "600519")
            self.assertEqual(pos["entity_name"], "贵州茅台")
            self.assertEqual(pos["quantity"], 100)
            self.assertEqual(pos["average_cost"], 1500)
        finally:
            tmp.cleanup()

    def test_r2_position_update_01(self):
        """R2-POSITION-UPDATE-01: same account+instrument controlled update."""
        svc, ids, tmp = self._fresh()
        try:
            svc.set_position("paper", "600519.SH", quantity=100, average_cost=1500)
            res = svc.set_position("paper", "600519.SH", quantity=200, average_cost=1600)
            self.assertEqual(res["action"], "UPDATED")
            pos = svc.get_position("paper", "600519.SH")
            self.assertEqual(pos["quantity"], 200)
            self.assertEqual(pos["average_cost"], 1600)
            positions = svc.list_positions("paper")
            self.assertEqual(len(positions), 1)  # still one OPEN row
        finally:
            tmp.cleanup()

    def test_r2_position_close_01(self):
        """R2-POSITION-CLOSE-01: close position."""
        svc, ids, tmp = self._fresh()
        try:
            svc.set_position("paper", "600519.SH", quantity=100)
            res = svc.close_position("paper", "600519.SH")
            self.assertEqual(res["status"], "CLOSED")
            positions = svc.list_positions("paper", status="OPEN")
            self.assertEqual(len(positions), 0)
            closed = svc.list_positions("paper", status="CLOSED")
            self.assertEqual(len(closed), 1)
        finally:
            tmp.cleanup()

    def test_r2_position_identity_fail_01(self):
        """R2-POSITION-IDENTITY-FAIL-01: unknown instrument fail-fast."""
        svc, ids, tmp = self._fresh()
        try:
            with self.assertRaises(IdentityNotFoundError):
                svc.set_position("paper", "ABC_NOT_EXIST", quantity=10)
        finally:
            tmp.cleanup()

    def test_r2_position_negative_quantity(self):
        svc, ids, tmp = self._fresh()
        try:
            with self.assertRaises(Exception):
                svc.set_position("paper", "600519.SH", quantity=-5)
        finally:
            tmp.cleanup()


class TestWatchlist(unittest.TestCase):
    def _fresh(self):
        tmp = tempfile.TemporaryDirectory()
        td = Path(tmp.name)
        core_db, private_db = td / "core.db", td / "private.db"
        identities = build_temp_core(core_db)
        build_temp_private(private_db)
        svc = PortfolioService(core_db, private_db)
        return svc, identities, tmp

    def test_r2_watchlist_01_create(self):
        """R2-WATCHLIST-01: create watchlist."""
        svc, ids, tmp = self._fresh()
        try:
            wl = svc.create_watchlist("CORE")
            self.assertEqual(wl["name"], "CORE")
            self.assertEqual(len(svc.list_watchlists()), 1)
            with self.assertRaises(WatchlistNameConflictError):
                svc.create_watchlist("CORE")
        finally:
            tmp.cleanup()

    def test_r2_watchlist_instrument_01(self):
        """R2-WATCHLIST-INSTRUMENT-01: add instrument item."""
        svc, ids, tmp = self._fresh()
        try:
            svc.create_watchlist("CORE")
            item = svc.add_watchlist_item("CORE", instrument="600519.SH", reason="核心持仓")
            self.assertEqual(item["instrument_uid"], ids[0]["instrument_uid"])
            items = svc.list_watchlist_items("CORE")
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["target_type"], "INSTRUMENT")
            self.assertEqual(items[0]["display"], "600519")
        finally:
            tmp.cleanup()

    def test_r2_watchlist_entity_01(self):
        """R2-WATCHLIST-ENTITY-01: add entity item."""
        svc, ids, tmp = self._fresh()
        try:
            svc.create_watchlist("CORE")
            item = svc.add_watchlist_item("CORE", entity=ids[1]["entity_uid"])
            self.assertEqual(item["entity_uid"], ids[1]["entity_uid"])
            items = svc.list_watchlist_items("CORE")
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["target_type"], "ENTITY")
            self.assertEqual(items[0]["display"], "平安银行")
        finally:
            tmp.cleanup()

    def test_r2_watchlist_xor_01(self):
        """R2-WATCHLIST-XOR-01: both/null violation fail."""
        svc, ids, tmp = self._fresh()
        try:
            svc.create_watchlist("CORE")
            with self.assertRaises(WatchlistItemError):
                svc.add_watchlist_item("CORE", instrument="600519.SH",
                                       entity=ids[0]["entity_uid"])
            with self.assertRaises(WatchlistItemError):
                svc.add_watchlist_item("CORE")
        finally:
            tmp.cleanup()

    def test_r2_watchlist_dup_01(self):
        """R2-WATCHLIST-DUP-01: duplicate item rejected."""
        svc, ids, tmp = self._fresh()
        try:
            svc.create_watchlist("CORE")
            svc.add_watchlist_item("CORE", instrument="600519.SH")
            with self.assertRaises(WatchlistItemError):
                svc.add_watchlist_item("CORE", instrument="600519.SH")
        finally:
            tmp.cleanup()

    def test_r2_watchlist_unknown_identity_fail(self):
        svc, ids, tmp = self._fresh()
        try:
            svc.create_watchlist("CORE")
            with self.assertRaises(IdentityNotFoundError):
                svc.add_watchlist_item("CORE", instrument="NOPE.NOPE")
        finally:
            tmp.cleanup()


class TestCrossDbAndPrivacy(unittest.TestCase):
    def _fresh(self):
        tmp = tempfile.TemporaryDirectory()
        td = Path(tmp.name)
        core_db, private_db = td / "core.db", td / "private.db"
        identities = build_temp_core(core_db)
        build_temp_private(private_db)
        svc = PortfolioService(core_db, private_db)
        svc.create_account("paper")
        self.core_db = core_db
        self.private_db = private_db
        return svc, identities, tmp, core_db, private_db

    def test_r2_crossdb_01(self):
        """R2-CROSSDB-01: valid private UID resolves in core."""
        svc, ids, tmp, core_db, private_db = self._fresh()
        try:
            svc.set_position("paper", "600519.SH", quantity=10)
            svc.create_watchlist("CORE")
            svc.add_watchlist_item("CORE", instrument="000001.SZ")
            svc.add_watchlist_item("CORE", entity=ids[0]["entity_uid"])
            result = svc.validate_private_core_references()
            self.assertTrue(result["valid"], msg=f"problems: {result['problems']}")
            self.assertEqual(result["counts"]["positions"], 1)
            self.assertEqual(result["counts"]["watchlist_instruments"], 1)
            self.assertEqual(result["counts"]["watchlist_entities"], 1)
        finally:
            tmp.cleanup()

    def test_r2_crossdb_orphan_01(self):
        """R2-CROSSDB-ORPHAN-01: orphan detected."""
        svc, ids, tmp, core_db, private_db = self._fresh()
        try:
            # inject orphan directly (bypass service guard) to test validator
            import sqlite3 as _sq
            orphan_uid = uid()
            acc_id = svc.private.find_account_by_name("paper")["account_id"]
            conn = _sq.connect(str(private_db))
            conn.execute(
                "INSERT INTO positions(account_id, instrument_uid, quantity,"
                " currency_code, as_of_date, status, created_at, updated_at)"
                " VALUES (?,?,?,?,?, 'OPEN', ?, ?)",
                (acc_id, orphan_uid, 5, "CNY", "2026-08-25", now(), now()),
            )
            conn.commit()
            conn.close()
            result = svc.validate_private_core_references()
            self.assertFalse(result["valid"])
            self.assertTrue(any("orphan" in p for p in result["problems"]))
        finally:
            tmp.cleanup()

    def test_r2_privacy_01(self):
        """R2-PRIVACY-01: private fields absent from core DB."""
        svc, ids, tmp, core_db, private_db = self._fresh()
        try:
            conn = sqlite3.connect(f"file:{core_db.resolve()}?mode=ro", uri=True)
            try:
                tables = {r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")}
                self.assertNotIn("accounts", tables)
                self.assertNotIn("positions", tables)
                self.assertNotIn("watchlists", tables)
                cols = {r[1] for r in conn.execute("PRAGMA table_info('instruments')")}
                self.assertNotIn("avg_cost", cols)
                self.assertNotIn("quantity", cols)
            finally:
                conn.close()
        finally:
            tmp.cleanup()


class TestIdentityAndUniverse(unittest.TestCase):
    def _fresh(self):
        tmp = tempfile.TemporaryDirectory()
        td = Path(tmp.name)
        core_db, private_db = td / "core.db", td / "private.db"
        identities = build_temp_core(core_db)
        build_temp_private(private_db)
        svc = PortfolioService(core_db, private_db)
        svc.create_account("paper")
        return svc, identities, tmp

    def test_identity_resolve_ts_code(self):
        """ts_code 600519.SH -> exactly one instrument."""
        svc, ids, tmp = self._fresh()
        try:
            r = svc.resolve_instrument("600519.SH")
            self.assertEqual(r["instrument_uid"], ids[0]["instrument_uid"])
            self.assertEqual(r["entity_name"], "贵州茅台")
            self.assertEqual(r["exchange_code"], "XSHG")
        finally:
            tmp.cleanup()

    def test_identity_resolve_bj(self):
        svc, ids, tmp = self._fresh()
        try:
            r = svc.resolve_instrument("430047.BJ")
            self.assertEqual(r["instrument_uid"], ids[2]["instrument_uid"])
            self.assertEqual(r["exchange_code"], "XBSE")
        finally:
            tmp.cleanup()

    def test_identity_resolve_bare_ticker(self):
        svc, ids, tmp = self._fresh()
        try:
            r = svc.resolve_instrument("000001")
            self.assertEqual(r["instrument_uid"], ids[1]["instrument_uid"])
        finally:
            tmp.cleanup()

    def test_identity_unknown_fails(self):
        svc, ids, tmp = self._fresh()
        try:
            with self.assertRaises(IdentityNotFoundError):
                svc.resolve_instrument("ABC_NOT_EXIST")
            with self.assertRaises(IdentityNotFoundError):
                svc.resolve_entity("ABC_NOT_EXIST")
        finally:
            tmp.cleanup()

    def test_r2_universe_01(self):
        """R2-UNIVERSE: union + dedupe + source preservation."""
        svc, ids, tmp = self._fresh()
        try:
            # position on 600519 + watchlist 600519 + watchlist 000001 + entity
            svc.set_position("paper", "600519.SH", quantity=100)
            svc.create_watchlist("CORE")
            svc.add_watchlist_item("CORE", instrument="600519.SH")
            svc.add_watchlist_item("CORE", instrument="000001.SZ")
            svc.add_watchlist_item("CORE", entity=ids[0]["entity_uid"])
            uni = svc.get_monitoring_universe()
            inst_uids = {i["uid"] for i in uni["instruments"]}
            self.assertEqual(len(uni["instruments"]), 2)  # dedupe 600519
            self.assertEqual(len(uni["entities"]), 1)
            # 600519 appears in position + watchlist -> BOTH
            by_uid = {i["uid"]: i for i in uni["instruments"]}
            self.assertEqual(by_uid[ids[0]["instrument_uid"]]["source"], "BOTH")
            self.assertEqual(by_uid[ids[1]["instrument_uid"]]["source"], "WATCHLIST")
            self.assertEqual(uni["entities"][0]["source"], "WATCHLIST")
        finally:
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
