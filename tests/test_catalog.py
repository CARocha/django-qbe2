from unittest.mock import patch

from django.test import RequestFactory, TestCase

from django_qbe2.registry import Report
from tests.fixtures import grant_view, make_staff
from tests.models import Customer, Order


class CatalogReport(Report):
    def __init__(self, model, fields):
        self.model = model
        self.fields = fields

    def get_queryset(self, request):
        return self.model._default_manager.all()


class CatalogTests(TestCase):
    def test_catalog_is_request_local(self):
        from django_qbe2.catalog import get_catalog

        alice = make_staff("alice")
        bob = make_staff("bob")
        grant_view(alice, Order, Customer)
        request = RequestFactory().get("/qbe/")
        request.user = alice
        first = get_catalog(request)
        self.assertIn("customer__name", first["tests.order"].fields)
        self.assertNotIn("owner", first["tests.order"].fields)
        request.user = bob
        self.assertEqual(get_catalog(request), {})
        request.user = alice
        self.assertEqual(
            tuple(get_catalog(request)["tests.order"].fields),
            tuple(first["tests.order"].fields),
        )

    def test_related_permission_is_required(self):
        from django_qbe2.catalog import get_catalog

        user = make_staff("restricted")
        grant_view(user, Order)
        request = RequestFactory().get("/qbe/")
        request.user = user
        fields = get_catalog(request)["tests.order"].fields
        self.assertIn("total", fields)
        self.assertNotIn("customer__name", fields)

    def test_catalog_describes_reverse_foreign_key_and_one_to_one_paths(self):
        from django_qbe2.catalog import describe_report
        from tests.models import Profile

        order = CatalogReport(Order, ("number",))
        profile = CatalogReport(Profile, ("label",))
        reports = {
            "tests.customer": CatalogReport(
                Customer, ("name", "order__number", "profile__label")
            ),
            "tests.order": order,
            "tests.profile": profile,
        }
        spec = describe_report(reports["tests.customer"], reports)

        self.assertEqual(len(spec.fields["order__number"].relations), 1)
        self.assertTrue(spec.fields["order__number"].multi_valued)
        self.assertEqual(len(spec.fields["profile__label"].relations), 1)
        self.assertFalse(spec.fields["profile__label"].multi_valued)

    def test_catalog_describes_forward_and_reverse_many_to_many_paths(self):
        from django_qbe2.catalog import describe_report
        from tests.models import Pet, Tag

        reports = {
            "tests.pet": CatalogReport(Pet, ("name", "tags__label")),
            "tests.tag": CatalogReport(Tag, ("label", "pets__name")),
        }
        pet = describe_report(reports["tests.pet"], reports)
        tag = describe_report(reports["tests.tag"], reports)

        self.assertTrue(pet.fields["tags__label"].multi_valued)
        self.assertTrue(tag.fields["pets__name"].multi_valued)

    def test_catalog_allows_two_hops_with_one_multivalued_edge(self):
        from django_qbe2.catalog import describe_report
        from tests.models import Pet

        reports = {
            "tests.order": CatalogReport(Order, ("number", "customer__pets__name")),
            "tests.customer": CatalogReport(Customer, ("name",)),
            "tests.pet": CatalogReport(Pet, ("name",)),
        }
        spec = describe_report(reports["tests.order"], reports)
        field = spec.fields["customer__pets__name"]

        self.assertEqual(len(field.relations), 2)
        self.assertTrue(field.multi_valued)

    def test_catalog_rejects_more_than_one_multivalued_edge(self):
        from django.core.exceptions import ImproperlyConfigured

        from django_qbe2.catalog import describe_report
        from tests.models import Pet, Tag

        reports = {
            "tests.customer": CatalogReport(Customer, ("name", "pets__tags__label")),
            "tests.pet": CatalogReport(Pet, ("name", "tags__label")),
            "tests.tag": CatalogReport(Tag, ("label",)),
        }
        with self.assertRaises(ImproperlyConfigured):
            describe_report(reports["tests.customer"], reports)

    def test_catalog_rejects_more_than_two_relationship_hops(self):
        from django.core.exceptions import ImproperlyConfigured

        from django_qbe2.catalog import describe_report
        from tests.models import Pet, Tag

        reports = {
            "tests.order": CatalogReport(Order, ("customer__pets__tags__label",)),
            "tests.customer": CatalogReport(Customer, ("name",)),
            "tests.pet": CatalogReport(Pet, ("name", "tags__label")),
            "tests.tag": CatalogReport(Tag, ("label",)),
        }
        with self.assertRaises(ImproperlyConfigured):
            describe_report(reports["tests.order"], reports)

    def test_catalog_rejects_unknown_terminal_field(self):
        from django.core.exceptions import ImproperlyConfigured

        from django_qbe2.catalog import describe_report
        from tests.models import Pet

        reports = {
            "tests.customer": CatalogReport(Customer, ("pets__missing",)),
            "tests.pet": CatalogReport(Pet, ("name",)),
        }
        with self.assertRaises(ImproperlyConfigured):
            describe_report(reports["tests.customer"], reports)

    def test_catalog_rejects_relation_as_terminal_field(self):
        from django.core.exceptions import ImproperlyConfigured

        from django_qbe2.catalog import describe_report

        reports = {"tests.customer": CatalogReport(Customer, ("owner",))}
        with self.assertRaises(ImproperlyConfigured):
            describe_report(reports["tests.customer"], reports)

    def test_catalog_hides_nested_path_without_intermediate_permission(self):
        from django_qbe2.catalog import get_catalog
        from django_qbe2.registry import _reports
        from tests.fixtures import grant_view
        from tests.models import Pet

        user = make_staff("nested_restricted")
        grant_view(user, Order, Pet)
        reports = {
            "tests.order": CatalogReport(Order, ("number", "customer__pets__name")),
            "tests.customer": CatalogReport(Customer, ("name",)),
            "tests.pet": CatalogReport(Pet, ("name",)),
        }
        request = RequestFactory().get("/qbe/")
        request.user = user

        with patch.dict(_reports, reports):
            self.assertNotIn(
                "customer__pets__name", get_catalog(request)["tests.order"].fields
            )
