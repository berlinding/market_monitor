#!/usr/bin/env python3
"""
migrate.py — Market Monitor schema migration runner (stdlib only)

R1C Phase 1 implementation of migration_runner_spec_v1.md.

Usage:
  python3 scripts/migrate.py --db core --plan
  python3 scripts/migrate.py --db core
  python3 scripts/migrate.py --db private
  python3 scripts/migrate.py --db all --plan
  python3 scripts/migrate.py --status

Contract highlights (DB-D034 / DB-D029 / DB-D030):
  * BEGIN IMMEDIATE is prepended to each migration script and executed via
    executescript(); migration files must NOT contain BEGIN/COMMIT/ROLLBACK.
  * schema_migrations record is written in the same transaction via a
    parameterized execute(); conn.commit() is the only commit point;
    any exception -> conn.rollback().
  * SHA-256 checksum per migration file; applied + modified file -> hard error.
  * core.db and private.db have separate migration histories (Cxxxx / Pxxxx).
  * PRODUCTION_WRITES_ENABLED = False: writing to data/runtime/core.db or
    data/private/private.db is refused in this phase.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MIGRATIONS_DIR = PROJECT_ROOT / "docs" / "database" / "sql" / "migrations"
DEFAULT_DB_PATHS = {
    "core": PROJECT_ROOT / "data" / "runtime" / "core.db",
    "private": PROJECT_ROOT / "data" / "private" / "private.db",
}

# ---------------------------------------------------------------------------
# Safety guard (R1C Phase 1): production writes are NOT authorized.
# ---------------------------------------------------------------------------
PRODUCTION_WRITES_ENABLED = False
PRODUCTION_PATHS = {
    "core": DEFAULT_DB_PATHS["core"].resolve(),
    "private": DEFAULT_DB_PATHS["private"].resolve(),
}

# schema_migrations bootstrap — single definition used by the runner.
# C0001/P0001 contain the same IF NOT EXISTS DDL; a test asserts consistency.
SCHEMA_MIGRATIONS_DDL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    migration_id TEXT PRIMARY KEY,
    checksum     TEXT    NOT NULL CHECK (length(checksum) = 64),
    applied_at   TEXT    NOT NULL,
    description  TEXT,
    execution_ms INTEGER
);
"""

MIGRATION_FILENAME_RE = re.compile(r"^(?P<prefix>[CP])(?P<num>\d{4})_(?P<name>[a-z0-9_]+)\.sql$")

# Roughly detect transaction-control keywords outside comments.
# We strip line comments (--) and block comments (/* */) before matching,
# so "COMMIT" appearing only inside a comment is not a false positive.
_TX_TOKEN_RE = re.compile(r"\b(BEGIN|COMMIT|ROLLBACK)\b", re.IGNORECASE)


class MigrationError(Exception):
    """Base class for migration runner errors."""


class MigrationChecksumError(MigrationError):
    """Applied migration file was modified; refusing to replay."""


class MigrationFileError(MigrationError):
    """Migration file name or content is invalid."""


class BackupGateError(MigrationError):
    """Backup requirement not satisfied before applying to an existing DB."""


class ProductionWriteNotAuthorizedError(MigrationError):
    """Attempted to write a production database path in this phase."""


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
def utc_now_iso() -> str:
    """Return current UTC time as YYYY-MM-DDTHH:MM:SSZ (frozen contract)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def strip_sql_comments(sql: str) -> str:
    """Remove -- line comments and /* */ block comments (approximate but safe
    for our DDL files, which contain no string literals with comment markers)."""
    lines = []
    in_block = False
    for raw_line in sql.splitlines():
        line = raw_line
        out = []
        i = 0
        while i < len(line):
            if in_block:
                idx = line.find("*/", i)
                if idx == -1:
                    break
                in_block = False
                i = idx + 2
                continue
            if line[i : i + 2] == "/*":
                in_block = True
                i += 2
                continue
            if line[i : i + 2] == "--":
                break
            out.append(line[i])
            i += 1
        lines.append("".join(out))
    return "\n".join(lines)


def validate_migration_content(migration_id: str, sql: str) -> None:
    """Reject migration files that manage their own transactions."""
    stripped = strip_sql_comments(sql)
    for match in _TX_TOKEN_RE.finditer(stripped):
        raise MigrationFileError(
            f"{migration_id}: migration file must not contain "
            f"transaction control ({match.group(1)!r}); "
            "transactions are owned by the runner (DB-D034)."
        )


def iter_migration_files(migrations_dir: Path, prefix: str):
    """Yield (migration_id, number, path) sorted by number for one DB prefix."""
    files = []
    for path in sorted(migrations_dir.glob(f"{prefix}*.sql")):
        m = MIGRATION_FILENAME_RE.match(path.name)
        if not m:
            raise MigrationFileError(f"invalid migration filename: {path.name}")
        if m.group("prefix") != prefix:
            raise MigrationFileError(f"wrong prefix in {path.name} for db={prefix.lower()}")
        files.append((m.group("prefix") + m.group("num"), int(m.group("num")), path))
    files.sort(key=lambda t: t[1])
    # continuity check (detect gaps / duplicates)
    for i, (_, num, _) in enumerate(files, start=1):
        if num != i:
            raise MigrationFileError(
                f"non-contiguous migration numbers in {prefix} series: "
                f"expected {i}, found {num}"
            )
    return files


# ---------------------------------------------------------------------------
# DB / schema_migrations
# ---------------------------------------------------------------------------
def ensure_schema_migrations(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_MIGRATIONS_DDL)


def connect_db(db_path: Path, create: bool = False) -> sqlite3.Connection:
    if not create and not db_path.exists():
        raise MigrationError(f"database does not exist: {db_path}")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    return conn


def load_applied(conn: sqlite3.Connection, readonly: bool = False) -> dict[str, str]:
    if readonly:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='schema_migrations'"
        ).fetchone()
        if not row:
            return {}
        return {
            mid: checksum
            for mid, checksum in conn.execute(
                "SELECT migration_id, checksum FROM schema_migrations"
            )
        }
    ensure_schema_migrations(conn)
    return {
        mid: checksum
        for mid, checksum in conn.execute(
            "SELECT migration_id, checksum FROM schema_migrations"
        )
    }


# ---------------------------------------------------------------------------
# Core migration execution (DB-D034 transaction contract)
# ---------------------------------------------------------------------------
def apply_migration(
    conn: sqlite3.Connection,
    migration_id: str,
    sql: str,
    description: str,
) -> None:
    validate_migration_content(migration_id, sql)
    checksum = sha256_bytes(sql.encode("utf-8"))
    migration_script = "BEGIN IMMEDIATE;\n" + sql
    started = time.monotonic()
    try:
        conn.executescript(migration_script)
        conn.execute(
            "INSERT INTO schema_migrations"
            "(migration_id, checksum, applied_at, description, execution_ms)"
            " VALUES (?, ?, ?, ?, ?)",
            (migration_id, checksum, utc_now_iso(), description,
             int((time.monotonic() - started) * 1000)),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        # failure verification: no record, no partial objects (checked by tests)
        raise


def run_migrations(
    db_path: Path,
    migrations_dir: Path,
    prefix: str,
    db_label: str,
    plan_only: bool = False,
    no_backup_gate: bool = False,
) -> list[dict]:
    """Apply (or plan) migrations for one database. Returns status rows."""
    files = iter_migration_files(migrations_dir, prefix)

    if plan_only:
        if not db_path.exists():
            return [
                {
                    "db": db_label,
                    "migration_id": mid,
                    "status": "PENDING",
                    "checksum": sha256_bytes(path.read_bytes()),
                    "note": "DB_NOT_CREATED",
                }
                for mid, _, path in files
            ]
        # read-only: never create/write anything in plan mode
        conn = sqlite3.connect(
            f"file:{db_path.resolve()}?mode=ro", uri=True, isolation_level=None
        )
        try:
            applied = load_applied(conn, readonly=True)
        finally:
            conn.close()
        rows = []
        for mid, _, path in files:
            checksum = sha256_bytes(path.read_bytes())
            if mid in applied:
                status = (
                    "APPLIED" if applied[mid] == checksum else "CHECKSUM_MISMATCH"
                )
            else:
                status = "PENDING"
            rows.append({"db": db_label, "migration_id": mid,
                         "status": status, "checksum": checksum})
        return rows

    # --- actual execution ---
    resolved = db_path.resolve()
    if resolved in PRODUCTION_PATHS.values() and not PRODUCTION_WRITES_ENABLED:
        raise ProductionWriteNotAuthorizedError(
            f"writing production database path is not authorized in this phase: {db_path}"
        )

    create_new = not db_path.exists()
    if not create_new and not no_backup_gate:
        backup_marker = db_path.with_name(db_path.name + ".backup.sha256")
        if not backup_marker.exists():
            raise BackupGateError(
                f"backup gate: no backup marker {backup_marker.name} found for existing DB; "
                "pass --no-backup-gate only for disposable temp DBs."
            )

    conn = connect_db(db_path, create=create_new)
    rows = []
    try:
        applied = load_applied(conn)
        for mid, _, path in files:
            sql = path.read_text(encoding="utf-8")
            checksum = sha256_bytes(sql.encode("utf-8"))
            if mid in applied:
                if applied[mid] == checksum:
                    rows.append({"db": db_label, "migration_id": mid,
                                 "status": "SKIP", "checksum": checksum})
                    continue
                raise MigrationChecksumError(
                    f"{mid}: applied migration file changed (checksum mismatch); "
                    "refusing to replay. Create a new migration instead."
                )
            apply_migration(conn, mid, sql, description=path.stem)
            rows.append({"db": db_label, "migration_id": mid,
                         "status": "APPLIED", "checksum": checksum})
    finally:
        conn.close()
    return rows


# ---------------------------------------------------------------------------
# Status / CLI
# ---------------------------------------------------------------------------
def show_status(db_path: Path, db_label: str, migrations_dir: Path, prefix: str) -> None:
    if not db_path.exists():
        print(f"[{db_label}] {db_path}  ->  NOT_CREATED")
        return
    conn = sqlite3.connect(
        f"file:{db_path.resolve()}?mode=ro", uri=True, isolation_level=None
    )
    try:
        applied = load_applied(conn, readonly=True)
    finally:
        conn.close()
    files = iter_migration_files(migrations_dir, prefix)
    pending = []
    mismatches = []
    for mid, _, path in files:
        checksum = sha256_bytes(path.read_bytes())
        if mid not in applied:
            pending.append(mid)
        elif applied[mid] != checksum:
            mismatches.append(mid)
    latest = max(applied) if applied else None
    print(f"[{db_label}] {db_path}")
    print(f"  migration count applied : {len(applied)}")
    print(f"  latest migration        : {latest}")
    print(f"  pending                 : {pending if pending else 'none'}")
    print(f"  checksum mismatch       : {mismatches if mismatches else 'none'}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Market Monitor migration runner (stdlib)")
    p.add_argument("--db", choices=["core", "private", "all"], default="core")
    p.add_argument("--plan", action="store_true", help="dry-run, never writes")
    p.add_argument("--status", action="store_true", help="show migration status")
    p.add_argument("--db-path", help="override database path (default per --db)")
    p.add_argument("--migrations-dir", default=str(DEFAULT_MIGRATIONS_DIR),
                   help="migrations root directory")
    p.add_argument("--no-backup-gate", action="store_true",
                   help="skip backup gate (disposable temp DBs only)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    migrations_dir = Path(args.migrations_dir)
    targets = ["core", "private"] if args.db == "all" else [args.db]

    if args.status:
        for label in targets:
            db_path = (
                Path(args.db_path) if args.db_path
                else DEFAULT_DB_PATHS[label]
            )
            prefix = "C" if label == "core" else "P"
            show_status(db_path, label, migrations_dir / label, prefix)
        return 0

    all_rows = []
    try:
        for label in targets:
            db_path = (
                Path(args.db_path) if args.db_path
                else DEFAULT_DB_PATHS[label]
            )
            prefix = "C" if label == "core" else "P"
            rows = run_migrations(
                db_path,
                migrations_dir / label,
                prefix,
                db_label=label,
                plan_only=args.plan,
                no_backup_gate=args.no_backup_gate,
            )
            all_rows.extend(rows)
    except (MigrationError, sqlite3.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    for row in all_rows:
        print(f"[{row['db']}] {row['migration_id']:>6}  {row['status']:<17} {row['checksum'][:12]}…")
    return 0


if __name__ == "__main__":
    sys.exit(main())
