"""T9 Dashboard deploy governance tests (DB-D015 / 2026-08-27 governance fix).

Guards against regression of the dashboard auto-sync deploy path:

- T-DASH-ROOT-01: root-level dashboard files (index.html / chart.umd.min.js /
  data/dashboard_data.js) must NOT be tracked by git (governance: prototype
  lives only in prototypes/dividend_dashboard/).
- T-DASH-ROOT-02: .gitignore contains root-anchored ignore patterns for those
  paths (belt-and-suspenders so `git add -A` in any clone cannot re-stage them).
- T-DASH-PROTO-01: prototype files exist at prototypes/dividend_dashboard/
  and are tracked by git (prototype remains complete/usable).

These tests are pure repo-state checks: they do NOT touch production DBs
(data/runtime/core.db, data/private/private.db) or any data pipeline.
"""

import subprocess
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Root-level dashboard paths that must never be tracked again (governance).
FORBIDDEN_ROOT_PATHS = (
    "index.html",
    "chart.umd.min.js",
    "data/dashboard_data.js",
)

# Canonical prototype location (single source of truth).
PROTOTYPE_DIR = PROJECT_ROOT / "prototypes" / "dividend_dashboard"
PROTOTYPE_FILES = (
    "index.html",
    "chart.umd.min.js",
    "data/dashboard_data.js",
)


def _git_ls_files() -> set:
    out = subprocess.run(
        ["git", "ls-files"], cwd=PROJECT_ROOT,
        capture_output=True, text=True, check=True,
    )
    return set(line for line in out.stdout.splitlines() if line)


class TestDashboardDeployGovernance(unittest.TestCase):
    """Repo-state guards for the dashboard deploy path."""

    @classmethod
    def setUpClass(cls):
        cls.tracked = _git_ls_files()

    def test_root_dashboard_files_not_tracked(self):
        """T-DASH-ROOT-01: no root-level dashboard copies in git."""
        for rel in FORBIDDEN_ROOT_PATHS:
            self.assertNotIn(
                rel, self.tracked,
                f"root-level dashboard file is tracked: {rel} "
                f"(governance: must live in prototypes/dividend_dashboard/)",
            )

    def test_gitignore_blocks_root_dashboard_paths(self):
        """T-DASH-ROOT-02: .gitignore root-anchored patterns present."""
        gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
        for rel in FORBIDDEN_ROOT_PATHS:
            self.assertIn(
                f"/{rel}", gitignore,
                f".gitignore missing root-anchored pattern /{rel}",
            )

    def test_prototype_files_exist_and_tracked(self):
        """T-DASH-PROTO-01: prototype complete + tracked."""
        for rel in PROTOTYPE_FILES:
            p = PROTOTYPE_DIR / rel
            self.assertTrue(p.is_file(), f"prototype file missing: {p}")
            self.assertIn(
                f"prototypes/dividend_dashboard/{rel}", self.tracked,
                f"prototype file not tracked: {rel}",
            )


if __name__ == "__main__":
    sys.exit(unittest.main())
