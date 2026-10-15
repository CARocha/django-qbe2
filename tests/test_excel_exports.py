import json
from datetime import date
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from openpyxl import load_workbook

from tests import test_engine
from tests.fixtures import grant_view
from tests.models import Order, Pet
from tests.test_validation import order_payload


class ExcelExportTests(TestCase):
    setUp = test_engine.EngineTests.setUp

    def export(self, payload, export_format="xlsx"):
        self.client.force_login(self.alice)
        return self.client.post(
            reverse("django_qbe2:export"),
            {
                "definition": json.dumps(payload),
                "export_format": export_format,
            },
        )

    def workbook(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        content = b"".join(response.streaming_content)
        response.close()
        return load_workbook(BytesIO(content), data_only=False)

    def test_row_export_preserves_types_and_keeps_text_as_text(self):
        Order.objects.filter(pk=self.orders[0].pk).update(
            total=Decimal("100.01"),
            due_date=date(2026, 10, 15),
            note='=HYPERLINK("https://example.invalid","open")',
        )
        response = self.export(
            order_payload(columns=["number", "total", "active", "due_date", "note"])
        )

        self.assertIn(".xlsx", response["Content-Disposition"])
        workbook = self.workbook(response)
        sheet = workbook["Report"]
        self.assertEqual(
            [cell.value for cell in sheet[1]],
            ["number", "total", "active", "due date", "note"],
        )
        self.assertEqual(sheet["A2"].value, "A100")
        self.assertEqual(sheet["B2"].value, 100.01)
        self.assertEqual(sheet["B2"].data_type, "n")
        self.assertIs(sheet["C2"].value, True)
        self.assertEqual(sheet["C2"].data_type, "b")
        self.assertEqual(sheet["D2"].value.date(), date(2026, 10, 15))
        self.assertEqual(
            sheet["E2"].value,
            '=HYPERLINK("https://example.invalid","open")',
        )
        self.assertEqual(sheet["E2"].data_type, "s")
        workbook.close()

    def test_row_export_keeps_related_values_in_one_cell_and_scoped(self):
        grant_view(self.alice, Pet)
        for cache in ("_perm_cache", "_user_perm_cache", "_group_perm_cache"):
            if hasattr(self.alice, cache):
                delattr(self.alice, cache)
        customer = self.orders[0].customer
        Pet.objects.create(customer=customer, name="Milo")
        Pet.objects.create(customer=customer, name="Luna")

        workbook = self.workbook(
            self.export(order_payload(columns=["number", "customer__pets__name"]))
        )

        rows = list(workbook["Report"].values)
        self.assertEqual(rows[0], ("number", "name"))
        self.assertIn(("A100", "Milo, Luna"), rows)
        self.assertNotIn(("B100", "Bob Customer"), rows)
        workbook.close()

    @override_settings(QBE2_MAX_ROWS=1)
    def test_row_export_is_bounded_and_reports_truncation(self):
        response = self.export(order_payload(columns=["number", "total"]))
        self.assertEqual(response["X-QBE-Truncated"], "true")
        workbook = self.workbook(response)
        rows = list(workbook["Report"].values)
        self.assertEqual(rows[1:], [("A100", 100.01)])
        workbook.close()

    def test_unknown_export_format_is_rejected(self):
        response = self.export(order_payload(), export_format="xls")
        self.assertEqual(response.status_code, 400)

    def test_excel_export_is_not_available_without_optional_dependency(self):
        with patch("django_qbe2.exports.find_spec", return_value=None):
            response = self.export(order_payload())
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "django-qbe2[excel]", status_code=400)
