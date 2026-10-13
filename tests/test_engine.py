from django.core.exceptions import ImproperlyConfigured
from django.test import RequestFactory, TestCase

from django_qbe2.catalog import get_catalog
from django_qbe2.validation import validate_definition
from tests.fixtures import grant_view, make_orders, make_staff
from tests.models import Customer, Order
from tests.test_validation import order_payload


class EngineTests(TestCase):
    def setUp(self):
        self.alice = make_staff("alice")
        self.bob = make_staff("bob")
        grant_view(self.alice, Order, Customer)
        self.orders = make_orders(self.alice)
        make_orders(self.bob)
        self.request = RequestFactory().get("/")
        self.request.user = self.alice
        self.catalog = get_catalog(self.request)

    def query(self, **changes):
        from django_qbe2.engine import build_queryset

        definition = validate_definition(order_payload(**changes), self.catalog)
        return build_queryset(definition, self.catalog, self.request)

    def test_scoped_filter_and_order(self):
        queryset = self.query(
            filters=[
                {"field": "total", "operator": "gte", "value": "100"},
                {"field": "total", "operator": "lte", "value": "200"},
            ],
            ordering=[{"field": "number", "direction": "asc"}],
        )
        self.assertEqual(
            list(queryset.values_list("number", flat=True)), ["A100", "A200"]
        )

    def test_hostile_value_is_a_parameter(self):
        queryset = self.query(
            filters=[
                {
                    "field": "number",
                    "operator": "exact",
                    "value": "' OR 1=1 --",
                }
            ]
        )
        self.assertEqual(list(queryset), [])
        self.assertEqual(Order.objects.count(), 4)

    def test_stable_order_has_primary_key_tiebreaker(self):
        Order.objects.filter(owner=self.alice).update(total="100.00")
        queryset = self.query(ordering=[{"field": "total", "direction": "desc"}])
        self.assertEqual(
            list(queryset.values_list("pk", flat=True)),
            [order.pk for order in self.orders],
        )

    def test_invalid_scope_is_configuration_error(self):
        report = self.catalog["tests.order"].report
        original = report.get_queryset
        try:
            for scope in (
                Order.objects.all()[:1],
                Order.objects.values("number"),
                Customer.objects.all(),
            ):
                report.get_queryset = lambda request, scope=scope: scope
                with self.assertRaises(ImproperlyConfigured):
                    self.query()
        finally:
            report.get_queryset = original
