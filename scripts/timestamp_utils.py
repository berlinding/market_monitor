#!/usr/bin/env python3
"""
timestamp_utils.py — UTC / legacy timestamp utilities (stdlib only)

Covers R1C Phase 1 / 1.1 / 1.2 / Phase 2 helper semantics.

Frozen contract (DB-D027): instants are TEXT UTC ISO-8601 with
'Z' suffix (e.g. 2026-08-16T15:39:29Z). Legacy fetch_log.fetched_at is a
NAIVE LOCAL timestamp (datetime.now().isoformat(timespec="seconds")) and must
NOT be blindly relabelled as UTC (S2 / DB-D035).

Phase 2 (real-data staging): legacy timezone CONFIRMED = Asia/Shanghai;
convert_legacy_naive_to_utc() is used to backfill ingest_runs.started_at.
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class TimestampResolutionError(ValueError):
    """Legacy timestamp timezone could not be reliably determined."""


def utc_now_iso() -> str:
    """Current UTC time as YYYY-MM-DDTHH:MM:SSZ (no +00:00, per frozen contract)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def convert_legacy_naive_to_utc(raw_timestamp: str, timezone_name: str | None) -> str:
    """
    Convert a naive local timestamp to UTC ISO-8601 with Z.

    raw_timestamp  : e.g. '2026-08-16T23:39:29' (legacy fetch_log.fetched_at)
    timezone_name  : IANA zone, e.g. 'Asia/Shanghai'. Must be provided;
                     None or unknown -> TimestampResolutionError (never guess).

    Example: ('2026-08-16T23:39:29', 'Asia/Shanghai') -> '2026-08-16T15:39:29Z'
    """
    if not timezone_name:
        raise TimestampResolutionError(
            "legacy timestamp timezone is UNRESOLVED: refusing to guess UTC"
        )
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise TimestampResolutionError(
            f"unknown IANA timezone: {timezone_name!r}"
        ) from exc

    # 'Z' suffix or explicit offset input: already aware -> normalize
    raw = raw_timestamp.strip()
    if raw.endswith("Z"):
        naive = datetime.fromisoformat(raw[:-1])
        aware = naive.replace(tzinfo=timezone.utc)
    elif "+" in raw[10:] or "-" in raw[10:]:  # contains an offset
        aware = datetime.fromisoformat(raw)
    else:
        # naive local -> attach requested zone
        naive = datetime.fromisoformat(raw)
        aware = naive.replace(tzinfo=zone)

    return aware.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
