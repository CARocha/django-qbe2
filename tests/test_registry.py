from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from tests.models import Order


class RegistryTests(SimpleTestCase):
    def test_explicit_registration(self):
        from django_qbe2.registry import Report, get_reports, register

        class OrderReport(Report):
            model = Order
            fields = ("number",)

            def get_queryset(self, request):
                return Order.objects.filter(owner=request.user)

        with patch.dict("django_qbe2.registry._reports", clear=True):
            self.assertEqual(get_reports(), ())
            self.assertIs(register(OrderReport), OrderReport)
            self.assertEqual(get_reports()[0].model, Order)
            with self.assertRaises(ImproperlyConfigured):
                register(OrderReport)

    def test_missing_scope_is_rejected(self):
        from django_qbe2.registry import Report, register

        class UnsafeReport(Report):
            model = Order
            fields = ("number",)

        with self.assertRaises(ImproperlyConfigured):
            register(UnsafeReport)
