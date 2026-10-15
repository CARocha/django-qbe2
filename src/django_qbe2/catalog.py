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
class RelationStep:
    source_model: type[models.Model]
    accessor: str
    target_model: type[models.Model]
    target_report_id: str
    relation_field: models.Field
    target_key: str
    reverse: bool
    multi_valued: bool


@dataclass(frozen=True)
class FieldSpec:
    path: str
    label: str
    django_field: models.Field
    operators: tuple[str, ...]
    relations: tuple[RelationStep, ...] = ()
    choices: tuple[tuple[Scalar, str], ...] = ()
    choices_declared: bool = False

    @property
    def multi_valued(self) -> bool:
        return any(step.multi_valued for step in self.relations)

    @property
    def relation_name(self) -> str | None:
        return self.relations[0].accessor if self.relations else None

    @property
    def target_report_id(self) -> str | None:
        return self.relations[0].target_report_id if self.relations else None

    @property
    def target_key(self) -> str | None:
        return self.relations[0].target_key if self.relations else None


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


def _relation_step(
    source_model: type[models.Model], field: models.Field
) -> RelationStep:
    reverse = field.auto_created and not field.concrete
    relation_field = field.field if reverse else field
    target_model = field.related_model
    if not isinstance(
        relation_field,
        (models.ForeignKey, models.OneToOneField, models.ManyToManyField),
    ):
        raise CatalogConfigurationError("E003", "Unsupported relation path.")
    accessor = field.name
    if relation_field.many_to_many:
        if reverse:
            target_key = relation_field.m2m_field_name()
        else:
            target_key = relation_field.m2m_reverse_field_name()
        target_key = relation_field.remote_field.through._meta.get_field(
            target_key
        ).target_field.name
    elif reverse:
        target_key = relation_field.name
    else:
        target_key = relation_field.target_field.name
    return RelationStep(
        source_model=source_model,
        accessor=accessor,
        target_model=target_model,
        target_report_id=target_model._meta.label_lower,
        relation_field=relation_field,
        target_key=target_key,
        reverse=reverse,
        multi_valued=field.one_to_many or field.many_to_many,
    )


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
        if len(parts) > 3:
            raise CatalogConfigurationError(
                "E003", "At most two relation hops are supported."
            )
        relations = []
        current_model = report.model
        multi_valued_count = 0
        try:
            for name in parts[:-1]:
                relation = current_model._meta.get_field(name)
                if not relation.is_relation:
                    raise CatalogConfigurationError(
                        "E003", "Each intermediate path component must be a relation."
                    )
                step = _relation_step(current_model, relation)
                target = reports.get(step.target_report_id)
                if target is None:
                    raise CatalogConfigurationError(
                        "E004", f"Register a report for {step.target_report_id}."
                    )
                relations.append(step)
                multi_valued_count += step.multi_valued
                if multi_valued_count > 1:
                    raise CatalogConfigurationError(
                        "E003",
                        "A field path may contain only one multi-valued relation.",
                    )
                current_model = step.target_model
            if relations:
                target = reports[relations[-1].target_report_id]
                if parts[-1] not in target.fields:
                    raise CatalogConfigurationError(
                        "E004",
                        "Register target field "
                        f"{relations[-1].target_report_id}.{parts[-1]}.",
                    )
            field = current_model._meta.get_field(parts[-1])
        except FieldDoesNotExist as error:
            raise CatalogConfigurationError(
                "E002", f"Unknown field path: {path}."
            ) from error
        fields[path] = FieldSpec(
            path,
            report.field_labels.get(path, str(field.verbose_name)),
            field,
            field_operators(field),
            tuple(relations),
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
            if all(step.target_report_id in visible_ids for step in field.relations)
        }
        catalog[key] = ReportSpec(key, spec.report, fields)
    return catalog
