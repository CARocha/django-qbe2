from unittest.mock import patch

from django.test import SimpleTestCase

from tests.models import Customer, Order


class CheckTests(SimpleTestCase):
    def test_invalid_configuration_has_actionable_checks(self):
        from django_qbe2.checks import check_reports
        from django_qbe2.registry import Report, register

        for fields, labels, expected in (
            ((), {}, "E001"),
            (("missing",), {}, "E002"),
            (("owner",), {}, "E003"),
            (("customer__name",), {}, "E004"),
            (("number",), {"missing": "Label"}, "E005"),
            (("owner__username__x",), {}, "E003"),
        ):
            with (
                self.subTest(fields=fields),
                patch.dict("django_qbe2.registry._reports", clear=True),
            ):

                class InvalidReport(Report):
                    model = Order

                    def get_queryset(self, request):
                        return Order.objects.all()

                InvalidReport.fields = fields
                InvalidReport.field_labels = labels
                register(InvalidReport)
                self.assertEqual(check_reports()[0].id, f"django_qbe2.{expected}")

    def test_reverse_relations_are_rejected(self):
        from django_qbe2.checks import check_reports
        from django_qbe2.registry import Report, register

        with patch.dict("django_qbe2.registry._reports", clear=True):

            class ReverseReport(Report):
                model = Customer
                fields = ("order__number",)

                def get_queryset(self, request):
                    return Customer.objects.all()

            register(ReverseReport)
            self.assertEqual(check_reports()[0].id, "django_qbe2.E003")
