import unittest
from datetime import datetime

import pytz

from _test_support import reset_database  # noqa: F401
from evercore.time_utils import coerce_utc, now_utc


class TimeUtilsTests(unittest.TestCase):
    def test_now_utc_is_timezone_aware(self):
        value = now_utc()
        self.assertIsNotNone(value.tzinfo)
        self.assertEqual(value.tzinfo, pytz.UTC)

    def test_coerce_utc_localizes_naive(self):
        naive = datetime(2026, 1, 2, 3, 4, 5)
        coerced = coerce_utc(naive)
        self.assertIsNotNone(coerced)
        self.assertEqual(coerced.tzinfo, pytz.UTC)

    def test_coerce_utc_converts_non_utc_timezone(self):
        eastern = pytz.timezone("US/Eastern")
        local = eastern.localize(datetime(2026, 1, 2, 3, 4, 5))
        coerced = coerce_utc(local)
        self.assertIsNotNone(coerced)
        self.assertEqual(coerced.tzinfo, pytz.UTC)

    def test_coerce_utc_none_passthrough(self):
        self.assertIsNone(coerce_utc(None))


if __name__ == "__main__":
    unittest.main()
