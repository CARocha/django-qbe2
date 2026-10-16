from datetime import time
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import RequestFactory, TestCase
from django.utils import timezone

from django_qbe2.models import ScheduledReport
from django_qbe2.registry import get_reports
from tests.fixtures import grant_view, make_staff
from tests.models import Customer, Order
from tests.test_validation import order_payload


class ScheduledExecutionTests(TestCase):
    def setUp(self):
        from django_qbe2.catalog import get_catalog
        from django_qbe2.scheduled_execution import prepare_scheduled_execution

        self.prepare = prepare_scheduled_execution
        self.owner = make_staff("scheduled-exec-owner")
        grant_view(self.owner, Order, Customer)
        self.schedule = ScheduledReport.objects.create(
            owner=self.owner,
            name="Daily orders",
            definition=order_payload(),
            page_size=25,
            frequency="daily",
            weekday=None,
            local_time=time(9),
            timezone="America/Managua",
            recipients=["reports@example.com"],
            format="csv",
            next_run_at=timezone.now(),
        )
        request = RequestFactory().get("/")
        request.user = self.owner
        self.catalog = get_catalog(request)

    def test_default_scheduled_request_uses_owner_and_timezone(self):
        context = self.prepare(self.schedule)

        self.assertEqual(context.request.user.pk, self.owner.pk)
        self.assertEqual(context.request.timezone, ZoneInfo("America/Managua"))
        self.assertEqual(context.report_spec.id, "tests.order")

    def test_custom_report_context_hook_is_used(self):
        report = next(report for report in get_reports() if report.model is Order)
        marker = object()
        factory = RequestFactory()

        def custom_context(*, owner, schedule):
            request = factory.get("/scheduled/")
            request.user = owner
            request.tenant_marker = marker
            return request

        with patch.object(report, "get_scheduled_request", custom_context):
            context = self.prepare(self.schedule)

        self.assertIs(context.request.tenant_marker, marker)
        self.assertEqual(context.request.user.pk, self.owner.pk)

    def test_custom_context_cannot_replace_the_schedule_owner(self):
        report = next(report for report in get_reports() if report.model is Order)
        runner = make_staff("scheduled-exec-context-runner")
        factory = RequestFactory()

        def wrong_owner(*, owner, schedule):
            request = factory.get("/scheduled/")
            request.user = runner
            return request

        with patch.object(report, "get_scheduled_request", wrong_owner):
            with self.assertRaises(PermissionDenied):
                self.prepare(self.schedule)

    def test_inactive_owner_cannot_run_a_schedule(self):
        self.owner.is_active = False
        self.owner.save(update_fields=["is_active"])

        with self.assertRaises(PermissionDenied):
            self.prepare(self.schedule)

    def test_execution_fails_closed_after_owner_permission_loss(self):
        self.owner.user_permissions.remove(
            *self.owner.user_permissions.filter(
                codename__in=["view_order", "view_customer"]
            )
        )
        with self.assertRaises((PermissionDenied, ValidationError)):
            self.prepare(self.schedule)

    def test_execution_fails_closed_after_related_permission_loss(self):
        self.schedule.definition["columns"] = ["number", "customer__name"]
        self.schedule.save(update_fields=["definition"])
        permission = self.owner.user_permissions.get(codename="view_customer")
        self.owner.user_permissions.remove(permission)

        with self.assertRaises(PermissionDenied):
            self.prepare(self.schedule)

    def test_stale_definition_sends_no_attachment(self):
        self.schedule.definition["columns"] = ["owner__password"]
        self.schedule.save(update_fields=["definition"])

        with self.assertRaises(ValidationError):
            self.prepare(self.schedule)

    def test_superuser_runner_never_replaces_schedule_owner(self):
        runner = make_staff("scheduled-exec-runner")
        runner.is_superuser = True
        runner.save(update_fields=["is_superuser"])

        context = self.prepare(self.schedule)

        self.assertNotEqual(context.request.user.pk, runner.pk)
        self.assertEqual(context.request.user.pk, self.owner.pk)
