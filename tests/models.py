import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class Customer(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=40, unique=True)
    credit_limit = models.DecimalField(max_digits=12, decimal_places=2, null=True)


class Pet(models.Model):
    customer = models.ForeignKey(
        Customer, related_name="pets", on_delete=models.CASCADE
    )
    name = models.CharField(max_length=100)
    tags = models.ManyToManyField("Tag", through="PetTag", related_name="pets")


class Tag(models.Model):
    label = models.CharField(max_length=100)


class PetTag(models.Model):
    pet = models.ForeignKey(Pet, on_delete=models.CASCADE)
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE)


class Order(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    customer = models.ForeignKey(Customer, null=True, on_delete=models.SET_NULL)
    customer_by_code = models.ForeignKey(
        Customer,
        to_field="code",
        null=True,
        on_delete=models.SET_NULL,
        related_name="coded_orders",
    )
    number = models.CharField(max_length=100)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    due_date = models.DateField(null=True)
    reference = models.UUIDField(default=uuid.uuid4)
    quantity = models.IntegerField(default=0)
    note = models.TextField(blank=True)
    m1 = models.CharField(
        max_length=10,
        choices=(("a", "Same label"), ("A", "Same label")),
        default="a",
    )


class Profile(models.Model):
    customer = models.OneToOneField(Customer, on_delete=models.CASCADE)
    label = models.CharField(max_length=40)
