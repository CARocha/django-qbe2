from django.test import RequestFactory, TestCase

from tests.fixtures import grant_view, make_staff
from tests.models import Customer, Order


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
