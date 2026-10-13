from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext

from django_qbe2.validation import validate_definition
from tests import test_engine
from tests.models import Order
from tests.test_validation import order_payload


class PaginationTests(TestCase):
    setUp = test_engine.EngineTests.setUp
    query = test_engine.EngineTests.query

    def page(self, page=1, page_size=50):
        from django_qbe2.execution import get_page

        definition = validate_definition(order_payload(), self.catalog)
        return get_page(
            self.query(), definition, self.catalog, page=page, page_size=page_size
        )

    @override_settings(QBE2_MAX_ROWS=3)
    def test_bounded_total(self):
        for index in range(3):
            Order.objects.create(owner=self.alice, number=f"extra{index}", total="1.00")
        page = self.page(page_size=2)
        self.assertEqual(page.total_limited, 3)
        self.assertTrue(page.truncated)
        self.assertEqual(len(page.rows), 2)
        self.assertEqual(len(self.page(page=2, page_size=2).rows), 1)
        with self.assertRaises(ValidationError):
            self.page(page=3, page_size=2)

    @override_settings(QBE2_MAX_ROWS=2)
    def test_exact_limit_is_not_truncated(self):
        self.assertFalse(self.page().truncated)

    def test_empty_and_invalid_pages(self):
        Order.objects.filter(owner=self.alice).delete()
        page = self.page()
        self.assertEqual(page.rows, [])
        self.assertEqual(page.num_pages, 1)
        for number, size in ((0, 50), (-1, 50), (True, 50), (1, 201), (1, 0)):
            with (
                self.subTest(page=number, size=size),
                self.assertRaises(ValidationError),
            ):
                self.page(page=number, page_size=size)

    def test_query_count_is_independent_of_page_rows(self):
        with CaptureQueriesContext(connection) as first:
            one_row = self.page(page_size=1)
        with CaptureQueriesContext(connection) as second:
            two_rows = self.page(page_size=2)
        self.assertEqual(len(one_row.rows), 1)
        self.assertEqual(len(two_rows.rows), 2)
        self.assertEqual(len(first), len(second))
