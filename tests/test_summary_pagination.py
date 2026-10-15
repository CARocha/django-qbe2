from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase

from django_qbe2.aggregation import accumulate_summary
from django_qbe2.catalog import get_catalog
from django_qbe2.validation import validate_definition
from tests.fixtures import grant_view, make_staff
from tests.models import Customer, Order
from tests.test_summary_validation import summary_payload


class SummaryPaginationTests(TestCase):
    def setUp(self):
        user = make_staff("summary-pages")
        grant_view(user, Order, Customer)
        request = RequestFactory().get("/")
        request.user = user
        self.catalog = get_catalog(request)
        self.report = self.catalog["tests.order"]

    def result(self, records, **changes):
        definition = validate_definition(
            summary_payload(
                group_by=["customer__name"],
                metrics=[
                    {"id": "m1", "function": "count", "field": None},
                    {"id": "m2", "function": "sum", "field": "total"},
                ],
                **changes,
            ),
            self.catalog,
        )
        return definition, accumulate_summary(
            records,
            definition,
            self.report,
            source_count=len(records),
            source_limit=100,
        )

    def page(self, records, *, page=1, page_size=50, max_rows=10, **changes):
        from django_qbe2.aggregation import paginate_summary

        definition, result = self.result(records, **changes)
        return paginate_summary(
            result,
            definition,
            page=page,
            page_size=page_size,
            max_rows=max_rows,
        )

    def test_orders_by_metric_then_group_tiebreaker(self):
        records = [
            {"customer__name": "beta", "total": Decimal("2.00")},
            {"customer__name": "alpha", "total": Decimal("2.00")},
            {"customer__name": "gamma", "total": Decimal("1.00")},
        ]
        page = self.page(
            records,
            ordering=[{"type": "metric", "id": "m2", "direction": "desc"}],
        )
        self.assertEqual(
            [row["group:customer__name"] for row in page.rows],
            ["alpha", "beta", "gamma"],
        )

    def test_group_order_handles_null_first_ascending_and_last_descending(self):
        records = [
            {"customer__name": "b", "total": Decimal("1.00")},
            {"customer__name": None, "total": Decimal("1.00")},
            {"customer__name": "a", "total": Decimal("1.00")},
        ]
        ascending = self.page(
            records,
            ordering=[{"type": "group", "field": "customer__name", "direction": "asc"}],
        )
        descending = self.page(
            records,
            ordering=[
                {"type": "group", "field": "customer__name", "direction": "desc"}
            ],
        )
        self.assertEqual(
            [row["group:customer__name"] for row in ascending.rows],
            [None, "a", "b"],
        )
        self.assertEqual(
            [row["group:customer__name"] for row in descending.rows],
            ["b", "a", None],
        )

    def test_cap_and_pages_keep_complete_group_metrics(self):
        records = [
            {"customer__name": "a", "total": Decimal("1.00")},
            {"customer__name": "a", "total": Decimal("2.00")},
            {"customer__name": "b", "total": Decimal("4.00")},
            {"customer__name": "c", "total": Decimal("8.00")},
        ]
        first = self.page(records, page_size=1, max_rows=2)
        second = self.page(records, page=2, page_size=1, max_rows=2)
        self.assertTrue(first.truncated)
        self.assertEqual(first.total_limited, 2)
        self.assertEqual(first.rows[0]["metric:m2"], Decimal("3.00"))
        self.assertEqual(second.rows[0]["metric:m2"], Decimal("4.00"))

    def test_invalid_page_and_size_are_rejected(self):
        records = [{"customer__name": "a", "total": Decimal("1.00")}]
        for page, page_size in ((0, 50), (True, 50), (2, 50), (1, 0), (1, 201)):
            with (
                self.subTest(page=page, page_size=page_size),
                self.assertRaises(ValidationError),
            ):
                self.page(records, page=page, page_size=page_size)
