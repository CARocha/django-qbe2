from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext

from django_qbe2.validation import validate_definition
from tests import test_engine
from tests.fixtures import grant_view, make_orders, make_staff
from tests.models import Order
from tests.test_validation import order_payload


class PaginationTests(TestCase):
    setUp = test_engine.EngineTests.setUp
    query = test_engine.EngineTests.query

    def page(self, page=1, page_size=50):
        from django_qbe2.execution import get_page

        definition = validate_definition(order_payload(), self.catalog)
        return get_page(
            self.query(),
            definition,
            self.catalog,
            request=self.request,
            page=page,
            page_size=page_size,
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


class MultiValuedPaginationTests(TestCase):
    def setUp(self):
        from django.test import RequestFactory

        from django_qbe2.catalog import get_catalog
        from tests.models import Customer, Pet, Tag

        self.alice = make_staff("collection-page")
        grant_view(self.alice, Customer, Order, Pet, Tag)
        make_orders(self.alice)
        self.customer = Customer.objects.get(owner=self.alice)
        self.request = RequestFactory().get("/")
        self.request.user = self.alice
        self.catalog = get_catalog(self.request)

    def definition(self, *, report, columns, filters=(), ordering=()):
        from django_qbe2.validation import validate_definition

        return validate_definition(
            order_payload(
                report=report,
                columns=list(columns),
                filters=list(filters),
                ordering=list(ordering),
            ),
            self.catalog,
        )

    def page(self, definition, page=1, page_size=50):
        from django_qbe2.engine import build_queryset
        from django_qbe2.execution import get_page

        return get_page(
            build_queryset(definition, self.catalog, self.request),
            definition,
            self.catalog,
            request=self.request,
            page=page,
            page_size=page_size,
        )

    def test_two_collection_columns_are_independent_and_ordered(self):
        from tests.models import Pet

        Pet.objects.create(customer=self.customer, name="Milo")
        Pet.objects.create(customer=self.customer, name="Luna")
        definition = self.definition(
            report="tests.customer",
            columns=("name", "order__number", "pets__name"),
        )

        page = self.page(definition)

        self.assertEqual(page.total_limited, 1)
        self.assertEqual(page.rows[0]["order__number"], ("C100", "C200"))
        self.assertEqual(page.rows[0]["pets__name"], ("Milo", "Luna"))

    def test_empty_collection_is_an_empty_tuple(self):
        from tests.models import Customer

        empty = Customer.objects.create(
            owner=self.alice, name="Empty", code="EMPTY", credit_limit=None
        )
        definition = self.definition(
            report="tests.customer",
            columns=("name", "pets__name"),
            filters=({"field": "name", "operator": "exact", "value": "Empty"},),
        )

        page = self.page(definition)

        self.assertEqual(page.rows, [{"name": "Empty", "pets__name": ()}])
        self.assertEqual(page.rows[0]["name"], empty.name)

    def test_page_size_does_not_create_per_root_collection_queries(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from tests.models import Customer, Pet

        Pet.objects.create(customer=self.customer, name="Milo")
        other = Customer.objects.create(
            owner=self.alice, name="Other", code="OTHER", credit_limit=None
        )
        Pet.objects.create(customer=other, name="Luna")
        definition = self.definition(
            report="tests.customer", columns=("name", "pets__name")
        )
        with CaptureQueriesContext(connection) as one_row_queries:
            one_row = self.page(definition, page_size=1)
        with CaptureQueriesContext(connection) as two_row_queries:
            two_rows = self.page(definition, page_size=2)

        self.assertEqual(len(one_row.rows), 1)
        self.assertEqual(len(two_rows.rows), 2)
        self.assertEqual(len(one_row_queries), len(two_row_queries))

    def test_related_value_cap_is_enforced_without_truncating(self):
        from django.core.exceptions import ValidationError
        from django.test import override_settings

        from tests.models import Pet

        Pet.objects.create(customer=self.customer, name="Milo")
        Pet.objects.create(customer=self.customer, name="Luna")
        definition = self.definition(
            report="tests.customer", columns=("name", "pets__name")
        )
        with override_settings(QBE2_MAX_RELATED_VALUES=2):
            exact = self.page(definition)
            self.assertEqual(exact.rows[0]["pets__name"], ("Milo", "Luna"))
            Pet.objects.create(customer=self.customer, name="Pico")
            with self.assertRaises(ValidationError):
                self.page(definition)

    def test_related_values_follow_target_report_scope(self):
        from tests.models import Pet

        Pet.objects.create(customer=self.customer, name="Milo")
        pet_report = self.catalog["tests.pet"].report
        original = pet_report.get_queryset
        try:
            pet_report.get_queryset = lambda request: Pet.objects.none()
            definition = self.definition(
                report="tests.customer", columns=("name", "pets__name")
            )
            page = self.page(definition)
        finally:
            pet_report.get_queryset = original

        self.assertEqual(page.rows[0]["pets__name"], ())

    def test_duplicate_many_to_many_links_do_not_repeat_target(self):
        from tests.models import Pet, PetTag, Tag

        pet = Pet.objects.create(customer=self.customer, name="Milo")
        tag = Tag.objects.create(label="friendly")
        pet.tags.add(tag)
        PetTag.objects.create(pet=pet, tag=tag)
        definition = self.definition(
            report="tests.pet",
            columns=("name", "tags__label"),
            filters=({"field": "name", "operator": "exact", "value": "Milo"},),
        )

        page = self.page(definition)

        self.assertEqual(page.rows[0]["tags__label"], ("friendly",))

    def test_related_value_limit_must_be_positive(self):
        from django.core.exceptions import ImproperlyConfigured
        from django.test import override_settings

        from django_qbe2.limits import get_limits

        self.assertEqual(get_limits().max_related_values, 10_000)
        with override_settings(QBE2_MAX_RELATED_VALUES=0):
            with self.assertRaises(ImproperlyConfigured):
                get_limits()
