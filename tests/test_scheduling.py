import datetime
import unittest

from aura.scheduling import milliseconds_until, next_wall_clock_datetime, stop_datetime_after_start


class SchedulingTests(unittest.TestCase):
    def test_next_wall_clock_datetime_uses_today_when_time_is_later(self):
        now = datetime.datetime(2026, 5, 25, 9, 30, 45, tzinfo=datetime.timezone.utc)

        scheduled = next_wall_clock_datetime(now, 10, 15)

        self.assertEqual(scheduled, datetime.datetime(2026, 5, 25, 10, 15, tzinfo=datetime.timezone.utc))

    def test_next_wall_clock_datetime_rolls_past_time_to_tomorrow(self):
        now = datetime.datetime(2026, 5, 25, 9, 30, 45, tzinfo=datetime.timezone.utc)

        scheduled = next_wall_clock_datetime(now, 8, 0)

        self.assertEqual(scheduled, datetime.datetime(2026, 5, 26, 8, 0, tzinfo=datetime.timezone.utc))

    def test_next_wall_clock_datetime_can_start_inside_current_minute(self):
        now = datetime.datetime(2026, 5, 25, 9, 30, 45, tzinfo=datetime.timezone.utc)

        scheduled = next_wall_clock_datetime(now, 9, 30)

        self.assertEqual(scheduled, now)

    def test_stop_datetime_after_start_stays_after_start(self):
        start_at = datetime.datetime(2026, 5, 25, 23, 50, tzinfo=datetime.timezone.utc)

        scheduled = stop_datetime_after_start(start_at, 0, 15)

        self.assertEqual(scheduled, datetime.datetime(2026, 5, 26, 0, 15, tzinfo=datetime.timezone.utc))

    def test_stop_datetime_after_start_rolls_equal_time_to_next_day(self):
        start_at = datetime.datetime(2026, 5, 25, 9, 30, tzinfo=datetime.timezone.utc)

        scheduled = stop_datetime_after_start(start_at, 9, 30)

        self.assertEqual(scheduled, datetime.datetime(2026, 5, 26, 9, 30, tzinfo=datetime.timezone.utc))

    def test_milliseconds_until_never_returns_negative_interval(self):
        now = datetime.datetime(2026, 5, 25, 9, 30, 1, tzinfo=datetime.timezone.utc)
        target = datetime.datetime(2026, 5, 25, 9, 30, tzinfo=datetime.timezone.utc)

        self.assertEqual(milliseconds_until(now, target), 0)


if __name__ == "__main__":
    unittest.main()
