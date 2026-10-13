from decimal import Decimal

from django.test import TestCase


class FixtureTests(TestCase):
    def test_independent_owners(self):
        from tests.fixtures import make_orders, make_staff
        from tests.models import Order

        alice = make_staff("alice")
        bob = make_staff("bob")
        make_orders(alice)
        make_orders(bob)
        self.assertEqual(Order.objects.filter(owner=alice).count(), 2)
        self.assertEqual(Order.objects.filter(owner=bob).count(), 2)
        self.assertEqual(
            Order.objects.filter(owner=alice).first().total, Decimal("100.01")
        )
