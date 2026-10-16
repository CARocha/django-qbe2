from dataclasses import FrozenInstanceError
from decimal import Decimal

from django.test import SimpleTestCase

from django_qbe2.aggregation import SummaryResult
from django_qbe2.definitions import ConditionGroup, MetricSpec, SummaryDefinition
from django_qbe2.execution import ResultPage
from django_qbe2.output import OutputColumn


class SummaryBarChartTests(SimpleTestCase):
    def build(
        self, values, *, group_by=("status",), metrics=None, metric_id=None, choices=()
    ):
        from django_qbe2.charting import build_bar_chart

        metrics = metrics or (MetricSpec("m1", "count", None),)
        definition = SummaryDefinition(
            version=3,
            report="tests.order",
            where=ConditionGroup("and", False, ()),
            group_by=group_by,
            metrics=metrics,
            ordering=(),
        )
        columns = tuple(
            OutputColumn(f"group:{path}", "Status", False, choices) for path in group_by
        ) + tuple(
            OutputColumn(
                f"metric:{metric.id}", f"{metric.function.title()} value", True
            )
            for metric in metrics
        )
        result = SummaryResult([], columns, len(values))
        rows = [
            {"group:status": label, **metric_values} for label, metric_values in values
        ]
        page = ResultPage(
            rows=rows,
            labels=tuple(column.label for column in columns),
            page=1,
            page_size=50,
            total_limited=len(rows),
            num_pages=1,
            truncated=False,
        )
        return build_bar_chart(definition, result, page, metric_id)

    def test_count_sum_and_average_metrics_can_be_selected(self):
        metrics = (
            MetricSpec("m1", "count", None),
            MetricSpec("m2", "sum", "total"),
            MetricSpec("m3", "avg", "total"),
        )
        rows = [
            (
                "active",
                {
                    "metric:m1": 3,
                    "metric:m2": Decimal("12.50"),
                    "metric:m3": Decimal("4.166667"),
                },
            )
        ]

        default = self.build(rows, metrics=metrics)
        selected = self.build(rows, metrics=metrics, metric_id="m3")

        self.assertEqual(default.metric_id, "m1")
        self.assertEqual(default.bars[0].value, 3)
        self.assertIn("1 category on the current page", default.description)
        self.assertEqual(selected.metric_id, "m3")
        self.assertEqual(selected.bars[0].value, Decimal("4.166667"))

    def test_invalid_metric_falls_back_to_the_first_valid_metric(self):
        metrics = (MetricSpec("m1", "count", None), MetricSpec("m2", "sum", "total"))

        chart = self.build(
            [("active", {"metric:m1": 3, "metric:m2": Decimal("12.50")})],
            metrics=metrics,
            metric_id="forged__field",
        )

        self.assertEqual(chart.metric_id, "m1")

    def test_empty_ungrouped_and_multi_group_pages_have_no_chart(self):
        self.assertIsNone(self.build([]))
        self.assertIsNone(self.build([("active", {"metric:m1": 1})], group_by=()))
        self.assertIsNone(
            self.build(
                [("active", {"metric:m1": 1})],
                group_by=("status", "active"),
            )
        )

    def test_null_choice_and_long_category_labels_are_readable(self):
        label = "a long category label " * 20
        chart = self.build(
            [
                (None, {"metric:m1": 0}),
                ("A", {"metric:m1": 1}),
                (label, {"metric:m1": 2}),
            ],
            choices=(("A", "Active"),),
        )

        self.assertEqual([bar.label for bar in chart.bars], ["—", "Active", label])

    def test_zero_negative_and_large_values_use_bounded_coordinates(self):
        chart = self.build(
            [
                ("zero", {"metric:m1": 0}),
                ("negative", {"metric:m1": -(10**100)}),
                ("positive", {"metric:m1": 10**100}),
            ]
        )

        self.assertEqual(chart.baseline, Decimal("300"))
        self.assertEqual(chart.bars[0].width, Decimal(0))
        self.assertLess(chart.bars[1].x, chart.baseline)
        self.assertEqual(chart.bars[2].x, chart.baseline)
        self.assertGreater(chart.bars[2].x + chart.bars[2].width, chart.baseline)
        for bar in chart.bars:
            self.assertGreaterEqual(bar.x, 40)
            self.assertLessEqual(bar.x + bar.width, chart.width - 20)

    def test_negative_only_chart_keeps_zero_axis_in_the_plot_middle(self):
        chart = self.build([("negative", {"metric:m1": Decimal("-10.25")})])

        self.assertEqual(chart.baseline, Decimal("300"))
        self.assertEqual(chart.bars[0].x, Decimal("100"))
        self.assertEqual(chart.bars[0].width, Decimal("200"))
        self.assertEqual([tick.label for tick in chart.ticks], ["-10.25", "0"])

    def test_high_precision_decimal_values_remain_exact(self):
        exact = Decimal("123456789012345678901234567890.12345678901234567890")
        chart = self.build([("precise", {"metric:m1": exact})])

        self.assertEqual(chart.bars[0].value, exact)
        self.assertIsInstance(chart.bars[0].width, Decimal)
        self.assertEqual(chart.bars[0].width, Decimal("400"))

    def test_zero_only_values_produce_zero_width_bars_without_division(self):
        chart = self.build(
            [
                ("empty", {"metric:m1": 0}),
                ("also empty", {"metric:m1": Decimal("0.00")}),
            ]
        )

        self.assertEqual([bar.width for bar in chart.bars], [Decimal(0), Decimal(0)])
        self.assertEqual(chart.ticks[0].label, "0")

    def test_chart_and_bars_are_immutable(self):
        chart = self.build([("active", {"metric:m1": 3})])

        with self.assertRaises(FrozenInstanceError):
            chart.metric_id = "m2"
        with self.assertRaises(FrozenInstanceError):
            chart.bars[0].label = "changed"
