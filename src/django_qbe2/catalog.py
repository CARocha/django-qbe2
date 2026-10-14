"""Validate explicit field paths and build a fresh catalog for each request."""

from dataclasses import dataclass, replace

from django.core.exceptions import FieldDoesNotExist, ImproperlyConfigured
from django.db import models
from django.http import HttpRequest

from django_qbe2.choices import field_choices
from django_qbe2.definitions import Scalar
from django_qbe2.registry import Report, get_reports

TEXT_OPERATORS = (
    "exact",
    "iexact",
    "contains",
    "icontains",
    "startswith",
    "istartswith",
)
ORDERED_OPERATORS = ("exact", "gt", "gte", "lt", "lte")


class CatalogConfigurationError(ImproperlyConfigured):
    def __init__(self, code: str, message: str):
        self.check_id = f"django_qbe2.{code}"
        super().__init__(message)


@dataclass(frozen=True)
class FieldSpec:
    path: str
    label: str
    django_field: models.Field
    operators: tuple[str, ...]
    relation_name: str | None = None
    target_report_id: str | None = None
    target_key: str | None = None
    choices: tuple[tuple[Scalar, str], ...] = ()
    choices_declared: bool = False


@dataclass(frozen=True)
class ReportSpec:
    id: str
    report: Report
    fields: dict[str, FieldSpec]


def field_operators(field: models.Field) -> tuple[str, ...]:
    if field.is_relation:
        raise CatalogConfigurationError("E003", "Select a scalar related field.")
    if isinstance(field, (models.CharField, models.TextField)):
        operators = TEXT_OPERATORS
    elif isinstance(
        field, (models.IntegerField, models.DecimalField, models.DateField)
    ):
        operators = ORDERED_OPERATORS
    elif isinstance(field, (models.BooleanField, models.UUIDField)):
        operators = ("exact",)
    else:
        raise CatalogConfigurationError(
            "E003", f"Unsupported field type: {type(field).__name__}."
        )
    return operators + (("isnull",) if field.null else ())


def describe_report(report: Report, reports: dict[str, Report]) -> ReportSpec:
    if not isinstance(report.fields, tuple) or not report.fields:
        raise CatalogConfigurationError(
            "E001", "Report fields must be a nonempty tuple."
        )
    if not isinstance(report.field_labels, dict) or any(
        key not in report.fields or not isinstance(value, str)
        for key, value in report.field_labels.items()
    ):
        raise CatalogConfigurationError(
            "E005", "Field labels must map registered paths to text."
        )
    if isinstance(report.model._meta.pk, models.CompositePrimaryKey):
        raise CatalogConfigurationError(
            "E003", "Composite primary keys are not supported."
        )
    fields = {}
    for path in report.fields:
        if not isinstance(path, str) or not path or path in fields:
            raise CatalogConfigurationError(
                "E002", "Field paths must be unique strings."
            )
        parts = path.split("__")
        if len(parts) > 2:
            raise CatalogConfigurationError(
                "E003", "Only one forward relation hop is supported."
            )
        relation_name = target_id = target_key = None
        try:
            field = report.model._meta.get_field(parts[0])
            if len(parts) == 2:
                if not isinstance(field, models.ForeignKey) or field.auto_created:
                    raise CatalogConfigurationError(
                        "E003", "Only forward FK/OneToOne relations are supported."
                    )
                target_id = field.related_model._meta.label_lower
                target = reports.get(target_id)
                if target is None or parts[1] not in target.fields:
                    raise CatalogConfigurationError(
                        "E004", f"Register target field {target_id}.{parts[1]}."
                    )
                relation_name = parts[0]
                target_key = field.target_field.name
                field = field.related_model._meta.get_field(parts[1])
        except FieldDoesNotExist as error:
            raise CatalogConfigurationError(
                "E002", f"Unknown field path: {path}."
            ) from error
        fields[path] = FieldSpec(
            path,
            report.field_labels.get(path, str(field.verbose_name)),
            field,
            field_operators(field),
            relation_name,
            target_id,
            target_key,
        )
    return ReportSpec(report.model._meta.label_lower, report, fields)


def get_catalog(request: HttpRequest) -> dict[str, ReportSpec]:
    user = request.user
    if not (user.is_authenticated and user.is_active and user.is_staff):
        return {}
    reports = {report.model._meta.label_lower: report for report in get_reports()}
    visible_ids = {
        key
        for key, report in reports.items()
        if user.has_perm(
            f"{report.model._meta.app_label}.view_{report.model._meta.model_name}"
        )
    }
    catalog = {}
    for key in visible_ids:
        spec = describe_report(reports[key], reports)
        fields = {
            path: replace(
                field,
                choices=field_choices(field.django_field),
                choices_declared=field.django_field.choices is not None,
            )
            for path, field in spec.fields.items()
            if field.target_report_id is None or field.target_report_id in visible_ids
        }
        catalog[key] = ReportSpec(key, spec.report, fields)
    return catalog
