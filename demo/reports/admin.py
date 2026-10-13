from django.contrib import admin

from demo.reports.models import Customer, Order


class OwnedAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return (
            queryset
            if request.user.is_superuser
            else queryset.filter(owner=request.user)
        )

    def get_readonly_fields(self, request, obj=None):
        return () if request.user.is_superuser else ("owner",)

    def save_model(self, request, obj, form, change):
        if not request.user.is_superuser:
            obj.owner = request.user
        super().save_model(request, obj, form, change)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "customer" and not request.user.is_superuser:
            kwargs["queryset"] = Customer.objects.filter(owner=request.user)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Customer)
class CustomerAdmin(OwnedAdmin):
    list_display = ("name", "city", "active")
    search_fields = ("name", "city")


@admin.register(Order)
class OrderAdmin(OwnedAdmin):
    list_display = ("number", "customer", "total", "status")
    list_filter = ("status",)
    search_fields = ("number",)
