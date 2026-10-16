"""Expose navigation to QBE's authorized UI, never a raw definition editor."""

from django.contrib import admin
from django.shortcuts import redirect
from django.urls import path

from django_qbe2.models import SavedQuery, ScheduledReport


@admin.register(SavedQuery)
class SavedQueryAdmin(admin.ModelAdmin):
    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_staff

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_urls(self):
        return [
            path(
                "",
                self.admin_site.admin_view(self.changelist_view),
                name="django_qbe2_savedquery_changelist",
            )
        ]

    def changelist_view(self, request, extra_context=None):
        return redirect("django_qbe2:saved_list")


@admin.register(ScheduledReport)
class ScheduledReportAdmin(SavedQueryAdmin):
    def get_urls(self):
        return [
            path(
                "",
                self.admin_site.admin_view(self.changelist_view),
                name="django_qbe2_scheduledreport_changelist",
            )
        ]

    def changelist_view(self, request, extra_context=None):
        return redirect("django_qbe2:scheduled_list")
