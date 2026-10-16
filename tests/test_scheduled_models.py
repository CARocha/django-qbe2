from datetime import time
from uuid import UUID

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from tests.fixtures import make_staff


class ScheduledReportModelTests(TestCase):
    def setUp(self):
        self.owner = make_staff("schedule-owner")

    def schedule(self, **changes):
        from django_qbe2.models import ScheduledReport

        defaults = {
            "owner": self.owner,
            "name": "Daily orders",
            "definition": {
                "version": 1,
                "report": "tests.order",
                "columns": ["number"],
                "filters": [],
                "ordering": [],
            },
            "page_size": 50,
            "frequency": "daily",
            "weekday": None,
            "local_time": time(9),
            "timezone": "America/Managua",
            "recipients": ["reports@example.com"],
            "format": "csv",
            "next_run_at": timezone.now(),
        }
        defaults.update(changes)
        return ScheduledReport.objects.create(**defaults)

    def test_schedule_copies_definition_and_survives_saved_query_changes(self):
        from django_qbe2.models import SavedQuery

        saved_query = SavedQuery.objects.create(
            owner=self.owner,
            name="Orders",
            definition={"version": 1, "report": "tests.order"},
            page_size=25,
        )
        definition_copy = saved_query.definition.copy()
        schedule = self.schedule(
            definition=definition_copy,
            page_size=saved_query.page_size,
        )

        saved_query.definition = {"version": 1, "report": "tests.customer"}
        saved_query.save(update_fields=["definition"])
        saved_query.delete()

        schedule.refresh_from_db()
        self.assertEqual(schedule.definition, definition_copy)
        self.assertEqual(schedule.page_size, 25)
        self.assertIsInstance(schedule.pk, UUID)

    def test_schedule_owner_deletion_cascades_to_schedules_and_runs(self):
        from django_qbe2.models import ScheduledReportRun

        schedule = self.schedule()
        ScheduledReportRun.objects.create(
            schedule=schedule,
            scheduled_for=schedule.next_run_at,
            status="queued",
        )

        get_user_model().objects.filter(pk=self.owner.pk).delete()

        self.assertFalse(type(schedule).objects.exists())
        self.assertFalse(ScheduledReportRun.objects.exists())

    def test_run_occurrence_is_unique(self):
        from django_qbe2.models import ScheduledReportRun

        schedule = self.schedule()
        ScheduledReportRun.objects.create(
            schedule=schedule,
            scheduled_for=schedule.next_run_at,
            status="queued",
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            ScheduledReportRun.objects.create(
                schedule=schedule,
                scheduled_for=schedule.next_run_at,
                status="queued",
            )

    def test_run_history_does_not_have_report_rows_or_files(self):
        from django_qbe2.models import ScheduledReportRun

        field_names = {field.name for field in ScheduledReportRun._meta.get_fields()}
        self.assertTrue(
            {
                "schedule",
                "scheduled_for",
                "status",
                "attempts",
                "started_at",
                "finished_at",
                "lease_expires_at",
                "error_summary",
            }.issubset(field_names)
        )
        self.assertFalse({"rows", "results", "attachment", "file"} & field_names)
