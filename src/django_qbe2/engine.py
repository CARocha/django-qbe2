"""Compile validated definitions using the Django ORM and explicit row policies."""

from django.core.exceptions import ImproperlyConfigured
from django.db.models import Model, Q, QuerySet
from django.http import HttpRequest

from django_qbe2.catalog import ReportSpec
from django_qbe2.definitions import ConditionGroup, FilterSpec, QueryDefinition


def validate_scope(queryset: QuerySet, model: type[Model]) -> QuerySet:
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


def compile_condition(node: FilterSpec | ConditionGroup) -> Q:
    if isinstance(node, FilterSpec):
        return Q(**{f"{node.field}__{node.operator}": node.value})
    predicate = Q()
    for child in node.children:
        compiled = compile_condition(child)
        predicate = (
            predicate & compiled if node.connector == "and" else predicate | compiled
        )
    return ~predicate if node.negated else predicate


def build_queryset(
    definition: QueryDefinition,
    catalog: dict[str, ReportSpec],
    request: HttpRequest,
) -> QuerySet:
    report = catalog[definition.report].report
    queryset = validate_scope(report.get_queryset(request), report.model)
    used_fields = set(definition.columns)
    used_fields.update(item.field for item in definition.filters)
    used_fields.update(item.field for item in definition.ordering)
    scoped_relations = set()
    for path in used_fields:
        field = catalog[definition.report].fields[path]
        if field.relation_name is None or field.relation_name in scoped_relations:
            continue
        target_report = catalog[field.target_report_id].report
        target_scope = validate_scope(
            target_report.get_queryset(request),
            target_report.model,
        )
        lookup = f"{field.relation_name}__{field.target_key}__in"
        queryset = queryset.filter(
            Q(**{f"{field.relation_name}__isnull": True})
            | Q(**{lookup: target_scope.values(field.target_key)})
        )
        scoped_relations.add(field.relation_name)
    predicates = Q()
    if definition.where is not None:
        predicates = compile_condition(definition.where)
    else:
        for condition in definition.filters:
            predicates &= compile_condition(condition)
    ordering = [
        f"{'-' if item.direction == 'desc' else ''}{item.field}"
        for item in definition.ordering
    ]
    if report.model._meta.pk.name not in {item.field for item in definition.ordering}:
        ordering.append("pk")
    return queryset.filter(predicates).order_by(*ordering)
