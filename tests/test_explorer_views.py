from django.contrib.auth.models import Permission
from django.test import TestCase

from tests.fixtures import grant_view
from tests.models import Pet, Profile
from tests.test_engine import EngineTests


class ExplorerViewTests(TestCase):
    def setUp(self):
        EngineTests.setUp(self)
        self.client.force_login(self.alice)

    def test_permitted_related_fields_render_text_hierarchy_and_diagram_data(self):
        grant_view(self.alice, Pet, Profile)
        response = self.client.get("/qbe/", {"report": "tests.order"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Registered fields and relationships")
        self.assertContains(response, "customer__name")
        self.assertContains(response, "customer__pets__name")
        self.assertContains(response, "qbe-explorer-data")
        self.assertEqual(response.context["explorer_data"].root_id, "tests.order")

    def test_related_model_without_view_permission_is_not_rendered(self):
        permission = Permission.objects.get(
            codename="view_customer", content_type__app_label="tests"
        )
        self.alice.user_permissions.remove(permission)
        self.alice.__dict__.pop("_perm_cache", None)
        self.alice.__dict__.pop("_user_perm_cache", None)

        response = self.client.get("/qbe/", {"report": "tests.order"})

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "customer__name")
        self.assertNotContains(response, "customer__pets__name")
        self.assertNotContains(response, "customer__")
        self.assertEqual(
            [node.id for node in response.context["explorer_data"].nodes],
            ["tests.order"],
        )

    def test_no_selected_report_has_no_explorer(self):
        response = self.client.get("/qbe/")

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["explorer_data"])
        self.assertNotContains(response, "qbe-explorer-data")

    def test_report_without_related_paths_lists_only_root_fields(self):
        report = self.catalog["tests.order"].report
        original_fields = report.fields
        try:
            report.fields = ("number",)
            response = self.client.get("/qbe/", {"report": "tests.order"})
        finally:
            report.fields = original_fields

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "number")
        self.assertNotContains(response, "customer__name")
        self.assertEqual(len(response.context["explorer_data"].edges), 0)
