from demo.reports.models import Customer, Order
from django_qbe2.registry import Report, register


@register
class CustomerReport(Report):
    model = Customer
    fields = ("name", "city", "active")
    field_labels = {"name": "Customer name"}

    def get_queryset(self, request):
        queryset = Customer.objects.all()
        return (
            queryset
            if request.user.is_superuser
            else queryset.filter(owner=request.user)
        )


@register
class OrderReport(Report):
    model = Order
    fields = (
        "number",
        "customer__name",
        "customer__city",
        "total",
        "status",
        "created_at",
        "due_date",
        "delivered",
        "reference",
    )
    field_labels = {
        "number": "Order number",
        "customer__name": "Customer",
        "customer__city": "City",
        "total": "Total amount",
    }

    def get_queryset(self, request):
        queryset = Order.objects.all()
        return (
            queryset
            if request.user.is_superuser
            else queryset.filter(owner=request.user)
        )
