from dataclasses import replace
from decimal import Decimal, getcontext

from django.core.exceptions import ValidationError
from django.db import models
from django.test import RequestFactory, TestCase

from django_qbe2.catalog import get_catalog
from django_qbe2.validation import validate_definition
from tests.fixtures import grant_view, make_staff
from tests.models import Customer, Order
from tests.test_summary_validation import summary_payload


class SummaryAggregationTests(TestCase):
    def setUp(self):
        user = make_staff("summary-math")
        grant_view(user, Order, Customer)
        request = RequestFactory().get("/")
        request.user = user
        self.catalog = get_catalog(request)
        self.report = self.catalog["tests.order"]

    def definition(self, metrics, **changes):
        return validate_definition(
            summary_payload(metrics=metrics, **changes), self.catalog
        )

    def accumulate(self, records, definition, source_limit=10_000):
        from django_qbe2.aggregation import accumulate_summary

        return accumulate_summary(
            records,
            definition,
            self.report,
            source_count=len(records),
            source_limit=source_limit,
        )

    def test_count_sum_and_average_numeric_semantics(self):
        definition = self.definition(
            [
                {"id": "m1", "function": "count", "field": None},
                {"id": "m2", "function": "sum", "field": "quantity"},
                {"id": "m3", "function": "avg", "field": "quantity"},
                {"id": "m4", "function": "sum", "field": "total"},
                {"id": "m5", "function": "avg", "field": "total"},
            ]
        )
        records = [
            {"quantity": 0, "total": Decimal("0.00")},
            {"quantity": 2, "total": Decimal("1.25")},
            {"quantity": None, "total": None},
        ]

        result = self.accumulate(records, definition)

        self.assertEqual(
            result.rows,
            [
                {
                    "metric:m1": 3,
                    "metric:m2": 2,
                    "metric:m3": Decimal("1.000000"),
                    "metric:m4": Decimal("1.25"),
                    "metric:m5": Decimal("0.625000"),
                }
            ],
        )
        self.assertEqual(result.source_count, 3)
        self.assertEqual(
            [column.key for column in result.columns],
            ["metric:m1", "metric:m2", "metric:m3", "metric:m4", "metric:m5"],
        )

    def test_decimal_precision_uses_local_context_sized_for_source_limit(self):
        definition = self.definition(
            [{"id": "m1", "function": "sum", "field": "total"}]
        )
        previous = getcontext().prec
        getcontext().prec = 7
        try:
            result = self.accumulate(
                [
                    {"total": Decimal("9999999999.99")},
                    {"total": Decimal("9999999999.99")},
                ],
                definition,
                source_limit=10_000,
            )
            self.assertEqual(result.rows[0]["metric:m1"], Decimal("19999999999.98"))
            self.assertEqual(getcontext().prec, 7)
        finally:
            getcontext().prec = previous

    def test_average_uses_half_even_at_six_fractional_places(self):
        integer = self.definition(
            [{"id": "m1", "function": "avg", "field": "quantity"}]
        )
        decimal = self.definition([{"id": "m1", "function": "avg", "field": "total"}])
        integer_rows = [{"quantity": 1}] + [{"quantity": 0}] * 127
        decimal_rows = [{"total": Decimal("1.00")}] + [{"total": Decimal("0.00")}] * 127

        self.assertEqual(
            self.accumulate(integer_rows, integer).rows[0]["metric:m1"],
            Decimal("0.007812"),
        )
        self.assertEqual(
            self.accumulate(decimal_rows, decimal).rows[0]["metric:m1"],
            Decimal("0.007812"),
        )

    def test_average_keeps_precision_for_large_decimal_fields(self):
        definition = self.definition(
            [{"id": "m1", "function": "avg", "field": "total"}]
        )
        total_field = self.report.fields["total"]
        report = replace(
            self.report,
            fields={
                **self.report.fields,
                "total": replace(
                    total_field,
                    django_field=models.DecimalField(max_digits=30, decimal_places=0),
                ),
            },
        )
        base = Decimal("100000000000000000000000000000")
        base_plus_one = Decimal("100000000000000000000000000001")
        records = [{"total": base_plus_one}] * 50 + [{"total": base}] * 9_949

        from django_qbe2.aggregation import accumulate_summary

        result = accumulate_summary(
            records,
            definition,
            report,
            source_count=len(records),
            source_limit=10_000,
        )

        self.assertEqual(
            result.rows[0]["metric:m1"],
            Decimal("100000000000000000000000000000.005001"),
        )

    def test_empty_sources_and_nonfinite_values_are_controlled(self):
        definition = self.definition(
            [
                {"id": "m1", "function": "count", "field": None},
                {"id": "m2", "function": "sum", "field": "total"},
                {"id": "m3", "function": "avg", "field": "quantity"},
            ]
        )
        result = self.accumulate([], definition)
        self.assertEqual(
            result.rows,
            [{"metric:m1": 0, "metric:m2": None, "metric:m3": None}],
        )
        with self.assertRaisesRegex(ValidationError, "finite"):
            self.accumulate([{"total": Decimal("NaN"), "quantity": 1}], definition)

        grouped = self.definition(
            [{"id": "m1", "function": "count", "field": None}],
            group_by=["total"],
        )
        with self.assertRaisesRegex(ValidationError, "finite"):
            self.accumulate([{"total": Decimal("Infinity")}], grouped)

    def test_grouped_empty_source_has_no_rows(self):
        definition = self.definition(
            [{"id": "m1", "function": "count", "field": None}],
            group_by=["active"],
        )
        self.assertEqual(self.accumulate([], definition).rows, [])

    def test_source_limit_is_enforced_before_calculation(self):
        definition = self.definition([{"id": "m1", "function": "count", "field": None}])
        with self.assertRaisesRegex(ValidationError, "Refine"):
            self.accumulate([{}, {}], definition, source_limit=1)

    def test_group_keys_are_typed_case_sensitive_and_namespaced(self):
        definition = self.definition(
            [{"id": "m1", "function": "count", "field": None}],
            group_by=["m1"],
        )
        result = self.accumulate([{"m1": "a"}, {"m1": "A"}, {"m1": "a"}], definition)

        self.assertEqual(
            result.rows,
            [
                {"group:m1": "a", "metric:m1": 2},
                {"group:m1": "A", "metric:m1": 1},
            ],
        )
        self.assertEqual(result.columns[0].choices[0][1], "Same label")
        self.assertEqual(result.columns[0].choices[1][1], "Same label")

    def test_multiple_group_keys_keep_null_blank_and_zero_values(self):
        definition = self.definition(
            [{"id": "m1", "function": "count", "field": None}],
            group_by=["due_date", "note", "quantity"],
        )
        records = [
            {"due_date": None, "note": "", "quantity": 0},
            {"due_date": None, "note": "", "quantity": 0},
            {"due_date": None, "note": "0", "quantity": 0},
        ]

        result = self.accumulate(records, definition)

        self.assertEqual(len(result.rows), 2)
        self.assertEqual(result.rows[0]["group:due_date"], None)
        self.assertEqual(result.rows[0]["group:note"], "")
        self.assertEqual(result.rows[0]["group:quantity"], 0)
        self.assertEqual(result.rows[0]["metric:m1"], 2)

    def test_false_group_value_is_retained(self):
        definition = self.definition(
            [{"id": "m1", "function": "count", "field": None}],
            group_by=["active"],
        )
        result = self.accumulate(
            [{"active": False}, {"active": True}, {"active": False}], definition
        )
        self.assertEqual(
            result.rows,
            [
                {"group:active": False, "metric:m1": 2},
                {"group:active": True, "metric:m1": 1},
            ],
        )
