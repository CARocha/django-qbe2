from datetime import time
from unittest.mock import patch

import django
from django.core import mail
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone

from django_qbe2.models import ScheduledReport
from tests.fixtures import grant_view, make_orders, make_staff
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


@override_settings(**MAIL_SETTINGS)
class ScheduledEmailTests(TestCase):
    def setUp(self):
        from django_qbe2.scheduled_execution import prepare_scheduled_execution

        self.owner = make_staff("scheduled-email-owner")
        grant_view(self.owner, Order, Customer)
        make_orders(self.owner)
        self.schedule = ScheduledReport.objects.create(
            owner=self.owner,
            name="Daily orders",
            definition=order_payload(),
            page_size=25,
            frequency="daily",
            weekday=None,
            local_time=time(9),
            timezone="UTC",
            recipients=["first@example.com", "second@example.com"],
            format="csv",
            next_run_at=timezone.now(),
        )
        self.execution = prepare_scheduled_execution(self.schedule)

    def test_email_bcc_attachment_and_size_failure(self):
        from django_qbe2.scheduled_exports import (
            build_report_attachment,
            send_scheduled_report,
        )

        attachment = build_report_attachment(self.execution, self.schedule)
        self.assertEqual(attachment.filename, "report-tests-order.csv")
        self.assertIn(b"number,total", attachment.content)
        self.assertEqual(send_scheduled_report(self.schedule, attachment), 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [])
        self.assertEqual(mail.outbox[0].bcc, self.schedule.recipients)
        self.assertEqual(mail.outbox[0].attachments[0][0], attachment.filename)

        with override_settings(QBE2_MAX_SCHEDULED_ATTACHMENT_BYTES=1):
            with self.assertRaises(ValidationError):
                build_report_attachment(self.execution, self.schedule)

    def test_email_uses_locmem_default_mailer(self):
        from django_qbe2.scheduled_exports import (
            ReportAttachment,
            send_scheduled_report,
        )

        attachment = ReportAttachment("report.csv", "text/csv", b"number\nA1\n")

        self.assertEqual(send_scheduled_report(self.schedule, attachment), 1)
        self.assertEqual(mail.outbox[0].from_email, "webmaster@localhost")

    def test_zero_deliveries_are_not_reported_as_success(self):
        from django_qbe2.scheduled_exports import (
            ReportAttachment,
            send_scheduled_report,
        )

        attachment = ReportAttachment("report.csv", "text/csv", b"number\nA1\n")
        with patch("django_qbe2.scheduled_exports.EmailMessage.send", return_value=0):
            with self.assertRaises(OSError):
                send_scheduled_report(self.schedule, attachment)

    def test_summary_attachment_contains_aggregated_results(self):
        from django_qbe2.scheduled_execution import prepare_scheduled_execution
        from django_qbe2.scheduled_exports import build_report_attachment
        from tests.test_summary_validation import summary_payload

        self.schedule.definition = summary_payload(
            group_by=["active"],
            metrics=[
                {"id": "m1", "function": "count", "field": None},
                {"id": "m2", "function": "sum", "field": "total"},
            ],
        )
        self.schedule.save(update_fields=["definition"])
        execution = prepare_scheduled_execution(self.schedule)

        attachment = build_report_attachment(execution, self.schedule)

        self.assertIn(b"true,2,300.01", attachment.content)

    def test_xlsx_requires_optional_extra(self):
        from django_qbe2.scheduled_exports import build_report_attachment

        self.schedule.format = "xlsx"
        with patch("django_qbe2.scheduled_exports.excel_available", return_value=False):
            with self.assertRaises(ValidationError):
                build_report_attachment(self.execution, self.schedule)

    def test_report_limit_failure_sends_no_email(self):
        from django_qbe2.scheduled_exports import build_report_attachment

        with override_settings(QBE2_MAX_ROWS=1):
            with self.assertRaises(ValidationError):
                build_report_attachment(self.execution, self.schedule)
        self.assertEqual(mail.outbox, [])

    def test_email_failure_is_recorded_without_sensitive_values(self):
        from django_qbe2.scheduled_exports import (
            ReportAttachment,
            send_scheduled_report,
        )

        attachment = ReportAttachment("report.csv", "text/csv", b"private data")
        with patch(
            "django_qbe2.scheduled_exports.EmailMessage.send",
            side_effect=OSError("SMTP secret"),
        ):
            with self.assertRaises(OSError):
                send_scheduled_report(self.schedule, attachment)
