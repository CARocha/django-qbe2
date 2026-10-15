"""Build ORM predicates that preserve related-report row policies."""

from django.core.exceptions import ImproperlyConfigured
from django.db import models
from django.db.models import Exists, OuterRef, Q, QuerySet, Subquery
from django.http import HttpRequest

from django_qbe2.catalog import FieldSpec, RelationStep, ReportSpec


def validate_scope(queryset: QuerySet, model: type[models.Model]) -> QuerySet:
    if not isinstance(queryset, QuerySet) or queryset.model is not model:
        raise ImproperlyConfigured("Report policy must return its model's QuerySet.")
    if queryset.db != "default":
        raise ImproperlyConfigured("Only the default database is supported.")
    try:
        queryset.filter(pk__isnull=False)
        queryset.contains(model(pk=None))
    except TypeError as error:
        raise ImproperlyConfigured(
            "Report policies cannot return slices or values()."
        ) from error
    except ValueError:
        # contains() rejects an unsaved instance before accessing the database.
        pass
    return queryset


def _reverse_query_name(step: RelationStep) -> str:
    if step.reverse:
        return step.relation_field.name
    return step.relation_field.related_query_name()


def _path_to_source(steps: tuple[RelationStep, ...]) -> str:
    return "__".join(_reverse_query_name(step) for step in reversed(steps))


def related_queryset(
    field: FieldSpec,
    catalog: dict[str, ReportSpec],
    request: HttpRequest,
) -> QuerySet:
    """Return terminal rows scoped through every model on a declared path."""
    steps = field.relations
    if not steps:
        raise ImproperlyConfigured("A related queryset needs a relation path.")

    terminal_step = steps[-1]
    terminal_report = catalog[terminal_step.target_report_id].report
    queryset = validate_scope(
        terminal_report.get_queryset(request), terminal_step.target_model
    )

    for index in range(len(steps) - 2, -1, -1):
        step = steps[index]
        intermediate_report = catalog[step.target_report_id].report
        intermediate_scope = validate_scope(
            intermediate_report.get_queryset(request), step.target_model
        )
        path_to_intermediate = _path_to_source(steps[index + 1 :])
        queryset = queryset.filter(
            **{
                f"{path_to_intermediate}__pk__in": Subquery(
                    intermediate_scope.order_by().values("pk")
                )
            }
        )

    path_to_root = _path_to_source(steps)
    return queryset.order_by().filter(**{f"{path_to_root}__pk": OuterRef("pk")})


def apply_single_relation_scopes(
    queryset: QuerySet,
    field: FieldSpec,
    catalog: dict[str, ReportSpec],
    request: HttpRequest,
) -> QuerySet:
    """Keep roots whose to-one path is empty or points into every target scope."""
    path_parts = []
    for step in field.relations:
        path_parts.append(step.accessor)
        report = catalog[step.target_report_id].report
        scope = validate_scope(report.get_queryset(request), step.target_model)
        path = "__".join(path_parts)
        queryset = queryset.filter(
            Q(**{f"{path}__isnull": True})
            | Q(**{f"{path}__pk__in": Subquery(scope.order_by().values("pk"))})
        )
    return queryset


def related_exists(
    field: FieldSpec,
    lookup: str,
    value: object,
    catalog: dict[str, ReportSpec],
    request: HttpRequest,
) -> Exists:
    queryset = related_queryset(field, catalog, request)
    terminal_name = field.path.rsplit("__", 1)[-1]
    return Exists(queryset.filter(**{f"{terminal_name}__{lookup}": value}))
