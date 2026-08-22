"""T6 Privacy boundary tests — core.db must not contain private data;
private.db must not contain credentials. Schema-level inspection only
(no API.txt scanning, no production DB access)."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import migrate  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS = PROJECT_ROOT / "docs" / "database" / "sql" / "migrations"

CORE_ALLOWED_TABLES = {
    "entities", "entity_identifiers", "instruments", "instrument_identifiers",
    "data_sources", "datasets", "dataset_sources", "ingest_runs",
    "raw_artifacts", "data_gaps", "market_prices_daily", "events",
    "event_entities", "event_instruments", "event_evidence", "event_analysis",
    "schema_migrations",
}
PRIVATE_ALLOWED_TABLES = {
    "accounts", "positions", "watchlists", "watchlist_items",
    "investment_theses", "event_thesis_analysis", "alerts", "schema_migrations",
}

# patterns that must never appear in core.db schema
# NOTE: core.event_analysis.raw_output IS allowed (generic analysis raw output);
# private raw LLM output lives in private.event_thesis_analysis.raw_output
# and is covered by the private-DB test below.
CORE_FORBIDDEN_PATTERNS = [
    "account", "position", "avg_cost", "cost_basis", "quantity",
    "watchlist", "thesis", "impact_direction", "impact_severity",
    "alert", "channel", "rule_ref",
]

# patterns that must never appear as private.db columns (credential leakage)
PRIVATE_FORBIDDEN_PATTERNS = [
    "password", "token", "credential", "secret", "api_key", "apikey",
]


def build_core(td: str):
    db = Path(td) / "core.db"
    migrate.run_migrations(db, MIGRATIONS / "core", "C", db_label="core",
                           no_backup_gate=True)
    return migrate.connect_db(db)


def build_private(td: str):
    db = Path(td) / "private.db"
    migrate.run_migrations(db, MIGRATIONS / "private", "P", db_label="private",
                           no_backup_gate=True)
    return migrate.connect_db(db)


class TestCoreHasNoPrivateData(unittest.TestCase):
    def test_core_tables_are_whitelist_only(self):
        with tempfile.TemporaryDirectory() as td:
            conn = build_core(td)
            try:
                tables = {
                    r[0]
                    for r in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                self.assertEqual(tables, CORE_ALLOWED_TABLES)
            finally:
                conn.close()

    def test_core_has_no_private_columns(self):
        with tempfile.TemporaryDirectory() as td:
            conn = build_core(td)
            try:
                tables = [
                    r[0]
                    for r in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                ]
                for t in tables:
                    cols = [
                        c[1]
                        for c in conn.execute(f"PRAGMA table_info('{t}')")
                    ]
                    for col in cols:
                        for pat in CORE_FORBIDDEN_PATTERNS:
                            self.assertNotIn(
                                pat.lower(), col.lower(),
                                f"core table {t}.{col} leaks private pattern {pat}",
                            )
            finally:
                conn.close()


class TestPrivateHasNoCredentials(unittest.TestCase):
    def test_private_has_no_credential_columns(self):
        with tempfile.TemporaryDirectory() as td:
            conn = build_private(td)
            try:
                tables = [
                    r[0]
                    for r in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                ]
                self.assertEqual(set(tables), PRIVATE_ALLOWED_TABLES)
                for t in tables:
                    cols = [
                        c[1]
                        for c in conn.execute(f"PRAGMA table_info('{t}')")
                    ]
                    for col in cols:
                        for pat in PRIVATE_FORBIDDEN_PATTERNS:
                            self.assertNotIn(
                                pat.lower(), col.lower(),
                                f"private table {t}.{col} leaks credential pattern {pat}",
                            )
            finally:
                conn.close()

    def test_private_stores_uid_refs_not_core_tables(self):
        with tempfile.TemporaryDirectory() as td:
            conn = build_private(td)
            try:
                tables = {
                    r[0]
                    for r in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                # private.db must not duplicate core-only tables
                core_dup = tables & {
                    "entities", "instruments", "events", "market_prices_daily",
                    "raw_artifacts", "data_sources", "datasets",
                }
                self.assertEqual(core_dup, set())
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
