#!/usr/bin/env python3
"""
date_utils.py — canonical date normalization (stdlib only)

R1C Phase 1.2 (DB-D050/DB-D051).

Canonical date contract:
  * ALL canonical "date" fields MUST be YYYY-MM-DD (e.g. 2026-08-14, 1991-04-03).
  * Provider/raw artifacts keep their original strings (e.g. 20260814) untouched;
    normalization happens only at the canonical boundary.

normalize_date() accepts YYYYMMDD or YYYY-MM-DD and returns YYYY-MM-DD,
validating real calendar dates via datetime.strptime (no naive slicing).
"""

from __future__ import annotations

from datetime import datetime


class DateNormalizationError(ValueError):
    """Input is not a valid calendar date in an accepted format."""


def normalize_date(raw: str | None) -> str:
    """
    Normalize a compact (YYYYMMDD) or dash-separated (YYYY-MM-DD) date to
    the canonical YYYY-MM-DD form.

    Raises DateNormalizationError (with the original input in the message) for:
      * None / empty / whitespace
      * non-8-digit / non-10-char input
      * impossible calendar dates (20260230, 20260229 in non-leap year 2026)
      * separators other than '-'

    Examples:
      normalize_date("20260814")  -> "2026-08-14"
      normalize_date("2026-08-14")-> "2026-08-14"
      normalize_date("20240229")  -> "2024-02-29"   (2024 is a leap year)
      normalize_date("19910403")  -> "1991-04-03"
    """
    if raw is None:
        raise DateNormalizationError("date is None")
    s = str(raw).strip()
    if not s:
        raise DateNormalizationError(f"date is empty/whitespace: {raw!r}")

    if "-" in s:
        # canonical-ish form: YYYY-MM-DD only
        if len(s) != 10 or s.count("-") != 2:
            raise DateNormalizationError(f"invalid date format: {raw!r}")
        try:
            return datetime.strptime(s, "%Y-%m-%d").strftime("%Y-%m-%d")
        except ValueError as exc:
            raise DateNormalizationError(f"invalid calendar date: {raw!r}") from exc

    # compact form: YYYYMMDD
    if len(s) != 8 or not s.isdigit():
        raise DateNormalizationError(f"invalid compact date: {raw!r}")
    try:
        return datetime.strptime(s, "%Y%m%d").strftime("%Y-%m-%d")
    except ValueError as exc:
        raise DateNormalizationError(f"invalid calendar date: {raw!r}") from exc


def is_canonical_date(value: str | None) -> bool:
    """True if value is already a canonical YYYY-MM-DD calendar date."""
    try:
        return normalize_date(value) == value
    except DateNormalizationError:
        return False
