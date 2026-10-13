import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class Customer(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    city = models.CharField(max_length=80, blank=True)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Order(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    customer = models.ForeignKey(Customer, null=True, on_delete=models.SET_NULL)
    number = models.CharField(max_length=40, unique=True)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(
        max_length=12,
        choices=[
            ("paid", "Paid"),
            ("pending", "Pending"),
            ("overdue", "Overdue"),
        ],
        default="pending",
    )
    created_at = models.DateTimeField(default=timezone.now)
    due_date = models.DateField(null=True, blank=True)
    delivered = models.BooleanField(default=False)
    reference = models.UUIDField(default=uuid.uuid4)

    def __str__(self):
        return self.number
