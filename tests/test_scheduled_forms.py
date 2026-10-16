from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from django_qbe2.scheduled_forms import ScheduledReportForm


class ScheduledReportFormTests(SimpleTestCase):
    def form(self, **changes):
        data = {
            "name": "Daily orders",
            "frequency": "daily",
            "weekday": "",
            "local_time": "09:30",
            "timezone": "America/Managua",
            "recipients": " Sales@example.com \nsales@EXAMPLE.com\nops@example.org ",
            "format": "csv",
            "confirm_recipients": "on",
        }
        data.update(changes)
        return ScheduledReportForm(data)

    def test_recipients_are_normalized_deduplicated_and_bounded(self):
        form = self.form()

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(
            form.cleaned_data["recipients"],
            ["Sales@example.com", "ops@example.org"],
        )

        with override_settings(QBE2_MAX_SCHEDULED_RECIPIENTS=1):
            limited = self.form(recipients="one@example.com\ntwo@example.com")
            self.assertFalse(limited.is_valid())
            self.assertIn("recipients", limited.errors)

    @override_settings(QBE2_SCHEDULED_EMAIL_DOMAIN_ALLOWLIST=("example.com",))
    def test_optional_domain_allowlist_rejects_unapproved_domain(self):
        form = self.form(recipients="person@elsewhere.test")

        self.assertFalse(form.is_valid())
        self.assertIn("recipients", form.errors)

    def test_frequency_timezone_confirmation_and_excel_are_validated(self):
        cases = (
            {"frequency": "weekly", "weekday": ""},
            {"frequency": "daily", "weekday": "1"},
            {"timezone": "Mars/Olympus"},
            {"confirm_recipients": ""},
        )
        for changes in cases:
            with self.subTest(changes=changes):
                form = self.form(**changes)
                self.assertFalse(form.is_valid())

        with patch("django_qbe2.scheduled_forms.excel_available", return_value=False):
            form = self.form(format="xlsx")
            self.assertFalse(form.is_valid())
            self.assertIn("format", form.errors)
