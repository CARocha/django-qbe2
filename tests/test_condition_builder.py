import json
from copy import deepcopy
from unittest.mock import patch

from django.http import QueryDict
from django.test import TestCase

from django_qbe2.forms import QueryBuilderForm, payload_form_data
from tests import test_engine
from tests.test_condition_validation import group, grouped_payload, leaf


class ConditionBuilderTests(TestCase):
    setUp = test_engine.EngineTests.setUp

    def data(self, where):
        return payload_form_data(grouped_payload(where), page_size="50")

    def test_mixed_tree_round_trip_and_legacy_controls(self):
        payload = grouped_payload(
            group(
                group(leaf(), leaf(value="A200"), connector="or"),
                group(leaf("total", "200", "gte"), negated=True),
            )
        )
        form = QueryBuilderForm(
            payload_form_data(payload, page_size="50"), catalog=self.catalog
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.payload, payload)
        legacy = QueryDict(
            "report=tests.order&columns=number&page_size=50&filters-TOTAL_FORMS=1&filters-INITIAL_FORMS=0&filters-0-field=number&filters-0-operator=exact&filters-0-value=A100&ordering-TOTAL_FORMS=0&ordering-INITIAL_FORMS=0"
        )
        form = QueryBuilderForm(legacy, catalog=self.catalog)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.payload["version"], 1)

    def test_forged_graphs_and_counts_are_rejected(self):
        base = self.data(group(group(leaf())))
        variants = [
            {"groups-1-id": "root"},
            {"groups-1-parent": "missing"},
            {"groups-1-parent": "g1"},
            {"filters-0-group": "missing"},
            {"groups-TOTAL_FORMS": "100000"},
            {"groups-0-DELETE": "on"},
        ]
        for changes in variants:
            data = base.copy()
            data.update(changes)
            with self.subTest(changes=changes):
                form = QueryBuilderForm(data, catalog=self.catalog)
                self.assertFalse(form.is_valid())

    def test_deleting_group_removes_descendants_and_retains_other_conditions(self):
        data = self.data(group(leaf(), group(group(leaf(value="A200")))))
        data["groups-1-DELETE"] = "on"
        form = QueryBuilderForm(data, catalog=self.catalog)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.payload["version"], 1)
        self.assertEqual(form.payload["filters"], [leaf()])

    def test_no_javascript_actions_preserve_incomplete_values_without_execution(self):
        self.client.force_login(self.alice)
        data = self.data(group(leaf()))
        data["filters-0-value"] = "unfinished"
        for action, expected in (
            ("add_group:root", "Match any (OR)"),
            ("add_condition:root", "filters-1-value"),
        ):
            with patch(
                "django_qbe2.views.build_queryset",
                side_effect=AssertionError("must not execute"),
            ):
                response = self.client.post(
                    "/qbe/results/", {**dict(data.items()), "action": action}
                )
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, expected)
            self.assertContains(response, "unfinished")

    def test_deep_json_returns_validation_response(self):
        self.client.force_login(self.alice)
        response = self.client.post(
            "/qbe/results/", {"definition": "[" * 1500 + "0" + "]" * 1500}
        )
        self.assertEqual(response.status_code, 400)

    def test_invalid_original_is_not_normalized_into_a_valid_query(self):
        self.client.force_login(self.alice)
        payload = deepcopy(grouped_payload(group(group(leaf()))))
        payload["where"]["children"][0]["extra"] = True
        response = self.client.post(
            "/qbe/results/", {"definition": json.dumps(payload), "page_size": 50}
        )
        self.assertEqual(response.status_code, 400)
