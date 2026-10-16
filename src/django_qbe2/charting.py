"""Build bounded chart data from an already authorized summary page."""

from dataclasses import dataclass
from decimal import Decimal, localcontext

from django.utils.translation import gettext as _

from django_qbe2.aggregation import SummaryResult
from django_qbe2.definitions import SummaryDefinition
from django_qbe2.execution import ResultPage


@dataclass(frozen=True)
class Bar:
    label: str
    value: int | Decimal
    x: Decimal
    y: Decimal
    width: Decimal


@dataclass(frozen=True)
class BarChart:
    title: str
    description: str
    group_label: str
    metric_label: str
    metric_id: str
    width: int
    height: int
    baseline: Decimal
    bars: tuple[Bar, ...]


def _choice_label(value, choices):
    for choice_value, label in choices:
        if type(value) is type(choice_value) and value == choice_value:
            return str(label)
    return str(value) if value is not None else "—"


def build_bar_chart(
    definition: SummaryDefinition,
    result: SummaryResult,
    page: ResultPage,
    metric_id: str | None = None,
) -> BarChart | None:
    """Return a one-dimensional horizontal bar chart for the current page."""
    if len(definition.group_by) != 1 or not page.rows:
        return None

    selected_metric = next(
        (metric for metric in definition.metrics if metric.id == metric_id), None
    )
    if selected_metric is None:
        selected_metric = definition.metrics[0]

    group_key = f"group:{definition.group_by[0]}"
    metric_key = f"metric:{selected_metric.id}"
    group_column = next(
        (column for column in result.columns if column.key == group_key), None
    )
    metric_column = next(
        (column for column in result.columns if column.key == metric_key), None
    )
    if group_column is None or metric_column is None:
        return None

    values = [row.get(metric_key) for row in page.rows]
    if any(
        (type(value) is not int and not isinstance(value, Decimal))
        or isinstance(value, Decimal)
        and not value.is_finite()
        for value in values
    ):
        return None

    decimals = [Decimal(value) for value in values]
    maximum = max((abs(value) for value in decimals), default=Decimal(0))
    width = 720
    plot_left = Decimal(180)
    plot_width = Decimal(520)
    has_negative = any(value < 0 for value in decimals)
    has_positive = any(value > 0 for value in decimals)
    if has_negative and has_positive:
        baseline = plot_left + plot_width / 2
        maximum_width = plot_width / 2
    elif has_negative:
        baseline = plot_left + plot_width
        maximum_width = plot_width
    else:
        baseline = plot_left
        maximum_width = plot_width

    precision = max(28, *(len(value.as_tuple().digits) for value in decimals)) + 12
    bars = []
    with localcontext() as context:
        context.prec = precision
        for index, (row, value) in enumerate(zip(page.rows, decimals, strict=True)):
            bar_width = maximum_width * abs(value) / maximum if maximum else Decimal(0)
            label = _choice_label(row.get(group_key), group_column.choices)
            bars.append(
                Bar(
                    label=label,
                    value=values[index],
                    x=baseline - bar_width if value < 0 else baseline,
                    y=Decimal(40 + index * 44),
                    width=bar_width,
                )
            )

    return BarChart(
        title=str(_("Summary bar chart")),
        description=str(
            _("%(metric)s by %(group)s for %(count)s categories on the current page.")
            % {
                "metric": metric_column.label,
                "group": group_column.label,
                "count": len(bars),
            }
        ),
        group_label=group_column.label,
        metric_label=metric_column.label,
        metric_id=selected_metric.id,
        width=width,
        height=80 + len(bars) * 44,
        baseline=baseline,
        bars=tuple(bars),
    )
