"""Owner-only screens for creating and managing scheduled report snapshots."""

import json
from datetime import UTC
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import OuterRef, Subquery
from django.http import Http404, HttpRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from django_qbe2.access import require_qbe_access
from django_qbe2.catalog import get_catalog
from django_qbe2.models import ScheduledReport, ScheduledReportRun
from django_qbe2.saved import check_definition_size
from django_qbe2.scheduled_forms import ScheduledReportForm
from django_qbe2.scheduling import next_run_at
from django_qbe2.views import builder_context, query_form, report_errors


def schedule_context(request, title, **extra):
    return {
        **admin.site.each_context(request),
        "title": title,
        "site_header": _("Django QBE 2"),
        **extra,
    }


def get_owned_schedule(request: HttpRequest, pk) -> ScheduledReport:
    try:
        schedule_id = UUID(str(pk))
    except (TypeError, ValueError) as error:
        raise Http404("Scheduled report not available.") from error
    return get_object_or_404(ScheduledReport, pk=schedule_id, owner=request.user)


def _decorate_schedule(schedule):
    try:
        selected_zone = ZoneInfo(schedule.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        selected_zone = UTC
    schedule.next_run_local = timezone.localtime(schedule.next_run_at, selected_zone)
    if schedule.last_run_at:
        schedule.last_run_local = timezone.localtime(
            schedule.last_run_at, selected_zone
        )
    weekdays = (
        _("Monday"),
        _("Tuesday"),
        _("Wednesday"),
        _("Thursday"),
        _("Friday"),
        _("Saturday"),
        _("Sunday"),
    )
    schedule.weekday_label = (
        weekdays[schedule.weekday]
        if schedule.weekday is not None and 0 <= schedule.weekday < 7
        else ""
    )
    return schedule


def _next_run(form):
    return next_run_at(
        frequency=form.cleaned_data["frequency"],
        weekday=form.cleaned_data["weekday"],
        local_time=form.cleaned_data["local_time"],
        timezone_name=form.cleaned_data["timezone"],
        after=timezone.now(),
    )


def _definition_json(definition):
    return json.dumps(definition, separators=(",", ":"))


def _render_schedule_form(request, form, schedule_form, *, schedule=None, status=200):
    return render(
        request,
        "django_qbe2/scheduled_form.html",
        schedule_context(
            request,
            _("Edit scheduled report") if schedule else _("Schedule report"),
            query_form=form,
            schedule_form=schedule_form,
            schedule=schedule,
            definition_json=_definition_json(form.payload),
            page_size=form.cleaned_data["page_size"],
            schedule_config=True,
        ),
        status=status,
    )


@require_qbe_access
@require_GET
@report_errors
def list_view(request):
    last_runs = ScheduledReportRun.objects.filter(schedule=OuterRef("pk")).order_by(
        "-scheduled_for"
    )
    queryset = ScheduledReport.objects.filter(owner=request.user).annotate(
        last_run_status=Subquery(last_runs.values("status")[:1]),
        last_run_at=Subquery(last_runs.values("finished_at")[:1]),
    )
    page = Paginator(queryset.order_by("next_run_at", "id"), 25).get_page(
        request.GET.get("page")
    )
    for schedule in page.object_list:
        _decorate_schedule(schedule)
    return render(
        request,
        "django_qbe2/scheduled_list.html",
        schedule_context(request, _("Scheduled reports"), schedule_page=page),
    )


@require_qbe_access
@require_GET
@report_errors
def detail_view(request, pk):
    schedule = _decorate_schedule(get_owned_schedule(request, pk))
    try:
        selected_zone = ZoneInfo(schedule.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        selected_zone = UTC
    runs = list(schedule.runs.all()[:20])
    for run in runs:
        run.scheduled_for_local = timezone.localtime(run.scheduled_for, selected_zone)
    return render(
        request,
        "django_qbe2/scheduled_detail.html",
        schedule_context(
            request,
            schedule.name,
            schedule=schedule,
            runs=runs,
            recipient_count=len(schedule.recipients),
        ),
    )


@require_qbe_access
@require_POST
@report_errors
def create_view(request):
    catalog = get_catalog(request)
    form = query_form(request, catalog)
    if not form.is_valid():
        return render(
            request,
            "django_qbe2/builder.html",
            builder_context(request, catalog, form),
            status=400,
        )
    bound_config = request.POST.get("schedule_config") == "1"
    initial = {
        "frequency": ScheduledReport.Frequency.DAILY,
        "local_time": "09:00",
        "timezone": timezone.get_current_timezone_name(),
        "format": ScheduledReport.OutputFormat.CSV,
    }
    schedule_form = ScheduledReportForm(
        request.POST if bound_config else None,
        initial=initial,
    )
    if not bound_config:
        return _render_schedule_form(request, form, schedule_form)
    if not schedule_form.is_valid():
        return _render_schedule_form(request, form, schedule_form, status=400)
    try:
        check_definition_size(form.payload)
        next_run = _next_run(schedule_form)
    except ValidationError as error:
        schedule_form.add_error(None, error)
        return _render_schedule_form(request, form, schedule_form, status=400)
    schedule = ScheduledReport.objects.create(
        owner=request.user,
        name=schedule_form.cleaned_data["name"],
        definition=form.payload,
        page_size=form.cleaned_data["page_size"],
        frequency=schedule_form.cleaned_data["frequency"],
        weekday=schedule_form.cleaned_data["weekday"],
        local_time=schedule_form.cleaned_data["local_time"],
        timezone=schedule_form.cleaned_data["timezone"],
        recipients=schedule_form.cleaned_data["recipients"],
        format=schedule_form.cleaned_data["format"],
        next_run_at=next_run,
    )
    messages.success(request, _("Scheduled report created."))
    return redirect("django_qbe2:scheduled_detail", pk=schedule.pk)


def _initial_schedule_form(schedule):
    return {
        "name": schedule.name,
        "frequency": schedule.frequency,
        "weekday": "" if schedule.weekday is None else str(schedule.weekday),
        "local_time": schedule.local_time,
        "timezone": schedule.timezone,
        "recipients": "\n".join(schedule.recipients),
        "format": schedule.format,
    }


@require_qbe_access
@require_http_methods(["GET", "POST"])
@report_errors
def edit_view(request, pk):
    schedule = get_owned_schedule(request, pk)
    catalog = get_catalog(request)
    form = query_form(
        request,
        catalog,
        {
            "definition": _definition_json(schedule.definition),
            "page_size": str(schedule.page_size),
        },
    )
    if not form.is_valid():
        return render(
            request,
            "django_qbe2/saved_invalid.html",
            schedule_context(request, _("Scheduled report unavailable")),
            status=400,
        )
    bound_config = (
        request.method == "POST" and request.POST.get("schedule_config") == "1"
    )
    schedule_form = ScheduledReportForm(
        request.POST if bound_config else None,
        initial=_initial_schedule_form(schedule),
    )
    if not bound_config:
        return _render_schedule_form(request, form, schedule_form, schedule=schedule)
    if not schedule_form.is_valid():
        return _render_schedule_form(
            request, form, schedule_form, schedule=schedule, status=400
        )
    try:
        next_run = _next_run(schedule_form)
    except ValidationError as error:
        schedule_form.add_error(None, error)
        return _render_schedule_form(
            request, form, schedule_form, schedule=schedule, status=400
        )
    for field in (
        "name",
        "frequency",
        "weekday",
        "local_time",
        "timezone",
        "recipients",
        "format",
    ):
        setattr(schedule, field, schedule_form.cleaned_data[field])
    schedule.next_run_at = next_run
    schedule.enabled = True
    schedule.save()
    messages.success(request, _("Scheduled report updated."))
    return redirect("django_qbe2:scheduled_detail", pk=schedule.pk)


@require_qbe_access
@require_GET
@report_errors
def definition_view(request, pk):
    schedule = get_owned_schedule(request, pk)
    catalog = get_catalog(request)
    form = query_form(
        request,
        catalog,
        {
            "definition": _definition_json(schedule.definition),
            "page_size": str(schedule.page_size),
        },
    )
    if not form.is_valid():
        return render(
            request,
            "django_qbe2/saved_invalid.html",
            schedule_context(request, _("Scheduled report unavailable")),
            status=400,
        )
    return render(
        request,
        "django_qbe2/builder.html",
        {
            **builder_context(request, catalog, form),
            "scheduled_report": schedule,
        },
    )


@require_qbe_access
@require_POST
@report_errors
def update_definition_view(request, pk):
    schedule = get_owned_schedule(request, pk)
    catalog = get_catalog(request)
    form = query_form(request, catalog)
    if not form.is_valid():
        return render(
            request,
            "django_qbe2/builder.html",
            {
                **builder_context(request, catalog, form),
                "scheduled_report": schedule,
            },
            status=400,
        )
    try:
        check_definition_size(form.payload)
    except ValidationError as error:
        form.add_error(None, error)
        return render(
            request,
            "django_qbe2/builder.html",
            {
                **builder_context(request, catalog, form),
                "scheduled_report": schedule,
            },
            status=400,
        )
    schedule.definition = form.payload
    schedule.page_size = form.cleaned_data["page_size"]
    schedule.save(update_fields=["definition", "page_size", "updated_at"])
    messages.success(request, _("Scheduled report definition updated."))
    return redirect("django_qbe2:scheduled_detail", pk=schedule.pk)


@require_qbe_access
@require_POST
@report_errors
def pause_view(request, pk):
    schedule = get_owned_schedule(request, pk)
    schedule.enabled = False
    schedule.save(update_fields=["enabled", "updated_at"])
    messages.success(request, _("Scheduled report paused."))
    return redirect("django_qbe2:scheduled_detail", pk=schedule.pk)


@require_qbe_access
@require_POST
@report_errors
def resume_view(request, pk):
    schedule = get_owned_schedule(request, pk)
    try:
        schedule.next_run_at = next_run_at(
            frequency=schedule.frequency,
            weekday=schedule.weekday,
            local_time=schedule.local_time,
            timezone_name=schedule.timezone,
            after=timezone.now(),
        )
    except ValidationError as error:
        messages.error(request, error.messages)
        return redirect("django_qbe2:scheduled_detail", pk=schedule.pk)
    schedule.enabled = True
    schedule.save(update_fields=["enabled", "next_run_at", "updated_at"])
    messages.success(request, _("Scheduled report resumed."))
    return redirect("django_qbe2:scheduled_detail", pk=schedule.pk)


@require_qbe_access
@require_http_methods(["GET", "POST"])
@report_errors
def delete_view(request, pk):
    schedule = get_owned_schedule(request, pk)
    if request.method == "POST":
        schedule.delete()
        messages.success(request, _("Scheduled report deleted."))
        return redirect("django_qbe2:scheduled_list")
    return render(
        request,
        "django_qbe2/scheduled_delete.html",
        schedule_context(request, _("Delete scheduled report"), schedule=schedule),
    )
