"""Owner-managed definitions with explicit reader access and fresh validation."""

import json

from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from django_qbe2.access import require_qbe_access
from django_qbe2.catalog import get_catalog
from django_qbe2.saved import (
    accessible_queries,
    check_definition_size,
    create_saved_query,
    get_saved_query,
)
from django_qbe2.saved_forms import SavedQuerySettingsForm
from django_qbe2.views import builder_context, query_form, report_errors


def saved_context(request, title, **extra):
    return {
        **admin.site.each_context(request),
        "title": title,
        "site_header": _("Django QBE 2"),
        **extra,
    }


@require_qbe_access
@require_GET
@report_errors
def list_view(request):
    catalog = get_catalog(request)
    page = Paginator(accessible_queries(request, catalog), 25).get_page(
        request.GET.get("page")
    )
    return render(
        request,
        "django_qbe2/saved_list.html",
        saved_context(request, _("Saved queries"), saved_page=page),
    )


@require_qbe_access
@require_GET
@report_errors
def open_view(request, pk):
    query = get_saved_query(request, pk)
    catalog = get_catalog(request)
    try:
        check_definition_size(query.definition)
    except ValidationError:
        form = None
    else:
        form = query_form(
            request,
            catalog,
            {
                "definition": json.dumps(query.definition),
                "page_size": str(query.page_size),
            },
        )
    if form is None or not form.is_valid():
        return render(
            request,
            "django_qbe2/saved_invalid.html",
            saved_context(request, _("Saved query unavailable")),
            status=400,
        )
    return render(
        request,
        "django_qbe2/builder.html",
        {**builder_context(request, catalog, form), "saved_query": query},
    )


def save_error(request, form, save_form, query=None):
    return render(
        request,
        "django_qbe2/saved_save.html",
        saved_context(
            request,
            _("Save query"),
            form=form,
            save_form=save_form,
            saved_query=query,
            definition_json=request.POST.get("definition", ""),
            page_size=request.POST.get("page_size", "50"),
        ),
        status=400,
    )


@require_qbe_access
@require_POST
@report_errors
def create_view(request):
    form = query_form(request, get_catalog(request))
    save_form = SavedQuerySettingsForm(request.POST, owner=request.user)
    if form.is_valid() and save_form.is_valid():
        try:
            query = create_saved_query(request, form, save_form)
        except ValidationError as error:
            save_form.add_error(None, error)
        else:
            messages.success(request, _("Query saved."))
            return redirect("django_qbe2:saved_open", pk=query.pk)
    return save_error(request, form, save_form)


@require_qbe_access
@require_POST
@report_errors
def update_view(request, pk):
    query = get_saved_query(request, pk, owner_only=True)
    form = query_form(request, get_catalog(request))
    save_form = SavedQuerySettingsForm(request.POST, owner=request.user)
    if form.is_valid() and save_form.is_valid():
        try:
            check_definition_size(form.payload)
        except ValidationError as error:
            save_form.add_error(None, error)
        else:
            query.name = save_form.cleaned_data["name"]
            query.definition = form.payload
            query.page_size = form.cleaned_data["page_size"]
            query.save(update_fields=["name", "definition", "page_size", "updated_at"])
            messages.success(request, _("Saved query updated."))
            return redirect("django_qbe2:saved_open", pk=query.pk)
    return save_error(request, form, save_form, query)


@require_qbe_access
@require_http_methods(["GET", "POST"])
@report_errors
def settings_view(request, pk):
    query = get_saved_query(request, pk, owner_only=True)
    username_field = get_user_model().USERNAME_FIELD
    form = SavedQuerySettingsForm(
        request.POST if request.method == "POST" else None,
        owner=request.user,
        initial={
            "name": query.name,
            "shared_with": "\n".join(
                str(value)
                for value in query.shared_with.values_list(username_field, flat=True)
            ),
        },
    )
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            query.name = form.cleaned_data["name"]
            query.save(update_fields=["name", "updated_at"])
            query.shared_with.set(form.cleaned_data["shared_with"])
        messages.success(request, _("Name and sharing updated."))
        return redirect("django_qbe2:saved_list")
    return render(
        request,
        "django_qbe2/saved_settings.html",
        saved_context(request, _("Name and sharing"), form=form, saved_query=query),
        status=400 if request.method == "POST" else 200,
    )


@require_qbe_access
@require_http_methods(["GET", "POST"])
@report_errors
def delete_view(request, pk):
    query = get_saved_query(request, pk, owner_only=True)
    if request.method == "POST":
        query.delete()
        messages.success(request, _("Saved query deleted."))
        return redirect("django_qbe2:saved_list")
    return render(
        request,
        "django_qbe2/saved_delete.html",
        saved_context(request, _("Delete saved query"), saved_query=query),
    )
