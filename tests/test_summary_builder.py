from unittest.mock import patch

from django.test import TestCase, override_settings

from django_qbe2.forms import QueryBuilderForm, payload_form_data
from tests import test_engine
from tests.test_condition_validation import group, leaf
from tests.test_summary_validation import summary_payload


class SummaryBuilderFormTests(TestCase):
    setUp = test_engine.EngineTests.setUp

    def test_new_builder_defaults_to_rows_with_summary_count_available(self):
        form = QueryBuilderForm(catalog=self.catalog)
        self.assertEqual(form["mode"].value(), "rows")
        self.assertEqual(len(form.metrics.forms), 1)
        self.assertEqual(form.metrics.forms[0]["id"].value(), "m1")
        self.assertEqual(form.metrics.forms[0]["function"].value(), "count")

    def test_v3_controls_round_trip_exact_definition(self):
        payload = summary_payload(
            where=group(leaf("total", "10.50", "gte")),
            group_by=["active", "customer__name"],
            metrics=[
                {"id": "m2", "function": "sum", "field": "quantity"},
                {"id": "m7", "function": "avg", "field": "total"},
            ],
            ordering=[
                {"type": "metric", "id": "m7", "direction": "desc"},
                {"type": "group", "field": "active", "direction": "asc"},
            ],
        )
        form = QueryBuilderForm(
            payload_form_data(payload, page_size="25"), catalog=self.catalog
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.payload, payload)
        self.assertEqual(form.cleaned_data["page_size"], 25)
        self.assertEqual(
            [row["id"].value() for row in form.metrics.forms], ["m2", "m7"]
        )

    def test_metric_fields_offer_only_registered_numeric_paths(self):
        data = payload_form_data(summary_payload(), page_size="50")
        form = QueryBuilderForm(data, catalog=self.catalog)
        choices = dict(form.metrics.forms[0].fields["field"].choices)
        self.assertIn("quantity", choices)
        self.assertIn("total", choices)
        self.assertIn("customer__credit_limit", choices)
        self.assertNotIn("active", choices)
        self.assertNotIn("number", choices)
        self.assertNotIn("owner_id", choices)

    @override_settings(QBE2_MAX_GROUP_BY=3, QBE2_MAX_METRICS=10, QBE2_MAX_ORDERING=3)
    def test_summary_controls_expose_configured_structural_limits(self):
        metrics = [
            {"id": f"m{index}", "function": "sum", "field": "quantity"}
            if index == 1
            else {"id": f"m{index}", "function": "avg", "field": "quantity"}
            if index == 2
            else {"id": f"m{index}", "function": "count", "field": None}
            for index in range(1, 4)
        ]
        data = payload_form_data(summary_payload(metrics=metrics[:1]), page_size="50")
        form = QueryBuilderForm(data, catalog=self.catalog)
        self.assertEqual(form.fields["group_by"].widget.attrs["data-maximum"], 3)
        self.assertEqual(form.metrics.max_num, 10)
        self.assertEqual(form.summary_ordering.max_num, 3)


class SummaryBuilderActionTests(TestCase):
    setUp = test_engine.EngineTests.setUp

    def post(self, data):
        self.client.force_login(self.alice)
        return self.client.post("/qbe/results/", data)

    def test_apply_summary_preserves_conditions_and_resets_outputs(self):
        from tests.test_validation import order_payload

        data = payload_form_data(
            order_payload(
                columns=["number", "total"],
                filters=[
                    {"field": "number", "operator": "exact", "value": "unfinished"}
                ],
                ordering=[{"field": "total", "direction": "desc"}],
            ),
            page_size="50",
        )
        data.update({"mode": "summary", "action": "apply_mode"})
        with patch(
            "django_qbe2.views.build_queryset",
            side_effect=AssertionError("must not execute"),
        ):
            response = self.post(data)
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertEqual(form["mode"].value(), "summary")
        self.assertEqual(form.filters.forms[0]["value"].value(), "unfinished")
        self.assertEqual(form.metrics.forms[0]["function"].value(), "count")
        self.assertContains(response, "resets columns, calculations and ordering")
        self.assertContains(
            response,
            'name="action" value="add_summary_ordering"',
        )

    def test_apply_rows_preserves_conditions_and_restores_default_columns(self):
        data = payload_form_data(
            summary_payload(
                where=group(leaf(value="unfinished")),
                group_by=["active"],
                metrics=[{"id": "m8", "function": "sum", "field": "total"}],
            ),
            page_size="50",
        )
        data.update({"mode": "rows", "action": "apply_mode"})
        response = self.post(data)
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertEqual(form["mode"].value(), "rows")
        self.assertEqual(form.filters.forms[0]["value"].value(), "unfinished")
        self.assertEqual(form["columns"].value(), ["number", "total"])
        self.assertEqual(form.ordering.total_form_count(), 1)
        self.assertEqual(form.ordering.forms[0]["field"].value(), "")

    @override_settings(QBE2_MAX_METRICS=2)
    def test_add_metric_reclaims_deleted_capacity_and_keeps_stable_ids(self):
        data = payload_form_data(
            summary_payload(
                metrics=[
                    {"id": "m2", "function": "sum", "field": "quantity"},
                    {"id": "m7", "function": "avg", "field": "total"},
                ]
            ),
            page_size="50",
        )
        data["metrics-0-DELETE"] = "on"
        data["metrics-1-field"] = "unfinished"
        data["action"] = "add_metric"
        response = self.post(data)
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertEqual(form.metrics.total_form_count(), 2)
        self.assertEqual(form.metrics.forms[0]["id"].value(), "m7")
        self.assertEqual(form.metrics.forms[0]["field"].value(), "unfinished")
        self.assertEqual(form.metrics.forms[1]["id"].value(), "m1")

    def test_malformed_metric_management_is_rejected_without_execution(self):
        data = payload_form_data(summary_payload(), page_size="50")
        data["metrics-TOTAL_FORMS"] = "100000"
        data["action"] = "add_metric"
        with patch(
            "django_qbe2.views.build_summary_source",
            side_effect=AssertionError("must not execute"),
        ):
            response = self.post(data)
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Invalid calculation controls", status_code=400)

    def test_add_summary_ordering_preserves_existing_order_and_adds_a_row(self):
        payload = summary_payload(
            group_by=["active"],
            ordering=[{"type": "group", "field": "active", "direction": "asc"}],
        )
        data = payload_form_data(payload, page_size="50")
        data["action"] = "add_summary_ordering"
        response = self.post(data)
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertEqual(form.summary_ordering.total_form_count(), 2)
        self.assertEqual(
            form.summary_ordering.forms[0]["target"].value(), "group:active"
        )
        self.assertEqual(form.summary_ordering.forms[1]["target"].value(), "")

    @override_settings(QBE2_MAX_ORDERING=1)
    def test_add_summary_ordering_reclaims_deleted_capacity(self):
        payload = summary_payload(
            group_by=["active"],
            ordering=[{"type": "group", "field": "active", "direction": "asc"}],
        )
        data = payload_form_data(payload, page_size="50")
        data["summary_ordering-0-DELETE"] = "on"
        data["action"] = "add_summary_ordering"
        response = self.post(data)
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertEqual(form.summary_ordering.total_form_count(), 1)
        self.assertEqual(form.summary_ordering.forms[0]["target"].value(), "")
