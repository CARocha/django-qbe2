from dataclasses import dataclass

from django.db import models
from django.utils.translation import gettext as _

from django_qbe2.catalog import ReportSpec
from django_qbe2.definitions import Scalar, SummaryDefinition


@dataclass(frozen=True)
class OutputColumn:
    key: str
    label: str
    numeric: bool
    choices: tuple[tuple[Scalar, str], ...] = ()


def summary_columns(
    definition: SummaryDefinition, report: ReportSpec
) -> tuple[OutputColumn, ...]:
    columns = []
    for path in definition.group_by:
        spec = report.fields[path]
        columns.append(
            OutputColumn(
                f"group:{path}",
                spec.label,
                isinstance(
                    spec.django_field, (models.IntegerField, models.DecimalField)
                )
                and not isinstance(spec.django_field, models.BooleanField),
                spec.choices,
            )
        )
    for metric in definition.metrics:
        if metric.function == "count":
            label = _("Count records")
        else:
            field_label = report.fields[metric.field].label
            label = (
                _("Sum of %(field)s")
                if metric.function == "sum"
                else _("Average of %(field)s")
            ) % {"field": field_label}
        columns.append(OutputColumn(f"metric:{metric.id}", str(label), True))
    return tuple(columns)
