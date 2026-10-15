from django_qbe2.registry import Report, register
from tests.models import Customer, Order, Profile


@register
class CustomerReport(Report):
    model = Customer
    fields = ("name", "code", "credit_limit")

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
    )

    def get_queryset(self, request):
        return Order.objects.filter(owner=request.user)


@register
class ProfileReport(Report):
    model = Profile
    fields = ("label", "customer__name")

    def get_queryset(self, request):
        return Profile.objects.filter(customer__owner=request.user)
