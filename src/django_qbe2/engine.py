"""Compile validated definitions using the Django ORM and explicit row policies."""

from django.core.exceptions import ValidationError
from django.db.models import Q, QuerySet, Subquery
from django.http import HttpRequest
from django.utils.translation import gettext as _

from django_qbe2.catalog import ReportSpec
from django_qbe2.conditions import iter_filters
from django_qbe2.definitions import (
    ConditionGroup,
    FilterSpec,
    QueryDefinition,
    SummaryDefinition,
)
from django_qbe2.relations import (
    apply_single_relation_scopes,
    related_exists,
    validate_scope,
)


def compile_condition(
    node: FilterSpec | ConditionGroup,
    report_id: str,
    catalog: dict[str, ReportSpec],
    request: HttpRequest,
) -> Q:
    if isinstance(node, FilterSpec):
        field = catalog[report_id].fields[node.field]
        if field.multi_valued:
            return Q(
                related_exists(
                    field,
                    node.operator,
                    node.value,
                    catalog,
                    request,
                )
            )
        return Q(**{f"{node.field}__{node.operator}": node.value})
    predicate = Q()
    for child in node.children:
        compiled = compile_condition(child, report_id, catalog, request)
        predicate = (
            predicate & compiled if node.connector == "and" else predicate | compiled
        )
    return ~predicate if node.negated else predicate


def build_scoped_queryset(
    definition: QueryDefinition | SummaryDefinition,
    catalog: dict[str, ReportSpec],
    request: HttpRequest,
) -> QuerySet:
    report = catalog[definition.report].report
    queryset = validate_scope(report.get_queryset(request), report.model)
    if isinstance(definition, SummaryDefinition):
        filters = tuple(iter_filters(definition.where))
        summary_fields = set(definition.group_by)
        summary_fields.update(
            metric.field for metric in definition.metrics if metric.field is not None
        )
        if any(
            catalog[definition.report].fields[path].multi_valued
            for path in summary_fields
        ):
            raise ValidationError(
                _("Multi-valued relation fields cannot be grouped or summarized.")
            )
        used_fields = set(definition.group_by)
        used_fields.update(item.field for item in filters)
        used_fields.update(
            item.field for item in definition.metrics if item.field is not None
        )
    else:
        filters = definition.filters
        used_fields = set(definition.columns)
        used_fields.update(item.field for item in filters)
        used_fields.update(item.field for item in definition.ordering)
    scoped_relations = set()
    has_multi_valued_path = False
    for path in used_fields:
        field = catalog[definition.report].fields[path]
        if not field.relations:
            continue
        if field.multi_valued:
            has_multi_valued_path = True
            continue
        relation_key = tuple(step.accessor for step in field.relations)
        if relation_key in scoped_relations:
            continue
        queryset = apply_single_relation_scopes(queryset, field, catalog, request)
        scoped_relations.add(relation_key)
    predicates = Q()
    if definition.where is not None:
        predicates = compile_condition(
            definition.where, definition.report, catalog, request
        )
    else:
        for condition in filters:
            predicates &= compile_condition(
                condition, definition.report, catalog, request
            )
    queryset = queryset.filter(predicates)
    return queryset.distinct() if has_multi_valued_path else queryset


def build_queryset(
    definition: QueryDefinition,
    catalog: dict[str, ReportSpec],
    request: HttpRequest,
) -> QuerySet:
    report = catalog[definition.report].report
    if any(
        catalog[definition.report].fields[item.field].multi_valued
        for item in definition.ordering
    ):
        raise ValidationError(_("Multi-valued relation fields cannot be ordered."))
    queryset = build_scoped_queryset(definition, catalog, request)
    ordering = [
        f"{'-' if item.direction == 'desc' else ''}{item.field}"
        for item in definition.ordering
    ]
    if report.model._meta.pk.name not in {item.field for item in definition.ordering}:
        ordering.append("pk")
    return queryset.order_by(*ordering)


def build_summary_source(
    definition: SummaryDefinition,
    catalog: dict[str, ReportSpec],
    request: HttpRequest,
) -> QuerySet:
    report = catalog[definition.report].report
    scoped = build_scoped_queryset(definition, catalog, request)
    base = validate_scope(report.model._base_manager.all(), report.model)
    return base.filter(pk__in=Subquery(scoped.values("pk"))).order_by("pk")
