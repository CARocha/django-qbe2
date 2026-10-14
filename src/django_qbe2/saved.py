"""Saved-query storage and object access, separate from business-data policies."""

import json

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _

from django_qbe2.limits import get_limits
from django_qbe2.models import SavedQuery


def accessible_queries(request, catalog):
    return SavedQuery.objects.filter(
        Q(owner=request.user)
        | Q(shared_with=request.user, definition__report__in=list(catalog))
    ).distinct()


def get_saved_query(request, pk, *, owner_only=False):
    scope = Q(owner=request.user)
    if not owner_only:
        scope |= Q(shared_with=request.user)
    try:
        return get_object_or_404(SavedQuery.objects.filter(scope).distinct(), pk=pk)
    except (ValidationError, ValueError):
        raise Http404("Saved query not available.") from None


def check_definition_size(payload):
    if len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) > 65536:
        raise ValidationError(_("A saved definition must not exceed 64 KiB."))


def create_saved_query(request, form, settings_form):
    check_definition_size(form.payload)
    with transaction.atomic():
        get_user_model()._default_manager.select_for_update().get(pk=request.user.pk)
        if (
            SavedQuery.objects.filter(owner=request.user).count()
            >= get_limits().max_saved_queries
        ):
            raise ValidationError(_("You have reached your saved-query limit."))
        query = SavedQuery.objects.create(
            owner=request.user,
            name=settings_form.cleaned_data["name"],
            definition=form.payload,
            page_size=form.cleaned_data["page_size"],
        )
        query.shared_with.set(settings_form.cleaned_data["shared_with"])
    return query
