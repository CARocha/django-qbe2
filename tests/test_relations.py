from django_qbe2.engine import build_queryset
from django_qbe2.validation import validate_definition
from tests.models import Customer, Order
from tests.test_engine import EngineTests
from tests.test_validation import order_payload


class RelationTests(EngineTests):
    def test_inaccessible_customer_excludes_order(self):
        foreign = Customer.objects.get(owner=self.bob)
        Order.objects.filter(pk=self.orders[0].pk).update(customer=foreign)
        Order.objects.filter(pk=self.orders[1].pk).update(customer=None)
        for changes in (
            {"columns": ["number", "customer__name"]},
            {"ordering": [{"field": "customer__name", "direction": "asc"}]},
            {
                "filters": [
                    {"field": "customer__name", "operator": "contains", "value": "Bob"}
                ]
            },
        ):
            with self.subTest(changes=changes):
                queryset = self.query(**changes)
                numbers = list(queryset.values_list("number", flat=True))
                self.assertNotIn("A100", numbers)
                if "filters" not in changes:
                    self.assertEqual(numbers, ["A200"])

    def test_to_field_uses_target_key(self):
        foreign = Customer.objects.get(owner=self.bob)
        Order.objects.filter(pk=self.orders[0].pk).update(customer_by_code=foreign)
        queryset = self.query(columns=["customer_by_code__code"])
        self.assertEqual(
            list(queryset.values_list("customer_by_code__code", flat=True)), ["ALICE"]
        )

    def test_one_to_one_does_not_duplicate_rows(self):
        from django_qbe2.catalog import get_catalog
        from tests.fixtures import grant_view
        from tests.models import Profile

        customer = Customer.objects.get(owner=self.alice)
        Profile.objects.create(customer=customer, label="Primary")
        grant_view(self.alice, Profile)
        for name in ("_perm_cache", "_user_perm_cache"):
            self.alice.__dict__.pop(name, None)
        catalog = get_catalog(self.request)
        definition = validate_definition(
            order_payload(report="tests.profile", columns=["label", "customer__name"]),
            catalog,
        )
        queryset = build_queryset(definition, catalog, self.request)
        self.assertEqual(list(queryset.values_list("label", flat=True)), ["Primary"])
