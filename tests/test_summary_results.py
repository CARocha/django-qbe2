import json
from copy import deepcopy
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import connection
from django.test import RequestFactory, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from django_qbe2.catalog import get_catalog
from django_qbe2.engine import build_summary_source
from django_qbe2.validation import validate_definition
from tests.fixtures import grant_view, make_orders, make_staff
from tests.models import Customer, Order
from tests.test_summary_validation import summary_payload


class SummaryExecutionTests(TestCase):
    def setUp(self):
        self.user = make_staff("summary-results")
        grant_view(self.user, Order, Customer)
        self.orders = make_orders(self.user)
        self.request = RequestFactory().get("/")
        self.request.user = self.user
        self.catalog = get_catalog(self.request)

    def definition(self, **changes):
        return validate_definition(summary_payload(**changes), self.catalog)

    def execute(self, definition):
        from django_qbe2.execution import execute_summary

        return execute_summary(
            build_summary_source(definition, self.catalog, self.request),
            definition,
            self.catalog,
        )

    @override_settings(QBE2_MAX_AGGREGATE_ROWS=2)
    def test_exact_source_limit_succeeds_with_complete_totals(self):
        definition = self.definition(
            metrics=[
                {"id": "m1", "function": "count", "field": None},
                {"id": "m2", "function": "sum", "field": "total"},
            ]
        )
        result = self.execute(definition)
        self.assertEqual(result.source_count, 2)
        self.assertEqual(result.rows[0]["metric:m1"], 2)
        self.assertEqual(result.rows[0]["metric:m2"], Decimal("300.01"))

    @override_settings(QBE2_MAX_AGGREGATE_ROWS=1)
    def test_one_record_over_limit_fails_without_partial_totals(self):
        definition = self.definition(
            metrics=[{"id": "m1", "function": "sum", "field": "total"}]
        )
        with self.assertRaisesRegex(ValidationError, "Refine") as captured:
            self.execute(definition)
        self.assertNotIn("100.01", str(captured.exception))

    def test_execution_selects_only_group_metric_values_and_canonical_pk(self):
        definition = self.definition(
            group_by=["active"],
            metrics=[
                {"id": "m1", "function": "count", "field": None},
                {"id": "m2", "function": "avg", "field": "total"},
            ],
        )
        with CaptureQueriesContext(connection) as queries:
            self.execute(definition)
        business_queries = [
            query["sql"]
            for query in queries
            if query["sql"].lstrip().upper().startswith("SELECT")
            and "SET_CONFIG" not in query["sql"].upper()
            and "STATEMENT_TIMEOUT" not in query["sql"].upper()
        ]
        self.assertEqual(len(business_queries), 1)
        sql = business_queries[0].lower()
        self.assertIn("active", sql)
        self.assertIn("total", sql)
        self.assertNotIn("created_at", sql)
        self.assertNotIn("reference", sql)

    def test_summary_execution_only_reads_business_data(self):
        definition = self.definition(
            group_by=["m1"],
            metrics=[{"id": "m1", "function": "count", "field": None}],
        )
        before = list(Order.objects.values().order_by("pk"))
        with CaptureQueriesContext(connection) as queries:
            result = self.execute(definition)
        self.assertEqual(before, list(Order.objects.values().order_by("pk")))
        statements = [
            query["sql"].lstrip().upper()
            for query in queries
            if "SET_CONFIG" not in query["sql"].upper()
            and "STATEMENT_TIMEOUT" not in query["sql"].upper()
            and not query["sql"].lstrip().upper().startswith(
                ("SAVEPOINT", "RELEASE SAVEPOINT", "ROLLBACK TO SAVEPOINT")
            )
        ]
        self.assertTrue(statements)
        self.assertTrue(all(statement.startswith("SELECT") for statement in statements))
        self.assertEqual(result.source_count, 2)


class SummaryResultsViewTests(TestCase):
    def setUp(self):
        self.user = make_staff("summary-view")
        grant_view(self.user, Order, Customer)
        self.orders = make_orders(self.user)
        self.client.force_login(self.user)

    def post(self, payload, **extra):
        return self.client.post(
            reverse("django_qbe2:results"),
            {"definition": json.dumps(payload), "page_size": "50", **extra},
        )

    def test_ungrouped_summary_renders_source_count_and_metric_labels(self):
        payload = summary_payload(
            metrics=[
                {"id": "m1", "function": "count", "field": None},
                {"id": "m2", "function": "sum", "field": "total"},
            ]
        )
        response = self.post(payload)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "2 source records")
        self.assertContains(response, "Count records")
        self.assertContains(response, "Sum of total")
        self.assertContains(response, "300.01")

    def test_grouped_summary_labels_choices_and_namespaced_collision(self):
        Order.objects.filter(pk=self.orders[1].pk).update(m1="A")
        payload = summary_payload(
            group_by=["m1"],
            metrics=[{"id": "m1", "function": "count", "field": None}],
            ordering=[{"type": "group", "field": "m1", "direction": "asc"}],
        )
        response = self.post(payload)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "2 groups")
        self.assertContains(response, "Same label", count=2)
        self.assertEqual(
            response.context["page"].rows,
            [
                {"group:m1": "A", "metric:m1": 1},
                {"group:m1": "a", "metric:m1": 1},
            ],
        )

    def test_empty_grouped_summary_and_edit_roundtrip(self):
        Order.objects.filter(owner=self.user).delete()
        payload = summary_payload(
            group_by=["active"],
            metrics=[{"id": "m1", "function": "count", "field": None}],
        )
        response = self.post(payload)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No groups match your conditions")
        edited = self.post(payload, action="edit")
        self.assertEqual(edited.status_code, 200)
        self.assertEqual(edited.context["form"].payload, payload)

    def test_empty_ungrouped_summary_returns_one_zero_count_row(self):
        Order.objects.filter(owner=self.user).delete()
        response = self.post(summary_payload())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page"].rows, [{"metric:m1": 0}])
        self.assertContains(response, "0 source records")

    @override_settings(QBE2_MAX_ROWS=1)
    def test_group_truncation_and_pagination_are_visible(self):
        Order.objects.filter(pk=self.orders[1].pk).update(active=False)
        payload = summary_payload(
            group_by=["active"],
            metrics=[{"id": "m1", "function": "count", "field": None}],
        )
        response = self.post(payload)
        self.assertTrue(response.context["page"].truncated)
        self.assertContains(response, "groups")
        self.assertContains(response, "Results limited")

    def test_group_pagination_uses_complete_ordered_results(self):
        Order.objects.filter(pk=self.orders[0].pk).update(m1="A")
        Order.objects.create(owner=self.user, number="third", total="1.00", m1="a")
        payload = summary_payload(
            group_by=["m1"],
            metrics=[{"id": "m1", "function": "count", "field": None}],
            ordering=[{"type": "group", "field": "m1", "direction": "asc"}],
        )
        response = self.post(payload, page_size="1", page="2")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page"].rows[0]["group:m1"], "a")
        self.assertEqual(response.context["page"].rows[0]["metric:m1"], 2)

    @override_settings(QBE2_MAX_AGGREGATE_ROWS=1)
    def test_source_overflow_returns_builder_error_without_partial_total(self):
        response = self.post(summary_payload())
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Refine", status_code=400)
        self.assertNotContains(response, "1 source record", status_code=400)

    def test_preview_does_not_mutate_payload_or_business_rows(self):
        payload = summary_payload()
        original = deepcopy(payload)
        before = list(Order.objects.values().order_by("pk"))
        response = self.post(payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload, original)
        self.assertEqual(before, list(Order.objects.values().order_by("pk")))
