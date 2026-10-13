from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission

from tests.models import Customer, Order


def make_staff(username: str):
    return get_user_model().objects.create_user(username=username, is_staff=True)


def grant_view(user, *models):
    for model in models:
        user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label=model._meta.app_label,
                codename=f"view_{model._meta.model_name}",
            )
        )


def make_orders(owner):
    customer = Customer.objects.create(
        owner=owner,
        name=f"{owner.username.title()} Customer",
        code=owner.username.upper(),
    )
    return [
        Order.objects.create(
            owner=owner,
            customer=customer,
            customer_by_code=customer,
            number=f"{owner.username[0].upper()}{suffix}",
            total=total,
        )
        for suffix, total in ((100, Decimal("100.01")), (200, Decimal("200.00")))
    ]
