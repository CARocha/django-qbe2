import json
import logging
from functools import wraps

from django.contrib import admin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.html import escape
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST

from django_qbe2.access import require_qbe_access
from django_qbe2.aggregation import paginate_summary
from django_qbe2.catalog import get_catalog
from django_qbe2.choices import choice_value
from django_qbe2.definitions import SummaryDefinition
from django_qbe2.engine import build_queryset, build_summary_source
from django_qbe2.execution import execute_summary, get_page
from django_qbe2.exports import csv_response
from django_qbe2.forms import OPERATOR_LABELS, QueryBuilderForm, payload_form_data
from django_qbe2.group_forms import (
    compact_controls,
    default_group_data,
    validate_structure,
)
from django_qbe2.limits import get_limits
from django_qbe2.saved import get_saved_query
from django_qbe2.saved_forms import SavedQueryNameForm
from django_qbe2.validation import validate_definition

logger = logging.getLogger(__name__)


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
    fields = catalog[form.report_id].fields if form.report_id in catalog else {}
    return {
        **admin.site.each_context(request),
        "title": _("Query by Example"),
        "form": form,
        "catalog": catalog,
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
    return render(
        request, "django_qbe2/builder.html", builder_context(request, catalog, form)
    )


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
        if isinstance(original, dict) and original.get("version") == 3:
            report_id = original.get("report")
            fallback = (
                next(iter(catalog.get(report_id).fields), "")
                if report_id in catalog
                else ""
            )
            data.setlist("columns", [fallback] if fallback else [])
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


def builder_action(request, catalog, saved_query):
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
        {**builder_context(request, catalog, form), "saved_query": saved_query},
        status=status,
    )


@require_qbe_access
@require_POST
@report_errors
def results_view(request: HttpRequest):
    catalog = get_catalog(request)
    saved_query = None
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
        return builder_action(request, catalog, saved_query)
    form = query_form(request, catalog)
    if not form.is_valid() or request.POST.get("action") == "edit":
        status = 200 if form.is_valid() else 400
        return render(
            request,
            "django_qbe2/builder.html",
            {**builder_context(request, catalog, form), "saved_query": saved_query},
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
            {**builder_context(request, catalog, form), "saved_query": saved_query},
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
                choice_labels[column.key].get(row[column.key], row[column.key])
                for column in output_columns
            )
            for row in page.rows
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
                choice_labels[path].get(row[path], row[path])
                for path in form.definition.columns
            )
            for row in page.rows
        ]
    context = {
        **admin.site.each_context(request),
        "title": _("Report results"),
        "site_header": _("Django QBE 2"),
        "saved_query": saved_query,
        "owns_saved_query": saved_query is not None
        and saved_query.owner_id == request.user.pk,
        "save_form": SavedQueryNameForm(
            initial={"name": saved_query.name if saved_query else ""}
        ),
        "page": page,
        "is_summary": is_summary,
        "is_grouped": is_summary and bool(form.definition.group_by),
        "source_count": summary_result.source_count if is_summary else None,
        "group_count": len(summary_result.rows) if is_summary else None,
        "definition_json": json.dumps(form.payload),
        "limit": get_limits().max_rows,
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
    form = query_form(request, catalog)
    if not form.is_valid():
        return render(
            request,
            "django_qbe2/builder.html",
            builder_context(request, catalog, form),
            status=400,
        )
    queryset = build_queryset(form.definition, catalog, request)
    return csv_response(queryset, form.definition, catalog)
