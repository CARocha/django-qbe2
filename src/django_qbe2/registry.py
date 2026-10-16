"""Explicit report configuration; importing this module does not query a database."""

from abc import ABC, abstractmethod
from typing import ClassVar

from django.core.exceptions import ImproperlyConfigured
from django.db.models import Model, QuerySet
from django.http import HttpRequest
from django.test import RequestFactory


class Report(ABC):
    model: ClassVar[type[Model]]
    fields: ClassVar[tuple[str, ...]] = ()
    field_labels: ClassVar[dict[str, str]] = {}

    @abstractmethod
    def get_queryset(self, request: HttpRequest) -> QuerySet:
        """Return the rows this request is allowed to read."""

    def get_scheduled_request(self, *, owner, schedule) -> HttpRequest:
        """Build request context for a scheduled execution.

        Override this when a report policy needs context supplied by
        middleware, such as a tenant. The scheduled runner verifies the owner.
        """
        request = RequestFactory().get("/")
        request.user = owner
        return request


_reports: dict[str, Report] = {}


def register(report_class: type[Report]) -> type[Report]:
    if not isinstance(report_class, type) or not issubclass(report_class, Report):
        raise ImproperlyConfigured("Register a Report subclass.")
    try:
        report = report_class()
    except TypeError as error:
        raise ImproperlyConfigured(
            "Every report must define get_queryset()."
        ) from error
    model = getattr(report, "model", None)
    if not isinstance(model, type) or not issubclass(model, Model):
        raise ImproperlyConfigured("Every report must declare a Django model.")
    report_id = model._meta.label_lower
    if report_id in _reports:
        raise ImproperlyConfigured(f"Report {report_id} is already registered.")
    _reports[report_id] = report
    return report_class


def get_reports() -> tuple[Report, ...]:
    return tuple(_reports.values())
