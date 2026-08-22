"""Canonical date contract tests (R1C Phase 1.2, DB-D050/DB-D051)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.date_utils import (  # noqa: E402
    DateNormalizationError,
    is_canonical_date,
    normalize_date,
)


class TestNormalizeDate(unittest.TestCase):
    def test_compact_to_canonical(self):
        """T-DATE-01"""
        self.assertEqual(normalize_date("20260814"), "2026-08-14")

    def test_already_canonical_passthrough(self):
        """T-DATE-02"""
        self.assertEqual(normalize_date("2026-08-14"), "2026-08-14")

    def test_leap_year_compact(self):
        """T-DATE-03: 2024 is a leap year -> 2024-02-29 valid."""
        self.assertEqual(normalize_date("20240229"), "2024-02-29")

    def test_leap_year_dash(self):
        self.assertEqual(normalize_date("2024-02-29"), "2024-02-29")

    def test_provider_style_dates(self):
        self.assertEqual(normalize_date("19910403"), "1991-04-03")
        self.assertEqual(normalize_date("20010827"), "2001-08-27")
        self.assertEqual(normalize_date("20100101"), "2010-01-01")


class TestInvalidDates(unittest.TestCase):
    def test_invalid_day_30_feb(self):
        """T-DATE-INVALID-01"""
        with self.assertRaises(DateNormalizationError):
            normalize_date("20260230")

    def test_invalid_month_13(self):
        """T-DATE-INVALID-02"""
        with self.assertRaises(DateNormalizationError):
            normalize_date("20261340")

    def test_non_leap_2026_feb29(self):
        # 2026 is NOT a leap year
        with self.assertRaises(DateNormalizationError):
            normalize_date("20260229")

    def test_alpha(self):
        """T-DATE-INVALID-03"""
        with self.assertRaises(DateNormalizationError):
            normalize_date("abcdefgh")

    def test_slash_separated(self):
        with self.assertRaises(DateNormalizationError):
            normalize_date("2026/08/14")

    def test_too_short(self):
        with self.assertRaises(DateNormalizationError):
            normalize_date("2026081")

    def test_none_empty_whitespace(self):
        """T-DATE-INVALID-04"""
        for bad in (None, "", "   "):
            with self.assertRaises(DateNormalizationError):
                normalize_date(bad)

    def test_error_message_contains_input(self):
        try:
            normalize_date("20260230")
        except DateNormalizationError as exc:
            self.assertIn("20260230", str(exc))
        else:
            self.fail("expected DateNormalizationError")


class TestIsCanonicalDate(unittest.TestCase):
    def test_true_for_canonical(self):
        self.assertTrue(is_canonical_date("2026-08-14"))
        self.assertTrue(is_canonical_date("1991-04-03"))

    def test_false_for_compact(self):
        self.assertFalse(is_canonical_date("20260814"))

    def test_false_for_invalid(self):
        self.assertFalse(is_canonical_date("20260230"))
        self.assertFalse(is_canonical_date(None))


if __name__ == "__main__":
    unittest.main()
