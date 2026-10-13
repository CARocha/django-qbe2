from django_qbe2.registry import Report, register

from .models import Customer, Order


@register
class CustomerReport(Report):
    model = Customer
    fields = ("name",)

    def get_queryset(self, request):
        return Customer.objects.filter(owner=request.user)


@register
class OrderReport(Report):
    model = Order
    fields = ("number", "customer__name", "total")
    field_labels = {"customer__name": "Customer", "total": "Total amount"}

    def get_queryset(self, request):
        return Order.objects.filter(owner=request.user)
