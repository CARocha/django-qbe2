from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, time, timedelta
from threading import Barrier

import django
from django.core.management import call_command
from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from django_qbe2.models import ScheduledReport, ScheduledReportRun
from tests.fixtures import grant_view, make_staff
from tests.models import Customer, Order
from tests.test_validation import order_payload

MAIL_SETTINGS = (
    {
        "MAILERS": {
            "default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}
        }
    }
    if django.VERSION >= (6, 1)
    else {"EMAIL_BACKEND": "django.core.mail.backends.locmem.EmailBackend"}
)


class ScheduledCommandTests(TestCase):
    def setUp(self):
        self.owner = make_staff("scheduled-command-owner")
        grant_view(self.owner, Order, Customer)

    def schedule(self, **changes):
        values = {
            "owner": self.owner,
            "name": "Daily orders",
            "definition": order_payload(),
            "page_size": 25,
            "frequency": "daily",
            "weekday": None,
            "local_time": time(9),
            "timezone": "UTC",
            "recipients": ["reports@example.com"],
            "format": "csv",
            "next_run_at": timezone.now() - timedelta(minutes=1),
        }
        values.update(changes)
        return ScheduledReport.objects.create(**values)

    def test_claim_is_unique_for_one_schedule_occurrence(self):
        from django_qbe2.scheduling import claim_due_runs

        now = datetime(2026, 10, 16, 12, tzinfo=UTC)
        schedule = self.schedule(next_run_at=now - timedelta(days=10))

        first = claim_due_runs(now=now, limit=10)
        second = claim_due_runs(now=now, limit=10)

        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])
        self.assertEqual(
            ScheduledReportRun.objects.filter(schedule=schedule).count(), 1
        )
        self.assertEqual(first[0].status, ScheduledReportRun.Status.RUNNING)

    def test_runner_processes_only_due_schedules_up_to_limit(self):
        from django_qbe2.scheduling import claim_due_runs

        now = datetime(2026, 10, 16, 12, tzinfo=UTC)
        schedules = [
            self.schedule(name=f"Daily {i}", next_run_at=now - timedelta(minutes=1))
            for i in range(3)
        ]

        runs = claim_due_runs(now=now, limit=2)

        self.assertEqual(len(runs), 2)
        self.assertEqual(ScheduledReportRun.objects.count(), 2)
        self.assertEqual(
            ScheduledReport.objects.filter(
                pk__in=[item.pk for item in schedules], next_run_at__gt=now
            ).count(),
            2,
        )

    def test_expired_lease_can_be_reclaimed(self):
        from django_qbe2.scheduling import claim_due_runs

        now = datetime(2026, 10, 16, 12, tzinfo=UTC)
        self.schedule(next_run_at=now - timedelta(minutes=1))
        first = claim_due_runs(now=now, limit=1)[0]
        ScheduledReportRun.objects.filter(pk=first.pk).update(
            lease_expires_at=now - timedelta(seconds=1)
        )

        retry = claim_due_runs(now=now, limit=1)

        self.assertEqual([run.pk for run in retry], [first.pk])
        self.assertEqual(retry[0].attempts, 2)

    def test_expired_final_lease_is_marked_terminal(self):
        from django_qbe2.scheduling import claim_due_runs

        now = datetime(2026, 10, 16, 12, tzinfo=UTC)
        self.schedule(next_run_at=now - timedelta(minutes=1))
        run = claim_due_runs(now=now, limit=1)[0]
        ScheduledReportRun.objects.filter(pk=run.pk).update(
            attempts=3, lease_expires_at=now - timedelta(seconds=1)
        )

        self.assertEqual(claim_due_runs(now=now, limit=1), [])
        run.refresh_from_db()
        self.assertEqual(run.status, ScheduledReportRun.Status.FAILED)
        self.assertIsNone(run.lease_expires_at)

    def test_pause_prevents_future_claims_but_not_current_run(self):
        from django_qbe2.scheduling import claim_due_runs

        now = datetime(2026, 10, 16, 12, tzinfo=UTC)
        schedule = self.schedule(next_run_at=now - timedelta(minutes=1))
        current = claim_due_runs(now=now, limit=1)[0]
        schedule.enabled = False
        schedule.save(update_fields=["enabled"])

        self.assertEqual(claim_due_runs(now=now + timedelta(days=1), limit=1), [])
        current.refresh_from_db()
        self.assertEqual(current.status, ScheduledReportRun.Status.RUNNING)

    def test_missed_intervals_do_not_create_email_bursts(self):
        from django_qbe2.scheduling import claim_due_runs

        now = datetime(2026, 10, 16, 12, tzinfo=UTC)
        schedule = self.schedule(next_run_at=now - timedelta(days=100))

        runs = claim_due_runs(now=now, limit=10)

        self.assertEqual(len(runs), 1)
        self.assertGreaterEqual(runs[0].scheduled_for, now - timedelta(days=1))
        self.assertEqual(ScheduledReportRun.objects.count(), 1)
        schedule.refresh_from_db()
        self.assertGreater(schedule.next_run_at, now)

    def test_retry_stops_after_three_attempts(self):
        from django_qbe2.scheduling import claim_due_runs, finish_scheduled_run

        now = datetime(2026, 10, 16, 12, tzinfo=UTC)
        self.schedule(next_run_at=now - timedelta(minutes=1))
        run = claim_due_runs(now=now, limit=1)[0]
        for delay in (timedelta(minutes=5), timedelta(minutes=10)):
            finish_scheduled_run(run, now=now, error_summary="Email delivery failed.")
            now += delay
            run = claim_due_runs(now=now, limit=1)[0]
        finish_scheduled_run(run, now=now, error_summary="Email delivery failed.")
        now += timedelta(hours=1)

        self.assertEqual(claim_due_runs(now=now, limit=1), [])
        run.refresh_from_db()
        self.assertEqual(run.attempts, 3)
        self.assertEqual(run.status, ScheduledReportRun.Status.FAILED)

    @override_settings(**MAIL_SETTINGS)
    def test_command_sends_one_due_report_and_records_success(self):
        from django.core import mail

        self.schedule(next_run_at=timezone.now() - timedelta(minutes=1))

        call_command(
            "qbe2_run_scheduled_reports", limit=2, stdout=__import__("io").StringIO()
        )

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            ScheduledReportRun.objects.get().status, ScheduledReportRun.Status.SUCCEEDED
        )

    @override_settings(**MAIL_SETTINGS)
    def test_lost_report_permission_disables_schedule_without_sending(self):
        from django.core import mail

        schedule = self.schedule(next_run_at=timezone.now() - timedelta(minutes=1))
        self.owner.user_permissions.clear()

        call_command(
            "qbe2_run_scheduled_reports", limit=1, stdout=__import__("io").StringIO()
        )

        schedule.refresh_from_db()
        run = ScheduledReportRun.objects.get(schedule=schedule)
        self.assertFalse(schedule.enabled)
        self.assertEqual(run.status, ScheduledReportRun.Status.FAILED)
        self.assertIsNone(run.lease_expires_at)
        self.assertEqual(mail.outbox, [])

    def test_failure_summary_does_not_store_mailer_exception(self):
        from unittest.mock import patch

        schedule = self.schedule(next_run_at=timezone.now() - timedelta(minutes=1))
        with patch(
            "django_qbe2.management.commands.qbe2_run_scheduled_reports.send_scheduled_report",
            side_effect=OSError("SMTP secret recipient@example.com"),
        ):
            call_command(
                "qbe2_run_scheduled_reports",
                limit=1,
                stdout=__import__("io").StringIO(),
            )

        run = ScheduledReportRun.objects.get(schedule=schedule)
        self.assertNotIn("SMTP secret", run.error_summary)
        self.assertNotIn("recipient@example.com", run.error_summary)


class ConcurrentScheduledClaimsTests(TransactionTestCase):
    reset_sequences = True

    def test_concurrent_workers_claim_one_occurrence_once(self):
        from django_qbe2.scheduling import claim_due_runs

        owner = make_staff("scheduled-concurrent-owner")
        now = datetime(2026, 10, 16, 12, tzinfo=UTC)
        ScheduledReport.objects.create(
            owner=owner,
            name="Daily orders",
            definition=order_payload(),
            page_size=25,
            frequency="daily",
            weekday=None,
            local_time=time(9),
            timezone="UTC",
            recipients=["reports@example.com"],
            format="csv",
            next_run_at=now - timedelta(minutes=1),
        )
        gate = Barrier(2)

        def claim():
            close_old_connections()
            gate.wait()
            runs = claim_due_runs(now=now, limit=1)
            close_old_connections()
            return [run.pk for run in runs]

        with ThreadPoolExecutor(max_workers=2) as workers:
            claims = list(workers.map(lambda _item: claim(), range(2)))

        self.assertEqual(sum(len(result) for result in claims), 1)
        self.assertEqual(ScheduledReportRun.objects.count(), 1)

    def test_concurrent_workers_claim_one_retry_once(self):
        from django_qbe2.scheduling import claim_due_runs

        owner = make_staff("scheduled-concurrent-retry-owner")
        now = datetime(2026, 10, 16, 12, tzinfo=UTC)
        ScheduledReport.objects.create(
            owner=owner,
            name="Daily orders",
            definition=order_payload(),
            page_size=25,
            frequency="daily",
            weekday=None,
            local_time=time(9),
            timezone="UTC",
            recipients=["reports@example.com"],
            format="csv",
            next_run_at=now - timedelta(minutes=1),
        )
        run = claim_due_runs(now=now, limit=1)[0]
        run.status = ScheduledReportRun.Status.FAILED
        run.error_summary = "Temporary email failure."
        run.lease_expires_at = now - timedelta(seconds=1)
        run.save(update_fields=("status", "error_summary", "lease_expires_at"))
        gate = Barrier(2)

        def claim():
            close_old_connections()
            gate.wait()
            runs = claim_due_runs(now=now, limit=1)
            close_old_connections()
            return [item.pk for item in runs]

        with ThreadPoolExecutor(max_workers=2) as workers:
            claims = list(workers.map(lambda _item: claim(), range(2)))

        self.assertEqual(sum(len(result) for result in claims), 1)
        run.refresh_from_db()
        self.assertEqual(run.status, ScheduledReportRun.Status.RUNNING)
        self.assertEqual(run.attempts, 2)
