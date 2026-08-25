"""T7 R1 Finalization reproducibility tests (DB-D055).

T-REPRO-GIT-METADATA-01: report reproducibility schema contains
git_commit / git_dirty / runner_sha256 / c0001_sha256 / p0001_sha256.
T-REPRO-RUNNER-HASH-01: runner_sha256 == SHA256(actual raw runner bytes).

These tests exercise the PURE helper parts only (get_git_reproducibility_state
+ build_report schema). They do NOT mutate the real repository; the real
clean-tree gate is verified by the final rehearsal itself.
"""

import hashlib
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import phase2_staging_rehearsal as ph2  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _v(vid: str, ok: bool = True, detail: str = "") -> dict:
    return {"pass": ok, "detail": detail}


def _min_report_args() -> dict:
    """Minimal-but-complete argument bundle for build_report()."""
    m7_v = {
        f"V{i}": _v(f"V{i}") for i in range(1, 19)
    }
    m0 = {"health": {"ok": True}, "info": {"row_count": 3}}
    m1 = {
        "pass": True,
        "snapshot_path": str(PROJECT_ROOT / "data" / "raw" / "legacy" / "x.db"),
        "snapshot_sha256": "a" * 64,
        "manifest": {
            "row_count": 3,
            "distinct_ts_code": 2,
            "trade_date_distribution": {"20260814": 3},
        },
        "validation": {"integrity_check": True},
    }
    m2 = {
        "sha256": "b" * 64,
        "meta": {"merged_row_count": 2, "unique_ts_code_count": 2,
                 "retrieved_at_utc": "2026-08-25T00:00:00Z", "queries": []},
    }
    m3m4 = {"coverage": {"status": "PASS"}, "mapping": {"600519.SH": {"instrument_id": 1}}}
    staging = {
        "staging_dir": str(PROJECT_ROOT / "data" / "staging" / "t" / "r"),
        "core_db": str(PROJECT_ROOT / "data" / "staging" / "t" / "core.db"),
        "private_db": str(PROJECT_ROOT / "data" / "staging" / "t" / "private.db"),
        "core_migrations": {"C0001": "APPLIED"},
        "private_migrations": {"P0001": "APPLIED"},
        "core_checksums": {"C0001": "c" * 64},
        "private_checksums": {"P0001": "d" * 64},
        "core_checks": {"foreign_key_check_empty": True, "table_count": 17,
                        "table_count_ok": True, "tables": [], "schema_migrations": {}},
        "private_checks": {"foreign_key_check_empty": True, "table_count": 8,
                           "table_count_ok": True, "tables": [], "schema_migrations": {}},
        "metadata": {"source_id": 1, "dataset_id": 1},
        "artifacts": {"legacy_snapshot_artifact_id": 1, "stock_basic_artifact_id": 2},
    }
    entities = {"entities_created": 2, "instruments_created": 2,
                "identifiers_created": 4, "one_to_one_ok": True}
    m5 = {"runs_created": 1, "run_by_date": {"20260814": 1},
          "missing_dates": [], "extra_dates": [], "gate_ok": True}
    m6 = {"bars_inserted": 3, "successful_batches": ["20260814"],
          "failed_batches": [], "gate_ok": True}
    m7 = {"v_results": m7_v,
          "reconciliation": {"rows_checked": 3, "ohlc_mismatches": 0,
                             "volume_mismatches": 0, "turnover_mismatches": 0,
                             "date_mismatches": 0, "mapping_mismatches": 0}}
    return {
        "run_id": "testrun", "started_at": "2026-08-25T00:00:00Z",
        "m0": m0, "m1": m1, "m2": m2, "m3m4": m3m4, "staging": staging,
        "meta": staging["metadata"], "artifacts": staging["artifacts"],
        "entities": entities, "m5": m5, "m6": m6, "m7": m7,
        "warnings": [],
    }


class TestGitReproducibilityState(unittest.TestCase):
    """Pure helper: get_git_reproducibility_state() schema."""

    def test_state_schema_keys(self):
        """T-REPRO-GIT-METADATA-01 (helper part): all reproducibility keys present."""
        state = ph2.get_git_reproducibility_state()
        for key in ("git_commit", "git_branch", "git_dirty",
                    "runner_path", "runner_sha256",
                    "c0001_sha256", "p0001_sha256"):
            self.assertIn(key, state, f"missing reproducibility key: {key}")
        self.assertIsInstance(state["git_dirty"], bool)
        self.assertEqual(len(state["runner_sha256"]), 64)
        self.assertEqual(len(state["c0001_sha256"]), 64)
        self.assertEqual(len(state["p0001_sha256"]), 64)
        self.assertTrue(state["git_commit"])

    def test_runner_hash_matches_raw_bytes(self):
        """T-REPRO-RUNNER-HASH-01: runner_sha256 == SHA256(exact raw file bytes)."""
        state = ph2.get_git_reproducibility_state()
        self.assertEqual(state["runner_sha256"],
                         sha256_bytes(ph2.RUNNER_PATH.read_bytes()))
        self.assertEqual(state["c0001_sha256"],
                         sha256_bytes(ph2.C0001_PATH.read_bytes()))
        self.assertEqual(state["p0001_sha256"],
                         sha256_bytes(ph2.P0001_PATH.read_bytes()))
        self.assertEqual(state["runner_path"], "scripts/phase2_staging_rehearsal.py")


class TestReportReproducibilitySchema(unittest.TestCase):
    """build_report() output schema contains reproducibility fields."""

    def test_report_schema_contains_git_metadata(self):
        """T-REPRO-GIT-METADATA-01 (report part): report reproducibility schema.

        git_dirty is mocked to False: during the test run the working tree is
        necessarily dirty (the new test file itself is uncommitted), and the
        real clean-tree gate is enforced by the final rehearsal, not here.
        """
        args = _min_report_args()
        with mock.patch.object(ph2, "git_dirty", return_value=False):
            report = ph2.build_report(**args)
        self.assertEqual(report["final_result"], "PASS")
        repro = report["reproducibility"]
        for key in ("git_commit", "git_branch", "git_dirty",
                    "runner_path", "runner_sha256",
                    "c0001_sha256", "p0001_sha256"):
            self.assertIn(key, repro, f"report reproducibility missing: {key}")
        self.assertFalse(repro["git_dirty"])  # clean-tree requirement (DB-D055)
        self.assertEqual(report["git_commit"], repro["git_commit"])
        # safety block per R1 Finalization contract (§21)
        for key in ("production_core_exists", "production_private_exists",
                    "live_db_writer_used", "token_exposed", "dual_write_enabled",
                    "fetch_daily_production_behavior_modified"):
            self.assertIn(key, report["safety"], f"report safety missing: {key}")
        # report must be JSON-serializable
        json.dumps(report, sort_keys=True)

    def test_report_json_serializable_full(self):
        """Full report (incl. manifest) must survive json.dumps (T-MANIFEST-JSON style)."""
        args = _min_report_args()
        with mock.patch.object(ph2, "git_dirty", return_value=False):
            report = ph2.build_report(**args)
        blob = json.dumps(report, sort_keys=True)
        self.assertIn("reproducibility", blob)


if __name__ == "__main__":
    unittest.main()
