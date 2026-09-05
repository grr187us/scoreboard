"""EST/EDT conversion and human-readable formatting for operator timestamps."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from scoreboard.infrastructure.local_time import format_local_timestamp


class LocalTimeTests(unittest.TestCase):
    def test_summer_utc_timestamp_renders_as_edt(self) -> None:
        value = "2026-09-05T14:41:00+00:00"

        self.assertEqual(
            format_local_timestamp(value), "September 5, 2026 at 10:41 AM EDT"
        )

    def test_winter_utc_timestamp_renders_as_est(self) -> None:
        value = "2026-01-05T14:41:00+00:00"

        self.assertEqual(
            format_local_timestamp(value), "January 5, 2026 at 9:41 AM EST"
        )

    def test_midnight_and_noon_boundaries(self) -> None:
        # Midnight Eastern is 04:00 UTC during EDT (UTC-4).
        self.assertEqual(
            format_local_timestamp("2026-07-04T04:00:00+00:00"),
            "July 4, 2026 at 12:00 AM EDT",
        )
        # Noon Eastern is 16:00 UTC during EDT.
        self.assertEqual(
            format_local_timestamp("2026-07-04T16:00:00+00:00"),
            "July 4, 2026 at 12:00 PM EDT",
        )

    def test_microseconds_and_offset_suffix_are_accepted(self) -> None:
        self.assertEqual(
            format_local_timestamp("2026-09-05T14:41:00.123456+00:00"),
            "September 5, 2026 at 10:41 AM EDT",
        )

    def test_spring_forward_boundary_2026(self) -> None:
        # 2026-03-08 07:00 UTC is 01:00 EST (still standard time, one hour
        # before the 2:00 am local clocks skip to 3:00 am).
        self.assertEqual(
            format_local_timestamp("2026-03-08T06:59:00+00:00"),
            "March 8, 2026 at 1:59 AM EST",
        )
        # 2026-03-08 07:00 UTC is 03:00 EDT: the skipped local hour is gone,
        # and the offset has already moved to UTC-4.
        self.assertEqual(
            format_local_timestamp("2026-03-08T07:00:00+00:00"),
            "March 8, 2026 at 3:00 AM EDT",
        )

    def test_fall_back_boundary_2026(self) -> None:
        # 2026-11-01 05:30 UTC is 01:30 EDT, the last half hour before clocks
        # repeat 1:00-2:00 am local time.
        self.assertEqual(
            format_local_timestamp("2026-11-01T05:30:00+00:00"),
            "November 1, 2026 at 1:30 AM EDT",
        )
        # An hour later is 01:30 EST: the same local clock face, now standard
        # time and one hour further behind UTC.
        self.assertEqual(
            format_local_timestamp("2026-11-01T06:30:00+00:00"),
            "November 1, 2026 at 1:30 AM EST",
        )

    def test_none_input_returns_none(self) -> None:
        self.assertIsNone(format_local_timestamp(None))

    def test_naive_datetime_is_treated_as_utc(self) -> None:
        naive = datetime(2026, 9, 5, 14, 41, 0)

        self.assertEqual(
            format_local_timestamp(naive), "September 5, 2026 at 10:41 AM EDT"
        )

    def test_aware_datetime_input_is_accepted_directly(self) -> None:
        aware = datetime(2026, 9, 5, 14, 41, 0, tzinfo=timezone.utc)

        self.assertEqual(
            format_local_timestamp(aware), "September 5, 2026 at 10:41 AM EDT"
        )

    def test_unparsable_string_is_returned_unchanged(self) -> None:
        self.assertEqual(format_local_timestamp("not a timestamp"), "not a timestamp")

    def test_empty_string_is_returned_unchanged(self) -> None:
        self.assertEqual(format_local_timestamp(""), "")


if __name__ == "__main__":
    unittest.main()
