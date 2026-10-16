import json
from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from tests import test_engine
from tests.test_validation import order_payload


class ResultsTests(TestCase):
    setUp = test_engine.EngineTests.setUp

    def post(self, payload=None, **extra):
        self.client.force_login(self.alice)
        return self.client.post(
            reverse("django_qbe2:results"),
            {
                "definition": json.dumps(payload or order_payload()),
                **extra,
            },
        )

    def test_pagination_preserves_definition(self):
        payload = order_payload(
            columns=["total", "number"],
            filters=[
                {
                    "field": "total",
                    "operator": "gte",
                    "value": "100",
                }
            ],
            ordering=[{"field": "number", "direction": "asc"}],
        )
        response = self.post(payload, page_size="1", page="2")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "A200")
        self.assertNotContains(response, "A100")
        self.assertNotContains(response, "B100")
        self.assertEqual(json.loads(response.context["definition_json"]), payload)
        self.assertContains(response, "csrfmiddlewaretoken")

    def test_excel_export_button_is_shown_when_optional_dependency_is_available(self):
        with patch("django_qbe2.views.excel_available", return_value=True):
            response = self.post()
        self.assertContains(response, 'value="xlsx"')
        self.assertContains(response, "Export Excel")

    def test_excel_export_button_is_hidden_without_optional_dependency(self):
        with patch("django_qbe2.views.excel_available", return_value=False):
            response = self.post()
        self.assertNotContains(response, "Export Excel")
        self.assertContains(response, "Export CSV")

    def test_invalid_definition_returns_builder_with_errors(self):
        response = self.post(order_payload(columns=["owner__password"]))
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "permitted column", status_code=400)

    def test_missing_report_returns_builder_validation_error(self):
        self.client.force_login(self.alice)

        response = self.client.post(reverse("django_qbe2:results"), {})

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "This field is required.", status_code=400)
        self.assertContains(
            response, "Choose a report before previewing.", status_code=400
        )

    def test_invisible_report_is_404(self):
        self.assertEqual(self.post(order_payload(report="auth.user")).status_code, 404)

    def test_results_require_post_and_csrf(self):
        self.client.force_login(self.alice)
        self.assertEqual(
            self.client.get(reverse("django_qbe2:results")).status_code, 405
        )
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.alice)
        self.assertEqual(
            client.post(reverse("django_qbe2:results"), {}).status_code, 403
        )

    @override_settings(QBE2_MAX_ROWS=1)
    def test_truncation_is_visible(self):
        response = self.post()
        self.assertTrue(response.context["page"].truncated)
        self.assertContains(response, "Results limited")

    def test_malformed_json_and_invalid_pagination_are_400(self):
        self.assertEqual(self.post(page="-1").status_code, 400)
        self.client.force_login(self.alice)
        response = self.client.post(reverse("django_qbe2:results"), {"definition": "{"})
        self.assertEqual(response.status_code, 400)

    @override_settings(QBE2_MAX_FILTERS=7)
    def test_edit_retains_capacity_to_add_conditions(self):
        response = self.post(action="edit")
        self.assertEqual(response.status_code, 200)
        maximum = (
            response.context["form"].filters.management_form["MAX_NUM_FORMS"].value()
        )
        self.assertEqual(maximum, "7")

    def test_edit_keeps_an_empty_condition_without_javascript(self):
        response = self.post(action="edit")
        self.assertEqual(len(response.context["form"].filters.forms), 1)


class MultiValuedResultsTests(TestCase):
    setUp = test_engine.EngineTests.setUp

    def test_related_values_render_as_joined_escaped_html(self):
        from tests.fixtures import grant_view
        from tests.models import Pet

        grant_view(self.alice, Pet)
        for cache in ("_perm_cache", "_user_perm_cache", "_group_perm_cache"):
            if hasattr(self.alice, cache):
                delattr(self.alice, cache)
        customer = self.orders[0].customer
        Pet.objects.create(customer=customer, name="<Milo>")
        Pet.objects.create(customer=customer, name="Luna")
        self.client.force_login(self.alice)
        payload = order_payload(columns=["number", "customer__pets__name"])
        response = self.client.post(
            reverse("django_qbe2:results"),
            {"definition": json.dumps(payload), "page_size": "50"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "&lt;Milo&gt;, Luna")
        self.assertNotContains(response, "<Milo>")
