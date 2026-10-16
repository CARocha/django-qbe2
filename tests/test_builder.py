from django.test import TestCase
from django.urls import reverse

from tests import test_engine


class BuilderTests(TestCase):
    setUp = test_engine.EngineTests.setUp

    def test_only_authorized_choices_render(self):
        self.client.force_login(self.alice)
        response = self.client.get("/qbe/", {"report": "tests.order"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "customer__name")
        self.assertNotContains(response, "owner__password")
        self.assertContains(response, "csrfmiddlewaretoken")

    def test_preview_is_disabled_until_a_report_is_selected(self):
        self.client.force_login(self.alice)

        unselected = self.client.get(reverse("django_qbe2:builder"))
        selected = self.client.get(
            reverse("django_qbe2:builder"), {"report": "tests.order"}
        )

        self.assertRegex(
            unselected.content.decode(), r'<input id="qbe-preview-report"[^>]*disabled'
        )
        self.assertContains(unselected, "Choose a report before previewing.")
        self.assertContains(selected, 'id="qbe-preview-report"')
        self.assertNotRegex(
            selected.content.decode(), r'<input id="qbe-preview-report"[^>]*disabled'
        )

    def test_catalog_empty_has_clear_message(self):
        self.client.force_login(self.bob)
        response = self.client.get("/qbe/")
        self.assertContains(response, "No reports available")

    def test_labels_are_escaped(self):
        report = self.catalog["tests.order"].report
        original = report.field_labels
        report.field_labels = {"number": "<script>alert(1)</script>"}
        try:
            self.client.force_login(self.alice)
            response = self.client.get("/qbe/", {"report": "tests.order"})
            self.assertContains(response, "&lt;script&gt;")
            self.assertNotContains(response, "<script>alert(1)</script>")
        finally:
            report.field_labels = original

    def test_form_preserves_columns_and_converts_boolean(self):
        from django_qbe2.forms import QueryBuilderForm

        form = QueryBuilderForm(
            {
                "report": "tests.order",
                "columns": ["total", "number"],
                "page_size": "50",
                "filters-TOTAL_FORMS": "1",
                "filters-INITIAL_FORMS": "0",
                "filters-0-field": "active",
                "filters-0-operator": "exact",
                "filters-0-value": "false",
                "ordering-TOTAL_FORMS": "0",
                "ordering-INITIAL_FORMS": "0",
            },
            catalog=self.catalog,
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.definition.columns, ("total", "number"))
        self.assertIs(form.definition.filters[0].value, False)

    def test_builder_disallows_post(self):
        self.client.force_login(self.alice)
        self.assertEqual(
            self.client.post(reverse("django_qbe2:builder")).status_code, 405
        )
