import json
import logging
from dataclasses import asdict
from functools import wraps

from django.contrib import admin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.html import escape, format_html_join
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST

from django_qbe2.access import require_qbe_access
from django_qbe2.aggregation import paginate_summary
from django_qbe2.catalog import get_catalog
from django_qbe2.charting import build_bar_chart
from django_qbe2.choices import choice_value
from django_qbe2.definitions import SummaryDefinition
from django_qbe2.engine import build_queryset, build_summary_source
from django_qbe2.execution import execute_summary, get_page
from django_qbe2.explorer import build_explorer
from django_qbe2.exports import (
    csv_response,
    excel_available,
    summary_csv_response,
    summary_xlsx_response,
    xlsx_response,
)
from django_qbe2.forms import OPERATOR_LABELS, QueryBuilderForm, payload_form_data
from django_qbe2.group_forms import (
    compact_controls,
    default_group_data,
    validate_structure,
)
from django_qbe2.limits import get_limits
from django_qbe2.saved import get_saved_query
from django_qbe2.saved_forms import SavedQueryNameForm
from django_qbe2.summary_forms import compact_metrics, compact_summary_ordering
from django_qbe2.validation import validate_definition

logger = logging.getLogger(__name__)


def present_cell(value, labels):
    if isinstance(value, tuple):
        if not value:
            return None
        return format_html_join(
            ", ", "{}", ((labels.get(item, item),) for item in value)
        )
    return labels.get(value, value)


def report_errors(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        try:
            return view(request, *args, **kwargs)
        except (Http404, PermissionDenied):
            raise
        except Exception as error:
            # The HTTP boundary hides database details, even when DEBUG is enabled.
            logger.error("Report request failed (%s).", type(error).__name__)
            return HttpResponse(
                _("The report could not be completed. Please try again."), status=500
            )

    return wrapped


def builder_context(request, catalog, form):
    selected_report = catalog.get(form.report_id)
    fields = selected_report.fields if selected_report else {}
    explorer_data = (
        build_explorer(selected_report, catalog) if selected_report else None
    )
    return {
        **admin.site.each_context(request),
        "title": _("Query by Example"),
        "form": form,
        "catalog": catalog,
        "explorer_data": explorer_data,
        "explorer_json": asdict(explorer_data) if explorer_data else None,
        "has_reports": bool(catalog),
        "site_header": _("Django QBE 2"),
        "field_data": {
            path: {
                "operators": [
                    {"value": operator, "label": str(OPERATOR_LABELS[operator])}
                    for operator in field.operators
                ],
                "boolean": isinstance(field.django_field, models.BooleanField),
                "choices": [
                    {"value": choice_value(value), "label": label}
                    for value, label in field.choices
                ],
                "choices_declared": field.choices_declared,
            }
            for path, field in fields.items()
        },
        "widget_labels": {
            "choose": _("Choose a value"),
            "true": _("Yes (true)"),
            "false": _("No (false)"),
        },
    }


@require_qbe_access
@require_GET
@report_errors
def builder_view(request: HttpRequest):
    catalog = get_catalog(request)
    selected = request.GET.get("report")
    if selected and selected not in catalog:
        raise Http404("Report not available.")
    form = QueryBuilderForm(catalog=catalog, initial={"report": selected})
    context = builder_context(request, catalog, form)
    if not selected:
        context["explorer_data"] = None
        context["explorer_json"] = None
    return render(request, "django_qbe2/builder.html", context)


def query_form(request, catalog, data=None):
    original = None
    data = request.POST if data is None else data
    source = data
    if "definition" in source:
        try:
            original = json.loads(source["definition"])
        except (json.JSONDecodeError, ValueError, RecursionError):
            form = QueryBuilderForm(data, catalog=catalog)
            form.is_valid()
            form.add_error(None, _("Invalid query definition."))
            return form
        data = payload_form_data(
            original,
            page_size=source.get("page_size", str(get_limits().page_size)),
        )
    report_id = data.get("report")
    if report_id and report_id not in catalog:
        raise Http404("Report not available.")
    form = QueryBuilderForm(data, catalog=catalog)
    form.is_valid()
    if original is not None:
        try:
            definition = validate_definition(original, catalog)
        except ValidationError as error:
            for control, messages in error.message_dict.items():
                form.add_error(control if control in form.fields else None, messages)
        else:
            if form.is_valid():
                form.payload = original
                form.definition = definition
    return form


def builder_action(request, catalog, saved_query, scheduled_report=None):
    data = default_group_data(request.POST, get_limits()).copy()
    form = QueryBuilderForm(data, catalog=catalog, structure_only=True)
    status = 200
    try:
        if not form.groups.is_valid():
            raise ValidationError(_("Correct the condition groups below."))
        nodes, removed = validate_structure(form.groups.cleaned_data, get_limits())
        action, separator, identity = request.POST.get("action", "").partition(":")
        if not separator or identity not in nodes or identity in removed:
            raise ValidationError(_("Choose an available parent group."))
        prefix = "groups" if action == "add_group" else "filters"
        maximum = (
            get_limits().max_groups if prefix == "groups" else get_limits().max_filters
        )
        management = (
            form.groups.management_form
            if prefix == "groups"
            else form.filters.management_form
        )
        if not management.is_valid():
            raise ValidationError(_("Invalid condition controls."))
        data = compact_controls(data, form.groups, form.filters, removed, get_limits())
        count = int(data[f"{prefix}-TOTAL_FORMS"])
        if count >= maximum:
            raise ValidationError(_("The condition limit was reached."))
        if prefix == "groups":
            current = identity
            depth = 1
            while current != "root":
                current = nodes[current]["parent"]
                depth += 1
            if depth >= get_limits().max_group_depth:
                raise ValidationError(_("The condition group depth limit was reached."))
            new_id = next(
                f"g{index}"
                for index in range(1, maximum + 1)
                if f"g{index}" not in nodes
            )
            values = {"id": new_id, "parent": identity, "connector": "and"}
        else:
            values = {"group": identity}
        data[f"{prefix}-TOTAL_FORMS"] = str(count + 1)
        for key, value in values.items():
            data[f"{prefix}-{count}-{key}"] = value
        form = QueryBuilderForm(data, catalog=catalog, structure_only=True)
        added = (
            form.groups.forms[count]
            if prefix == "groups"
            else form.filters.forms[count]
        )
        added.fields["connector" if prefix == "groups" else "field"].widget.attrs[
            "autofocus"
        ] = True
    except (ValidationError, ValueError) as error:
        form.is_valid()
        form.add_error(
            None,
            error.messages
            if isinstance(error, ValidationError)
            else _("Invalid condition controls."),
        )
        status = 400
    return render(
        request,
        "django_qbe2/builder.html",
        {
            **builder_context(request, catalog, form),
            "saved_query": saved_query,
            "scheduled_report": scheduled_report,
        },
        status=status,
    )


def _replace_formset(data, prefix, rows, maximum):
    for key in list(data):
        if key.startswith(f"{prefix}-"):
            del data[key]
    data.update(
        {
            f"{prefix}-TOTAL_FORMS": str(len(rows)),
            f"{prefix}-INITIAL_FORMS": "0",
            f"{prefix}-MIN_NUM_FORMS": "0",
            f"{prefix}-MAX_NUM_FORMS": str(maximum),
        }
    )
    for index, row in enumerate(rows):
        for key, value in row.items():
            data[f"{prefix}-{index}-{key}"] = value


def summary_builder_action(request, catalog, saved_query, scheduled_report=None):
    limits = get_limits()
    data = default_group_data(request.POST, limits).copy()
    action = request.POST.get("action")
    status = 200
    try:
        if action == "apply_mode":
            mode = data.get("mode")
            if mode not in ("rows", "summary"):
                raise ValidationError(_("Choose Rows or Summary."))
            report_id = data.get("report")
            fields = catalog[report_id].fields if report_id in catalog else {}
            data.setlist("group_by", [])
            _replace_formset(
                data,
                "ordering",
                [{"field": "", "direction": "asc"}] if mode == "rows" else [],
                limits.max_ordering,
            )
            _replace_formset(data, "summary_ordering", [], limits.max_ordering)
            _replace_formset(
                data,
                "metrics",
                [{"id": "m1", "function": "count", "field": ""}],
                limits.max_metrics,
            )
            data.setlist("columns", list(fields)[:2] if mode == "rows" else [])
        elif action == "add_metric":
            form = QueryBuilderForm(data, catalog=catalog, structure_only=True)
            if not form.groups.is_valid():
                raise ValidationError(_("Correct the condition groups below."))
            validate_structure(form.groups.cleaned_data, limits)
            data = compact_metrics(data, form.metrics, limits.max_metrics)
            count = int(data["metrics-TOTAL_FORMS"])
            if count >= limits.max_metrics:
                raise ValidationError(_("The calculation limit was reached."))
            used = {data.get(f"metrics-{index}-id") for index in range(count)}
            identity = next(
                f"m{number}"
                for number in range(1, limits.max_metrics + 2)
                if f"m{number}" not in used
            )
            data.update(
                {
                    f"metrics-{count}-id": identity,
                    f"metrics-{count}-function": "",
                    f"metrics-{count}-field": "",
                    "metrics-TOTAL_FORMS": str(count + 1),
                    "mode": "summary",
                }
            )
        elif action == "add_summary_ordering":
            form = QueryBuilderForm(data, catalog=catalog, structure_only=True)
            if not form.groups.is_valid():
                raise ValidationError(_("Correct the conditions below."))
            validate_structure(form.groups.cleaned_data, limits)
            data = compact_summary_ordering(
                data, form.summary_ordering, limits.max_ordering
            )
            count = int(data["summary_ordering-TOTAL_FORMS"])
            if not count or data.get(f"summary_ordering-{count - 1}-target"):
                if count >= limits.max_ordering:
                    raise ValidationError(_("The ordering limit was reached."))
                data.update(
                    {
                        f"summary_ordering-{count}-target": "",
                        f"summary_ordering-{count}-direction": "asc",
                        "summary_ordering-TOTAL_FORMS": str(count + 1),
                    }
                )
            data["mode"] = "summary"
        else:
            raise ValidationError(_("Choose an available builder action."))
        form = QueryBuilderForm(data, catalog=catalog, structure_only=True)
        form.is_valid()
        if action == "add_metric" and form.metrics.forms:
            form.metrics.forms[-1].fields["function"].widget.attrs["autofocus"] = True
        if action == "add_summary_ordering" and form.summary_ordering.forms:
            form.summary_ordering.forms[-1].fields["target"].widget.attrs[
                "autofocus"
            ] = True
    except (ValidationError, ValueError) as error:
        form = QueryBuilderForm(data, catalog=catalog, structure_only=True)
        form.is_valid()
        form.add_error(
            None,
            error.messages
            if isinstance(error, ValidationError)
            else _("Invalid calculation controls."),
        )
        status = 400
    return render(
        request,
        "django_qbe2/builder.html",
        {
            **builder_context(request, catalog, form),
            "saved_query": saved_query,
            "scheduled_report": scheduled_report,
        },
        status=status,
    )


@require_qbe_access
@require_POST
@report_errors
def results_view(request: HttpRequest):
    catalog = get_catalog(request)
    saved_query = None
    scheduled_report = None
    if request.POST.get("scheduled_report"):
        from django_qbe2.scheduled_views import get_owned_schedule

        scheduled_report = get_owned_schedule(request, request.POST["scheduled_report"])
    if request.POST.get("saved_query"):
        saved_query = get_saved_query(request, request.POST["saved_query"])
        if (
            saved_query.owner_id != request.user.pk
            and saved_query.definition.get("report") not in catalog
        ):
            raise Http404("Report not available.")
    if request.POST.get("action", "").split(":", 1)[0] in (
        "add_condition",
        "add_group",
    ):
        return builder_action(request, catalog, saved_query, scheduled_report)
    if request.POST.get("action") in (
        "apply_mode",
        "add_metric",
        "add_summary_ordering",
    ):
        return summary_builder_action(request, catalog, saved_query, scheduled_report)
    form = query_form(request, catalog)
    if not form.is_valid() or request.POST.get("action") == "edit":
        status = 200 if form.is_valid() else 400
        return render(
            request,
            "django_qbe2/builder.html",
            {
                **builder_context(request, catalog, form),
                "saved_query": saved_query,
                "scheduled_report": scheduled_report,
            },
            status=status,
        )
    try:
        page_number = int(request.POST.get("page", "1"))
        summary_result = None
        if isinstance(form.definition, SummaryDefinition):
            queryset = build_summary_source(form.definition, catalog, request)
            summary_result = execute_summary(queryset, form.definition, catalog)
            page = paginate_summary(
                summary_result,
                form.definition,
                page=page_number,
                page_size=form.cleaned_data["page_size"],
                max_rows=get_limits().max_rows,
            )
        else:
            queryset = build_queryset(form.definition, catalog, request)
            page = get_page(
                queryset,
                form.definition,
                catalog,
                request=request,
                page=page_number,
                page_size=form.cleaned_data["page_size"],
            )
    except (ValidationError, ValueError) as error:
        messages = (
            error.messages
            if isinstance(error, ValidationError)
            else [_("Invalid page number.")]
        )
        form.add_error(None, messages)
        return render(
            request,
            "django_qbe2/builder.html",
            {
                **builder_context(request, catalog, form),
                "saved_query": saved_query,
                "scheduled_report": scheduled_report,
            },
            status=400,
        )
    is_summary = isinstance(form.definition, SummaryDefinition)
    if is_summary:
        output_columns = summary_result.columns
        choice_labels = {
            column.key: {value: escape(label) for value, label in column.choices}
            for column in output_columns
        }
        table_rows = [
            tuple(
                present_cell(row[column.key], choice_labels[column.key])
                for column in output_columns
            )
            for row in page.rows
        ]
        bar_chart = build_bar_chart(
            form.definition,
            summary_result,
            page,
            request.POST.get("chart_metric"),
        )
        chart_metrics = [
            {
                "id": metric.id,
                "label": next(
                    column.label
                    for column in output_columns
                    if column.key == f"metric:{metric.id}"
                ),
            }
            for metric in form.definition.metrics
        ]
    else:
        choice_labels = {
            path: {
                value: escape(label)
                for value, label in catalog[form.definition.report].fields[path].choices
            }
            for path in form.definition.columns
        }
        table_rows = [
            tuple(
                present_cell(row[path], choice_labels[path])
                for path in form.definition.columns
            )
            for row in page.rows
        ]
        bar_chart = None
        chart_metrics = []
    context = {
        **admin.site.each_context(request),
        "title": _("Report results"),
        "site_header": _("Django QBE 2"),
        "saved_query": saved_query,
        "scheduled_report": scheduled_report,
        "owns_saved_query": saved_query is not None
        and saved_query.owner_id == request.user.pk,
        "save_form": SavedQueryNameForm(
            initial={"name": saved_query.name if saved_query else ""}
        ),
        "page": page,
        "is_summary": is_summary,
        "is_grouped": is_summary and bool(form.definition.group_by),
        "chart_is_supported": is_summary and len(form.definition.group_by) == 1,
        "bar_chart": bar_chart,
        "chart_metrics": chart_metrics,
        "chart_metric": bar_chart.metric_id if bar_chart else "",
        "source_count": summary_result.source_count if is_summary else None,
        "group_count": len(summary_result.rows) if is_summary else None,
        "definition_json": json.dumps(form.payload),
        "limit": get_limits().max_rows,
        "excel_available": excel_available(),
        "table_rows": table_rows,
        "previous_page": page.page - 1,
        "next_page": page.page + 1,
    }
    return render(request, "django_qbe2/results.html", context)


@require_qbe_access
@require_POST
@report_errors
def export_view(request: HttpRequest):
    catalog = get_catalog(request)
    export_format = request.POST.get("export_format", "csv")
    if export_format not in ("csv", "xlsx"):
        return HttpResponse(_("Choose a supported export format."), status=400)
    if export_format == "xlsx" and not excel_available():
        return HttpResponse(
            _(
                "Excel export requires the optional dependency. "
                "Install django-qbe2[excel]."
            ),
            status=400,
        )
    form = query_form(request, catalog)
    if not form.is_valid():
        return render(
            request,
            "django_qbe2/builder.html",
            builder_context(request, catalog, form),
            status=400,
        )
    if isinstance(form.definition, SummaryDefinition):
        try:
            queryset = build_summary_source(form.definition, catalog, request)
            result = execute_summary(queryset, form.definition, catalog)
        except ValidationError as error:
            form.add_error(None, error.messages)
            return render(
                request,
                "django_qbe2/builder.html",
                builder_context(request, catalog, form),
                status=400,
            )
        if export_format == "xlsx":
            return summary_xlsx_response(result, form.definition)
        return summary_csv_response(result, form.definition)
    queryset = build_queryset(form.definition, catalog, request)
    try:
        if export_format == "xlsx":
            return xlsx_response(queryset, form.definition, catalog, request=request)
        return csv_response(queryset, form.definition, catalog, request=request)
    except ValidationError as error:
        form.add_error(None, error.messages)
        return render(
            request,
            "django_qbe2/builder.html",
            builder_context(request, catalog, form),
            status=400,
        )
