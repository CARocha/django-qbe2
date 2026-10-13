from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from demo.reports.models import Customer, Order


class Command(BaseCommand):
    help = "Create synthetic reports for two users without setting login passwords."

    @transaction.atomic
    def handle(self, *args, **options):
        marker, _ = Group.objects.get_or_create(name="qbe2-demo-users")
        permissions = Permission.objects.filter(
            content_type__app_label="demo",
            codename__in=["view_customer", "view_order"],
        )
        for alias in ("alice", "bob"):
            user, created = get_user_model().objects.get_or_create(
                username=f"qbe2_demo_{alias}",
                defaults={
                    "is_staff": True,
                    "password": make_password(None),
                },
            )
            if not created and not user.groups.filter(pk=marker.pk).exists():
                raise CommandError(
                    f"Account {user.username} exists and is not a demo account."
                )
            user.groups.add(marker)
            user.user_permissions.add(*permissions)
            customers = [
                Customer.objects.get_or_create(
                    owner=user,
                    name=f"{name} ({alias})",
                    defaults={"city": city},
                )[0]
                for name, city in (
                    ("Atlas Studio", "Boston"),
                    ("Birch Market", "Seattle"),
                    ("Cedar Works", "Portland"),
                )
            ]
            for index in range(1, 13):
                order, _ = Order.objects.get_or_create(
                    number=f"QBE2-{alias.upper()}-{index:03}",
                    defaults={
                        "owner": user,
                        "customer": customers[(index - 1) % 3],
                        "total": Decimal("37.25") * index,
                        "status": ("paid", "pending", "overdue")[index % 3],
                        "delivered": index % 2 == 0,
                        "due_date": timezone.localdate() + timedelta(days=index - 6),
                    },
                )
                if order.owner_id != user.pk:
                    raise CommandError(
                        f"Order {order.number} belongs to another owner."
                    )
        if options["verbosity"]:
            self.stdout.write(
                self.style.SUCCESS("Demo ready: 6 customers and 24 orders.")
            )
            self.stdout.write(
                "Set a login password: python demo/manage.py "
                "changepassword qbe2_demo_alice"
            )
