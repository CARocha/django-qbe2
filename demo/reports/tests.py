import json

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import reverse


class DemoReportTests(TestCase):
    def test_owner_scope_and_total_filter(self):
        from demo.reports.models import Customer, Order

        alice = get_user_model().objects.create_user(username="alice", is_staff=True)
        bob = get_user_model().objects.create_user(username="bob", is_staff=True)
        alice.user_permissions.add(
            *Permission.objects.filter(
                content_type__app_label="demo",
                codename__in=["view_order", "view_customer"],
            )
        )
        own = Customer.objects.create(owner=alice, name="Atlas")
        foreign = Customer.objects.create(owner=bob, name="Birch")
        for number, owner, customer, total in (
            ("A100", alice, own, "100.01"),
            ("A200", alice, own, "200.00"),
            ("A300", alice, foreign, "300.00"),
            ("B100", bob, foreign, "400.00"),
        ):
            Order.objects.create(
                owner=owner, customer=customer, number=number, total=total
            )
        self.client.force_login(alice)
        response = self.client.post(
            reverse("django_qbe2:results"),
            {
                "definition": json.dumps(
                    {
                        "version": 1,
                        "report": "demo.order",
                        "columns": ["number", "customer__name", "total"],
                        "filters": [
                            {"field": "total", "operator": "gte", "value": "100"}
                        ],
                        "ordering": [],
                    }
                )
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [row[0] for row in response.context["table_rows"]], ["A100", "A200"]
        )
        self.assertNotContains(response, "Birch")


class SeedDemoTests(TestCase):
    def test_repeat_preserves_counts(self):
        from demo.reports.models import Customer, Order

        call_command("seed_demo", verbosity=0)
        original = list(
            Order.objects.order_by("number").values_list("number", "owner_id")
        )
        call_command("seed_demo", verbosity=0)
        self.assertEqual(Customer.objects.count(), 6)
        self.assertEqual(Order.objects.count(), 24)
        self.assertEqual(
            original,
            list(Order.objects.order_by("number").values_list("number", "owner_id")),
        )
        self.assertTrue(
            all(
                not user.has_usable_password()
                for user in get_user_model().objects.all()
            )
        )

    def test_existing_account_is_not_modified(self):
        existing = get_user_model().objects.create_user(username="qbe2_demo_alice")
        with self.assertRaises(CommandError):
            call_command("seed_demo", verbosity=0)
        existing.refresh_from_db()
        self.assertFalse(existing.is_staff)
        self.assertEqual(existing.user_permissions.count(), 0)
