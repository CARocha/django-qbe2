from collections.abc import Callable
from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest, HttpResponse
from django.urls import reverse

from django_qbe2.catalog import ReportSpec, get_catalog


def require_qbe_access(
    view: Callable[..., HttpResponse],
) -> Callable[..., HttpResponse]:
    @wraps(view)
    def wrapped(request: HttpRequest, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path(), reverse("admin:login"))
        if not request.user.is_active or not request.user.is_staff:
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapped


def visible_report(request: HttpRequest, report_id: str) -> ReportSpec:
    report = get_catalog(request).get(report_id)
    if report is None:
        raise Http404("Report not available.")
    return report
