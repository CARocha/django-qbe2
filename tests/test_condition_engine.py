from copy import deepcopy

from django.test import TestCase

from django_qbe2.engine import build_queryset
from django_qbe2.validation import validate_definition
from tests.models import Customer, Order
from tests.test_condition_validation import group, grouped_payload, leaf
from tests.test_engine import EngineTests


class ConditionEngineTests(TestCase):
    setUp = EngineTests.setUp

    def query(self, where):
        definition = validate_definition(grouped_payload(where), self.catalog)
        return build_queryset(definition, self.catalog, self.request)

    def numbers(self, where):
        return list(self.query(where).values_list("number", flat=True))

    def test_grouping_and_double_negation_have_distinct_results(self):
        a, b, c = leaf(), leaf(value="A200"), leaf("total", "150", "gte")
        self.assertEqual(self.numbers(group(group(a, b, connector="or"), c)), ["A200"])
        self.assertEqual(
            self.numbers(group(a, group(b, c), connector="or")), ["A100", "A200"]
        )
        self.assertEqual(self.numbers(group(a, negated=True)), ["A200"])
        self.assertEqual(
            self.numbers(group(group(a, negated=True), negated=True)), ["A100"]
        )

    def test_or_and_not_cannot_expand_owner_scope(self):
        for where in (
            group(leaf(value="B100"), leaf("total", "0", "gte"), connector="or"),
            group(leaf(value="B100"), negated=True),
        ):
            with self.subTest(where=where):
                self.assertEqual(self.numbers(where), ["A100", "A200"])

    def test_related_scope_stays_outside_local_or_and_not(self):
        inaccessible = Customer.objects.create(
            owner=self.bob, name="Hidden", code="HIDDEN"
        )
        Order.objects.filter(pk=self.orders[0].pk).update(customer=inaccessible)
        for where in (
            group(
                leaf("total", "0", "gte"),
                leaf("customer__name", "Hidden"),
                connector="or",
            ),
            group(leaf("customer__name", "Hidden"), negated=True),
        ):
            with self.subTest(where=where):
                self.assertEqual(self.numbers(where), ["A200"])

    def test_null_predicates_and_empty_root(self):
        Order.objects.filter(pk=self.orders[1].pk).update(due_date="2026-10-14")
        self.assertEqual(
            self.numbers(group(leaf("due_date", "2026-10-14"), negated=True)), ["A100"]
        )
        self.assertEqual(
            self.numbers(group(leaf("due_date", True, "isnull"))), ["A100"]
        )
        self.assertEqual(self.numbers(group()), ["A100", "A200"])

    def test_hostile_values_do_not_modify_business_rows(self):
        before = deepcopy(list(Order.objects.order_by("pk").values()))
        self.assertEqual(
            self.numbers(group(leaf(value="'; DELETE FROM tests_order; --"))), []
        )
        self.assertEqual(list(Order.objects.order_by("pk").values()), before)

    def test_false_zero_decimal_and_stable_order(self):
        Order.objects.filter(pk=self.orders[0].pk).update(active=False, quantity=0)
        self.assertEqual(
            self.numbers(
                group(
                    leaf("active", False), leaf("quantity", 0), leaf("total", "100.01")
                )
            ),
            ["A100"],
        )
