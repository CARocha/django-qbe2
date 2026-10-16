from datetime import UTC, datetime, time, timedelta

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from django_qbe2.scheduling import next_run_at, retry_at


class ScheduledTimeTests(SimpleTestCase):
    def test_daily_next_run_uses_local_timezone(self):
        next_run = next_run_at(
            frequency="daily",
            local_time=time(9, 30),
            timezone_name="America/Managua",
            weekday=None,
            after=datetime(2026, 10, 16, 15, 0, tzinfo=UTC),
        )

        self.assertEqual(
            next_run,
            datetime(2026, 10, 16, 15, 30, tzinfo=UTC),
        )

    def test_weekly_requires_and_uses_weekday(self):
        after = datetime(2026, 10, 16, 15, 0, tzinfo=UTC)
        with self.assertRaises(ValidationError):
            next_run_at(
                frequency="weekly",
                local_time=time(9),
                timezone_name="America/Managua",
                weekday=None,
                after=after,
            )

        next_run = next_run_at(
            frequency="weekly",
            local_time=time(9, 30),
            timezone_name="America/Managua",
            weekday=0,
            after=after,
        )

        self.assertEqual(next_run, datetime(2026, 10, 19, 15, 30, tzinfo=UTC))

    def test_invalid_zone_and_recurrence_are_rejected(self):
        base = {
            "frequency": "daily",
            "local_time": time(9),
            "timezone_name": "America/Managua",
            "weekday": None,
            "after": datetime(2026, 10, 16, 15, tzinfo=UTC),
        }
        for changes in (
            {"frequency": "hourly"},
            {"timezone_name": "Mars/Olympus"},
            {"frequency": "daily", "weekday": 2},
            {"frequency": "weekly", "weekday": 7},
            {"frequency": "weekly", "weekday": -1},
            {"after": datetime(2026, 10, 16, 15)},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                next_run_at(**(base | changes))

    def test_daily_and_weekly_next_run_across_dst_gap_and_fold(self):
        before_gap = datetime(2026, 3, 8, 6, 0, tzinfo=UTC)
        gap_run = next_run_at(
            frequency="daily",
            local_time=time(2, 30),
            timezone_name="America/New_York",
            weekday=None,
            after=before_gap,
        )
        self.assertEqual(gap_run, datetime(2026, 3, 8, 7, 0, tzinfo=UTC))

        before_fold = datetime(2026, 11, 1, 4, 0, tzinfo=UTC)
        fold_run = next_run_at(
            frequency="weekly",
            local_time=time(1, 30),
            timezone_name="America/New_York",
            weekday=6,
            after=before_fold,
        )
        self.assertEqual(fold_run, datetime(2026, 11, 1, 5, 30, tzinfo=UTC))

    def test_retry_backoff_is_bounded_and_stops_after_three_attempts(self):
        after = datetime(2026, 10, 16, 15, 0, tzinfo=UTC)
        self.assertEqual(retry_at(attempt=1, after=after), after + timedelta(minutes=5))
        self.assertEqual(
            retry_at(attempt=2, after=after), after + timedelta(minutes=10)
        )
        self.assertIsNone(retry_at(attempt=3, after=after))
        for attempt in (0, -1, True):
            with self.subTest(attempt=attempt), self.assertRaises(ValidationError):
                retry_at(attempt=attempt, after=after)
