from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from functools import cmp_to_key
from math import ceil

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext as _

from django_qbe2.catalog import ReportSpec
from django_qbe2.definitions import Scalar, SummaryDefinition
from django_qbe2.execution import ResultPage
from django_qbe2.limits import get_limits
from django_qbe2.output import OutputColumn, summary_columns


@dataclass(frozen=True)
class SummaryResult:
    rows: list[dict[str, Scalar]]
    columns: tuple[OutputColumn, ...]
    source_count: int


def _precision(field: models.Field, source_limit: int, *, output_scale: int = 0) -> int:
    if isinstance(field, models.DecimalField):
        decimal_places = field.decimal_places
        integer_digits = field.max_digits - decimal_places
    else:
        decimal_places = 0
        integer_digits = 20
    division_guard = len(str(max(1, source_limit)))
    return max(
        28,
        integer_digits + max(decimal_places, output_scale) + division_guard + 4,
    )


def _typed_group(values: tuple[Scalar, ...]) -> tuple[tuple[type, Scalar], ...]:
    return tuple((type(value), value) for value in values)


def _validated_numeric(value: Scalar, field: models.Field) -> int | Decimal:
    if isinstance(field, models.DecimalField):
        if not isinstance(value, Decimal) or not value.is_finite():
            raise ValidationError(_("Summary numeric values must be finite."))
        return value
    if type(value) is not int:
        raise ValidationError(_("Summary numeric values must be finite integers."))
    return value


def accumulate_summary(
    records: Iterable[dict[str, Scalar]],
    definition: SummaryDefinition,
    report: ReportSpec,
    *,
    source_count: int,
    source_limit: int,
) -> SummaryResult:
    if source_count > source_limit:
        raise ValidationError(
            _("Too many source records. Refine the report conditions and try again.")
        )
    groups = {}
    if not definition.group_by:
        groups[_typed_group(())] = ((), {})
    for record in records:
        group_values = []
        for path in definition.group_by:
            value = record[path]
            field = report.fields[path].django_field
            if isinstance(field, (models.IntegerField, models.DecimalField)):
                if value is not None:
                    _validated_numeric(value, field)
            group_values.append(value)
        group_values = tuple(group_values)
        key = _typed_group(group_values)
        _values, states = groups.setdefault(key, (group_values, {}))
        for metric in definition.metrics:
            state = states.setdefault(metric.id, {"sum": None, "count": 0})
            if metric.function == "count":
                state["count"] += 1
                continue
            value = record[metric.field]
            if value is None:
                continue
            field = report.fields[metric.field].django_field
            numeric = _validated_numeric(value, field)
            if isinstance(field, models.DecimalField):
                with localcontext() as context:
                    context.prec = _precision(field, source_limit)
                    state["sum"] = (state["sum"] or Decimal(0)) + numeric
            else:
                state["sum"] = (state["sum"] or 0) + numeric
            state["count"] += 1
    rows = []
    for group_values, states in groups.values():
        row = {
            f"group:{path}": value
            for path, value in zip(definition.group_by, group_values, strict=True)
        }
        for metric in definition.metrics:
            state = states.get(metric.id, {"sum": None, "count": 0})
            key = f"metric:{metric.id}"
            if metric.function == "count":
                row[key] = state["count"]
            elif metric.function == "sum" or not state["count"]:
                row[key] = state["sum"]
            else:
                field = report.fields[metric.field].django_field
                scale = (
                    max(6, field.decimal_places + 4)
                    if isinstance(field, models.DecimalField)
                    else 6
                )
                quantum = Decimal(1).scaleb(-scale)
                with localcontext() as context:
                    context.prec = _precision(field, source_limit, output_scale=scale)
                    row[key] = (
                        Decimal(state["sum"]) / Decimal(state["count"])
                    ).quantize(quantum, rounding=ROUND_HALF_EVEN)
        rows.append(row)
    return SummaryResult(rows, summary_columns(definition, report), source_count)


def _compare_values(left: Scalar, right: Scalar, direction: str) -> int:
    if left is None or right is None:
        compared = 0 if left is right else -1 if left is None else 1
    elif left < right:
        compared = -1
    elif left > right:
        compared = 1
    else:
        compared = 0
    return -compared if direction == "desc" else compared


def paginate_summary(
    result: SummaryResult,
    definition: SummaryDefinition,
    *,
    page: int,
    page_size: int,
    max_rows: int,
) -> ResultPage:
    limits = get_limits()
    if type(page) is not int or page < 1:
        raise ValidationError({"page": _("Choose a positive page number.")})
    if type(page_size) is not int or not 1 <= page_size <= limits.max_page_size:
        raise ValidationError(
            {
                "page_size": _("Choose 1–%(maximum)s rows per page.")
                % {"maximum": limits.max_page_size}
            }
        )
    ordering = []
    ordered_groups = set()
    for item in definition.ordering:
        if item.type == "group":
            ordering.append((f"group:{item.field}", item.direction))
            ordered_groups.add(item.field)
        else:
            ordering.append((f"metric:{item.id}", item.direction))
    ordering.extend(
        (f"group:{path}", "asc")
        for path in definition.group_by
        if path not in ordered_groups
    )

    def compare(left, right):
        for key, direction in ordering:
            compared = _compare_values(left[key], right[key], direction)
            if compared:
                return compared
        return 0

    rows = sorted(result.rows, key=cmp_to_key(compare))
    total = min(len(rows), max_rows)
    truncated = len(rows) > max_rows
    num_pages = max(1, ceil(total / page_size))
    if page > num_pages:
        raise ValidationError({"page": _("This page does not exist.")})
    start = (page - 1) * page_size
    return ResultPage(
        rows[start : min(start + page_size, total)],
        tuple(column.label for column in result.columns),
        page,
        page_size,
        total,
        num_pages,
        truncated,
    )
