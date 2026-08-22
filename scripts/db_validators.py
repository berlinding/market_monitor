#!/usr/bin/env python3
"""
db_validators.py — cross-db UID reference validators (stdlib only)

R1C Phase 1. private.db references core.db entities via *_uid TEXT columns
without pseudo-FKs (storage_architecture_v2 §2.2). Application layer must
validate existence against core.db before writing (migration_runner_spec §6).

These helpers are tested against TEMP databases only in this phase; never
connect to production paths.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


class CrossDbReferenceError(ValueError):
    """core uid reference does not exist / is invalid."""

    def __init__(self, uid: str, table: str, detail: str = ""):
        self.uid = uid
        self.table = table
        self.detail = detail
        super().__init__(
            f"cross-db reference error: uid={uid!r} not valid/existing "
            f"in core.{table}{': ' + detail if detail else ''}"
        )


def _validate_uuid_format(uid: str, table: str) -> None:
    if not isinstance(uid, str) or not UUID_RE.match(uid):
        raise CrossDbReferenceError(uid, table, "invalid UUIDv4 format")


def _exists(conn: sqlite3.Connection, table: str, uid_col: str, uid: str) -> bool:
    row = conn.execute(
        f"SELECT 1 FROM {table} WHERE {uid_col} = ?", (uid,)
    ).fetchone()
    return row is not None


def ensure_entity_uid(conn: sqlite3.Connection, entity_uid: str) -> bool:
    """True if entity_uid exists in core.entities; raises CrossDbReferenceError otherwise."""
    _validate_uuid_format(entity_uid, "entities")
    if _exists(conn, "entities", "entity_uid", entity_uid):
        return True
    raise CrossDbReferenceError(entity_uid, "entities")


def ensure_instrument_uid(conn: sqlite3.Connection, instrument_uid: str) -> bool:
    _validate_uuid_format(instrument_uid, "instruments")
    if _exists(conn, "instruments", "instrument_uid", instrument_uid):
        return True
    raise CrossDbReferenceError(instrument_uid, "instruments")


def ensure_event_uid(conn: sqlite3.Connection, event_uid: str) -> bool:
    _validate_uuid_format(event_uid, "events")
    if _exists(conn, "events", "event_uid", event_uid):
        return True
    raise CrossDbReferenceError(event_uid, "events")


def ensure_analysis_uid(conn: sqlite3.Connection, analysis_uid: str) -> bool:
    _validate_uuid_format(analysis_uid, "event_analysis")
    if _exists(conn, "event_analysis", "analysis_uid", analysis_uid):
        return True
    raise CrossDbReferenceError(analysis_uid, "event_analysis")


def open_core_readonly(core_db_path: Path) -> sqlite3.Connection:
    """Open core.db read-only for validation (URI mode)."""
    uri = f"file:{core_db_path.resolve()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn
