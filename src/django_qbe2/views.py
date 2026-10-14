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
from django_qbe2.catalog import get_catalog
from django_qbe2.choices import choice_value
from django_qbe2.engine import build_queryset
from django_qbe2.execution import get_page
from django_qbe2.exports import csv_response
from django_qbe2.forms import OPERATOR_LABELS, QueryBuilderForm, payload_form_data
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
        except (json.JSONDecodeError, ValueError):
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
    choice_labels = {
        path: {
            value: escape(label)
            for value, label in catalog[form.definition.report].fields[path].choices
        }
        for path in form.definition.columns
    }
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
        "definition_json": json.dumps(form.payload),
        "limit": get_limits().max_rows,
        "table_rows": [
            tuple(
                choice_labels[path].get(row[path], row[path])
                for path in form.definition.columns
            )
            for row in page.rows
        ],
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
