from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import connection, models
from django.test import RequestFactory, TestCase, override_settings
from django.test.utils import CaptureQueriesContext

from django_qbe2.catalog import get_catalog
from django_qbe2.engine import build_summary_source
from django_qbe2.execution import execute_summary
from django_qbe2.summary_sql import _uses_scaled_sqlite_decimal_sum
from django_qbe2.validation import validate_definition
from tests.fixtures import grant_view, make_orders, make_staff
from tests.models import Customer, Order, Pet
from tests.test_summary_validation import summary_payload


class DatabaseNativeSummaryTests(TestCase):
    def setUp(self):
        self.user = make_staff("database-summary")
        grant_view(self.user, Order, Customer, Pet)
        self.orders = make_orders(self.user)
        self.request = RequestFactory().get("/")
        self.request.user = self.user
        self.catalog = get_catalog(self.request)

    def execute(self, **changes):
        definition = validate_definition(summary_payload(**changes), self.catalog)
        source = build_summary_source(definition, self.catalog, self.request)
        return execute_summary(source, definition, self.catalog)

    def test_grouped_count_sum_avg_match_expected_rows(self):
        result = self.execute(
            group_by=["active"],
            metrics=[
                {"id": "m1", "function": "count", "field": None},
                {"id": "m2", "function": "sum", "field": "total"},
                {"id": "m3", "function": "avg", "field": "total"},
            ],
        )
        self.assertEqual(result.source_count, 2)
        self.assertEqual(
            result.rows,
            [
                {
                    "group:active": True,
                    "metric:m1": 2,
                    "metric:m2": Decimal("300.01"),
                    "metric:m3": Decimal("150.005000"),
                }
            ],
        )

    def test_multiple_metrics_do_not_multiply_results(self):
        result = self.execute(
            group_by=["customer__name"],
            metrics=[
                {"id": "m1", "function": "sum", "field": "total"},
                {"id": "m2", "function": "sum", "field": "customer__credit_limit"},
            ],
        )

        row = result.rows[0]
        self.assertEqual(row["metric:m1"], Decimal("300.01"))
        self.assertEqual(row["metric:m2"], Decimal("1000.00"))

    def test_multivalued_filter_counts_and_sums_each_root_once(self):
        customer = Customer.objects.get(owner=self.user)
        Pet.objects.create(customer=customer, name="Milo")
        Pet.objects.create(customer=customer, name="Milo")
        where = {
            "connector": "and",
            "negated": False,
            "children": [
                {
                    "field": "customer__pets__name",
                    "operator": "exact",
                    "value": "Milo",
                }
            ],
        }

        result = self.execute(
            where=where,
            metrics=[
                {"id": "m1", "function": "count", "field": None},
                {"id": "m2", "function": "sum", "field": "total"},
            ],
        )

        self.assertEqual(result.source_count, 2)
        self.assertEqual(result.rows[0]["metric:m1"], 2)
        self.assertEqual(result.rows[0]["metric:m2"], Decimal("300.01"))

    def test_decimal_average_keeps_half_even_rounding(self):
        customer = Customer.objects.get(owner=self.user)
        Order.objects.filter(pk=self.orders[0].pk).update(total=Decimal("1.00"))
        Order.objects.filter(pk=self.orders[1].pk).update(total=Decimal("0.00"))
        Order.objects.bulk_create(
            [
                Order(
                    owner=self.user,
                    customer=customer,
                    customer_by_code=customer,
                    number=f"extra-{index}",
                    total=Decimal("0.00"),
                )
                for index in range(126)
            ]
        )

        result = self.execute(
            metrics=[{"id": "m1", "function": "avg", "field": "total"}]
        )

        self.assertEqual(result.rows[0]["metric:m1"], Decimal("0.007812"))

    def test_decimal_sum_preserves_precision_beyond_field_max_digits(self):
        Order.objects.filter(owner=self.user).update(total=Decimal("9999999999.99"))
        customer = Customer.objects.get(owner=self.user)
        Order.objects.bulk_create(
            [
                Order(
                    owner=self.user,
                    customer=customer,
                    customer_by_code=customer,
                    number=f"large-{index}",
                    total=Decimal("9999999999.99"),
                )
                for index in range(9997)
            ]
        )

        result = self.execute(
            metrics=[{"id": "m1", "function": "sum", "field": "total"}]
        )

        self.assertEqual(result.rows[0]["metric:m1"], Decimal("99989999999900.01"))

    def test_sqlite_rejects_decimal_precision_that_cannot_be_summed_exactly(self):
        with self.assertRaisesRegex(ValidationError, "cannot safely sum"):
            _uses_scaled_sqlite_decimal_sum(
                models.DecimalField(max_digits=20, decimal_places=4),
                vendor="sqlite",
                source_count=10_000,
            )

    def test_all_null_metric_values_keep_count_and_null_totals(self):
        Customer.objects.filter(owner=self.user).update(credit_limit=None)

        result = self.execute(
            group_by=["active"],
            metrics=[
                {"id": "m1", "function": "count", "field": None},
                {"id": "m2", "function": "sum", "field": "customer__credit_limit"},
                {"id": "m3", "function": "avg", "field": "customer__credit_limit"},
            ],
        )

        self.assertEqual(result.rows[0]["metric:m1"], 2)
        self.assertIsNone(result.rows[0]["metric:m2"])
        self.assertIsNone(result.rows[0]["metric:m3"])

    def test_grouped_aggregates_are_executed_by_the_database(self):
        definition = validate_definition(
            summary_payload(
                group_by=["active"],
                metrics=[
                    {"id": "m1", "function": "count", "field": None},
                    {"id": "m2", "function": "sum", "field": "total"},
                ],
            ),
            self.catalog,
        )
        source = build_summary_source(definition, self.catalog, self.request)

        with CaptureQueriesContext(connection) as queries:
            execute_summary(source, definition, self.catalog)

        selects = [
            query["sql"].upper()
            for query in queries
            if query["sql"].lstrip().upper().startswith("SELECT")
        ]
        aggregate_queries = [
            sql
            for sql in selects
            if "GROUP BY" in sql and ("COUNT(" in sql or "SUM(" in sql)
        ]
        self.assertEqual(len(aggregate_queries), 1)

    @override_settings(QBE2_MAX_AGGREGATE_ROWS=1)
    def test_source_cap_rejects_before_aggregate_query(self):
        definition = validate_definition(
            summary_payload(
                metrics=[{"id": "m1", "function": "sum", "field": "total"}]
            ),
            self.catalog,
        )
        source = build_summary_source(definition, self.catalog, self.request)

        with CaptureQueriesContext(connection) as queries:
            with self.assertRaises(ValidationError):
                execute_summary(source, definition, self.catalog)

        self.assertFalse(
            any(
                "SUM(" in query["sql"].upper()
                for query in queries
                if query["sql"].lstrip().upper().startswith("SELECT")
            )
        )

    def test_ungrouped_empty_source_returns_zero_count_and_null_sum(self):
        Order.objects.filter(owner=self.user).delete()
        result = self.execute(
            metrics=[
                {"id": "m1", "function": "count", "field": None},
                {"id": "m2", "function": "sum", "field": "total"},
                {"id": "m3", "function": "avg", "field": "total"},
            ]
        )

        self.assertEqual(result.source_count, 0)
        self.assertEqual(
            result.rows,
            [{"metric:m1": 0, "metric:m2": None, "metric:m3": None}],
        )
