"""Rebuild an owner's current report authorization for scheduled execution."""

from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpRequest
from django.utils.translation import gettext as _

from django_qbe2.catalog import ReportSpec, describe_report, get_catalog
from django_qbe2.definitions import QueryDefinition, SummaryDefinition
from django_qbe2.limits import get_limits
from django_qbe2.models import ScheduledReport
from django_qbe2.registry import get_reports
from django_qbe2.saved import check_definition_size
from django_qbe2.validation import validate_definition


@dataclass(frozen=True)
class ScheduledExecutionContext:
    request: HttpRequest
    catalog: dict[str, ReportSpec]
    definition: QueryDefinition | SummaryDefinition
    report_spec: ReportSpec
    page_size: int


def _definition_field_paths(payload: dict) -> set[str]:
    paths = set()
    paths.update(item for item in payload.get("columns", ()) if isinstance(item, str))
    paths.update(item for item in payload.get("group_by", ()) if isinstance(item, str))
    for key in ("filters", "ordering", "metrics"):
        for item in payload.get(key, ()):
            if isinstance(item, dict) and isinstance(item.get("field"), str):
                paths.add(item["field"])

    def visit_group(group):
        if not isinstance(group, dict):
            return
        if isinstance(group.get("field"), str):
            paths.add(group["field"])
        for child in group.get("children", ()):
            visit_group(child)

    visit_group(payload.get("where"))
    return paths


def prepare_scheduled_execution(
    schedule: ScheduledReport,
) -> ScheduledExecutionContext:
    """Return a fresh, owner-bound context after revalidating stored policy."""
    owner = get_user_model()._default_manager.get(pk=schedule.owner_id)
    if not (owner.is_authenticated and owner.is_active and owner.is_staff):
        raise PermissionDenied
    if not isinstance(schedule.timezone, str):
        raise ValidationError({"timezone": _("Invalid schedule timezone.")})
    try:
        request_timezone = ZoneInfo(schedule.timezone)
    except (ValueError, ZoneInfoNotFoundError) as error:
        raise ValidationError({"timezone": _("Invalid schedule timezone.")}) from error
    try:
        check_definition_size(schedule.definition)
        if not 1 <= schedule.page_size <= get_limits().max_page_size:
            raise ValidationError({"page_size": _("Invalid scheduled page size.")})
        reports = {report.model._meta.label_lower: report for report in get_reports()}
        report = reports.get(schedule.definition.get("report"))
        if report is None:
            raise PermissionDenied
        if not owner.has_perm(
            f"{report.model._meta.app_label}.view_{report.model._meta.model_name}"
        ):
            raise PermissionDenied
        request = report.get_scheduled_request(owner=owner, schedule=schedule)
        if not isinstance(request, HttpRequest):
            raise PermissionDenied
        if getattr(getattr(request, "user", None), "pk", None) != owner.pk:
            raise PermissionDenied
        request.user = owner
        request.timezone = request_timezone
        catalog = get_catalog(request)
        report_id = schedule.definition.get("report")
        if report_id not in catalog:
            raise PermissionDenied
        full_spec = describe_report(report, reports)
        requested_paths = _definition_field_paths(schedule.definition)
        if any(
            path in full_spec.fields and path not in catalog[report_id].fields
            for path in requested_paths
        ):
            raise PermissionDenied
        definition = validate_definition(schedule.definition, catalog)
        report_spec = catalog[definition.report]
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        raise ValidationError(
            {"definition": _("Invalid scheduled report definition.")}
        ) from error
    return ScheduledExecutionContext(
        request=request,
        catalog=catalog,
        definition=definition,
        report_spec=report_spec,
        page_size=schedule.page_size,
    )
