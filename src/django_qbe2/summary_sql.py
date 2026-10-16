from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal, localcontext

from django.core.exceptions import ValidationError
from django.db import connections, models
from django.db.models import Count, F, QuerySet, Sum, Value
from django.db.models.functions import Cast, Round
from django.utils.translation import gettext as _

from django_qbe2.aggregation import SummaryResult, _precision, _validated_numeric
from django_qbe2.catalog import ReportSpec
from django_qbe2.definitions import SummaryDefinition
from django_qbe2.output import summary_columns


def _average(total, count: int, field, source_limit: int):
    if count == 0 or total is None:
        return None
    scale = max(6, field.decimal_places + 4) if hasattr(field, "decimal_places") else 6
    with localcontext() as context:
        context.prec = _precision(field, source_limit, output_scale=scale)
        try:
            return (Decimal(total) / Decimal(count)).quantize(
                Decimal(1).scaleb(-scale), rounding=ROUND_HALF_EVEN
            )
        except (ArithmeticError, ValueError) as exc:
            raise ValidationError(_("Summary numeric values must be finite.")) from exc


def _uses_scaled_sqlite_decimal_sum(field, *, vendor: str, source_count: int) -> bool:
    if vendor != "sqlite" or not isinstance(field, models.DecimalField):
        return False
    if (
        field.max_digits <= 15
        and field.max_digits + len(str(max(1, source_count))) <= 18
    ):
        return True
    raise ValidationError(
        _(
            "SQLite cannot safely sum this Decimal field for the matching rows. "
            "Use PostgreSQL or a lower-precision Decimal field."
        )
    )


def execute_database_summary(
    queryset: QuerySet,
    definition: SummaryDefinition,
    report: ReportSpec,
    *,
    source_limit: int,
) -> SummaryResult:
    """Calculate complete summary totals in the database within the source cap."""
    source_count = queryset.order_by().values("pk")[: source_limit + 1].count()
    if source_count > source_limit:
        raise ValidationError(
            _("Too many source records. Refine the report conditions and try again.")
        )

    aggregates = {}
    metric_aliases = {}
    for index, metric in enumerate(definition.metrics):
        if metric.function == "count":
            alias = f"qbe2_metric_{index}_count"
            aggregates[alias] = Count("pk")
            metric_aliases[metric.id] = (metric.function, alias, None, False)
            continue

        total_alias = f"qbe2_metric_{index}_sum"
        field = report.fields[metric.field].django_field
        scaled_sqlite_sum = _uses_scaled_sqlite_decimal_sum(
            field, vendor=connections[queryset.db].vendor, source_count=source_count
        )
        if scaled_sqlite_sum:
            scale = 10**field.decimal_places
            scaled_value = Cast(
                Round(F(metric.field) * Value(scale)),
                output_field=models.BigIntegerField(),
            )
            aggregates[total_alias] = Sum(
                scaled_value, output_field=models.BigIntegerField()
            )
        else:
            aggregates[total_alias] = Sum(metric.field)
        if metric.function == "sum":
            metric_aliases[metric.id] = (
                metric.function,
                total_alias,
                None,
                scaled_sqlite_sum,
            )
        else:
            count_alias = f"qbe2_metric_{index}_nonnull_count"
            aggregates[count_alias] = Count(metric.field)
            metric_aliases[metric.id] = (
                metric.function,
                total_alias,
                count_alias,
                scaled_sqlite_sum,
            )

    source = queryset.order_by()
    if definition.group_by:
        calculated = source.values(*definition.group_by).annotate(**aggregates)
    else:
        calculated = (source.aggregate(**aggregates),)

    rows = []
    for values in calculated:
        row = {}
        for path in definition.group_by:
            value = values[path]
            field = report.fields[path].django_field
            if value is not None and isinstance(
                field, (models.IntegerField, models.DecimalField)
            ):
                _validated_numeric(value, field)
            row[f"group:{path}"] = value

        for metric in definition.metrics:
            function, total_alias, count_alias, scaled_sqlite_sum = metric_aliases[
                metric.id
            ]
            value = values[total_alias]
            if function == "count":
                row[f"metric:{metric.id}"] = value
            elif function == "sum":
                field = report.fields[metric.field].django_field
                if scaled_sqlite_sum and value is not None:
                    value = Decimal(value).scaleb(-field.decimal_places)
                if value is not None:
                    _validated_numeric(value, field)
                row[f"metric:{metric.id}"] = value
            else:
                field = report.fields[metric.field].django_field
                if scaled_sqlite_sum and value is not None:
                    value = Decimal(value).scaleb(-field.decimal_places)
                if value is not None:
                    _validated_numeric(value, field)
                row[f"metric:{metric.id}"] = _average(
                    value, values[count_alias], field, source_limit
                )
        rows.append(row)

    if not definition.group_by and not rows:
        rows.append(
            {
                f"metric:{metric.id}": 0 if metric.function == "count" else None
                for metric in definition.metrics
            }
        )
    return SummaryResult(rows, summary_columns(definition, report), source_count)
