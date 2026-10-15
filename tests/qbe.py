from django_qbe2.registry import Report, register
from tests.models import Customer, Order, Pet, Profile, Tag


@register
class CustomerReport(Report):
    model = Customer
    fields = ("name", "code", "credit_limit", "order__number", "pets__name")

    def get_queryset(self, request):
        return Customer.objects.filter(owner=request.user)


@register
class OrderReport(Report):
    model = Order
    fields = (
        "number",
        "total",
        "active",
        "quantity",
        "note",
        "m1",
        "reference",
        "created_at",
        "due_date",
        "customer__name",
        "customer__credit_limit",
        "customer_by_code__code",
        "customer__pets__name",
        "customer__profile__label",
    )

    def get_queryset(self, request):
        return Order.objects.filter(owner=request.user)


@register
class ProfileReport(Report):
    model = Profile
    fields = ("label", "customer__name")

    def get_queryset(self, request):
        return Profile.objects.filter(customer__owner=request.user)


@register
class PetReport(Report):
    model = Pet
    fields = ("name", "tags__label")

    def get_queryset(self, request):
        return Pet.objects.filter(customer__owner=request.user)


@register
class TagReport(Report):
    model = Tag
    fields = ("label", "pets__name")

    def get_queryset(self, request):
        return Tag.objects.filter(pets__customer__owner=request.user).distinct()
