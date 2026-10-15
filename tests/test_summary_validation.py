from decimal import Decimal

from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.test import RequestFactory, TestCase, override_settings

from tests.fixtures import grant_view, make_staff
from tests.models import Customer, Order


def summary_payload(**changes):
    payload = {
        "version": 3,
        "report": "tests.order",
        "where": {"connector": "and", "negated": False, "children": []},
        "group_by": [],
        "metrics": [{"id": "m1", "function": "count", "field": None}],
        "ordering": [],
    }
    payload.update(changes)
    return payload


class SummaryValidationTests(TestCase):
    def setUp(self):
        from django_qbe2.catalog import get_catalog

        user = make_staff("summary-validator")
        grant_view(user, Order, Customer)
        request = RequestFactory().get("/")
        request.user = user
        self.catalog = get_catalog(request)

    def test_ungrouped_count_definition(self):
        from django_qbe2.definitions import MetricSpec, SummaryDefinition
        from django_qbe2.validation import validate_definition

        definition = validate_definition(summary_payload(), self.catalog)

        self.assertIsInstance(definition, SummaryDefinition)
        self.assertEqual(definition.metrics, (MetricSpec("m1", "count", None),))
        self.assertEqual(definition.group_by, ())
        self.assertEqual(definition.where.children, ())

    def test_grouped_metrics_and_ordering_definition(self):
        from django_qbe2.definitions import (
            FilterSpec,
            MetricSpec,
            SummaryOrderingSpec,
        )
        from django_qbe2.validation import validate_definition

        payload = summary_payload(
            where={
                "connector": "and",
                "negated": False,
                "children": [
                    {"field": "total", "operator": "gte", "value": "10.25"}
                ],
            },
            group_by=["active", "customer__name"],
            metrics=[
                {"id": "m1", "function": "count", "field": None},
                {"id": "m2", "function": "sum", "field": "quantity"},
                {"id": "m3", "function": "avg", "field": "total"},
            ],
            ordering=[
                {"type": "metric", "id": "m2", "direction": "desc"},
                {"type": "group", "field": "active", "direction": "asc"},
            ],
        )

        definition = validate_definition(payload, self.catalog)

        self.assertEqual(
            definition.where.children,
            (FilterSpec("total", "gte", Decimal("10.25")),),
        )
        self.assertEqual(definition.group_by, ("active", "customer__name"))
        self.assertEqual(
            definition.metrics,
            (
                MetricSpec("m1", "count", None),
                MetricSpec("m2", "sum", "quantity"),
                MetricSpec("m3", "avg", "total"),
            ),
        )
        self.assertEqual(
            definition.ordering,
            (
                SummaryOrderingSpec("metric", "desc", id="m2"),
                SummaryOrderingSpec("group", "asc", field="active"),
            ),
        )

    def assert_invalid(self, payload, control):
        from django_qbe2.validation import validate_definition

        with self.assertRaises(ValidationError) as captured:
            validate_definition(payload, self.catalog)
        self.assertIn(control, captured.exception.message_dict)

    def test_definition_shape_is_strict(self):
        for payload in (
            summary_payload(extra=True),
            {key: value for key, value in summary_payload().items() if key != "where"},
            summary_payload(version=True),
            summary_payload(version=4),
        ):
            with self.subTest(payload=payload):
                self.assert_invalid(payload, "definition")

    def test_metrics_reject_invalid_shapes_fields_and_duplicates(self):
        cases = (
            [],
            [None],
            [{"id": "m0", "function": "count", "field": None}],
            [{"id": "m0001", "function": "count", "field": None}],
            [{"id": "m1234567890", "function": "count", "field": None}],
            [{"id": "m1", "function": "median", "field": "total"}],
            [{"id": "m1", "function": "count", "field": "total"}],
            [{"id": "m1", "function": "sum", "field": None}],
            [{"id": "m1", "function": "sum", "field": "number"}],
            [{"id": "m1", "function": "sum", "field": "active"}],
            [{"id": "m1", "function": "sum", "field": "owner__password"}],
            [
                {"id": "m1", "function": "count", "field": None},
                {"id": "m1", "function": "sum", "field": "total"},
            ],
            [
                {"id": "m1", "function": "sum", "field": "total"},
                {"id": "m2", "function": "sum", "field": "total"},
            ],
            [{"id": "m1", "function": "count", "field": None, "extra": True}],
        )
        for metrics in cases:
            with self.subTest(metrics=metrics):
                self.assert_invalid(summary_payload(metrics=metrics), "metrics")

    def test_grouping_and_ordering_require_selected_distinct_targets(self):
        for group_by in (
            ["number", "number"],
            ["owner__password"],
            [1],
        ):
            with self.subTest(group_by=group_by):
                self.assert_invalid(summary_payload(group_by=group_by), "group_by")
        payload = summary_payload(group_by=["active"])
        for ordering in (
            [None],
            [{"type": "other", "id": "m1", "direction": "asc"}],
            [{"type": "metric", "field": "active", "direction": "asc"}],
            [{"type": "metric", "id": "m2", "direction": "asc"}],
            [{"type": "metric", "id": ["m1"], "direction": "asc"}],
            [{"type": "group", "field": "number", "direction": "asc"}],
            [{"type": "group", "field": ["active"], "direction": "asc"}],
            [{"type": "group", "field": "active", "direction": "sideways"}],
            [
                {"type": "metric", "id": "m1", "direction": "asc"},
                {"type": "metric", "id": "m1", "direction": "desc"},
            ],
            [{"type": "metric", "id": "m1", "direction": "asc", "extra": 1}],
        ):
            with self.subTest(ordering=ordering):
                self.assert_invalid({**payload, "ordering": ordering}, "ordering")

    def test_condition_tree_is_validated_with_existing_limits(self):
        self.assert_invalid(
            summary_payload(
                where={"connector": "or", "negated": False, "children": []}
            ),
            "filters",
        )
        with override_settings(QBE2_MAX_FILTERS=1):
            self.assert_invalid(
                summary_payload(
                    where={
                        "connector": "and",
                        "negated": False,
                        "children": [
                            {"field": "quantity", "operator": "gte", "value": 1},
                            {"field": "quantity", "operator": "lte", "value": 2},
                        ],
                    }
                ),
                "filters",
            )

    def test_summary_limits_accept_boundaries_and_reject_excess(self):
        metrics = [
            {"id": "m1", "function": "count", "field": None},
            {"id": "m2", "function": "sum", "field": "total"},
        ]
        with override_settings(
            QBE2_MAX_GROUP_BY=1,
            QBE2_MAX_METRICS=2,
            QBE2_MAX_ORDERING=1,
            QBE2_MAX_AGGREGATE_ROWS=1,
        ):
            from django_qbe2.limits import get_limits
            from django_qbe2.validation import validate_definition

            definition = validate_definition(
                summary_payload(group_by=["active"], metrics=metrics), self.catalog
            )
            self.assertEqual(len(definition.group_by), 1)
            self.assertEqual(len(definition.metrics), 2)
            self.assertEqual(get_limits().max_aggregate_rows, 1)
            self.assert_invalid(
                summary_payload(group_by=["active", "number"]), "group_by"
            )
            self.assert_invalid(
                summary_payload(
                    metrics=metrics
                    + [{"id": "m3", "function": "avg", "field": "total"}]
                ),
                "metrics",
            )

    def test_summary_limits_reject_non_positive_and_boolean_values(self):
        from django_qbe2.limits import get_limits

        for setting in (
            "QBE2_MAX_AGGREGATE_ROWS",
            "QBE2_MAX_GROUP_BY",
            "QBE2_MAX_METRICS",
        ):
            for value in (0, -1, True):
                with (
                    self.subTest(setting=setting, value=value),
                    override_settings(**{setting: value}),
                    self.assertRaises(ImproperlyConfigured),
                ):
                    get_limits()
