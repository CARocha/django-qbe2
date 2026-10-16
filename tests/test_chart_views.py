import json

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from tests.fixtures import grant_view, make_orders, make_staff
from tests.models import Customer, Order
from tests.test_summary_validation import summary_payload


class SummaryBarChartViewTests(TestCase):
    def setUp(self):
        self.user = make_staff("summary-chart-view")
        grant_view(self.user, Order, Customer)
        self.orders = make_orders(self.user)
        self.client.force_login(self.user)

    def post(self, payload, **extra):
        return self.client.post(
            reverse("django_qbe2:results"),
            {"definition": json.dumps(payload), "page_size": "50", **extra},
        )

    def test_grouped_summary_renders_chart_and_preserves_the_result_table(self):
        payload = summary_payload(
            group_by=["active"],
            metrics=[
                {"id": "m1", "function": "count", "field": None},
                {"id": "m2", "function": "sum", "field": "total"},
            ],
        )

        with CaptureQueriesContext(connection) as queries:
            response = self.post(payload, chart_metric="m2")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["bar_chart"].metric_id, "m2")
        self.assertContains(response, "Summary bar chart")
        self.assertContains(response, "current page")
        self.assertContains(response, "Report results table")
        self.assertContains(response, "Export CSV")
        self.assertContains(response, 'name="chart_metric" value="m2"')
        business_reads = [
            query["sql"]
            for query in queries
            if query["sql"].lstrip().upper().startswith("SELECT")
            and '"tests_order"' in query["sql"]
        ]
        self.assertEqual(len(business_reads), 1)

    def test_multiple_metric_selection_is_temporary_and_invalid_ids_fall_back(self):
        payload = summary_payload(
            group_by=["active"],
            metrics=[
                {"id": "m1", "function": "count", "field": None},
                {"id": "m2", "function": "sum", "field": "total"},
            ],
        )

        response = self.post(payload, chart_metric="forged__field")

        self.assertEqual(response.context["bar_chart"].metric_id, "m1")
        self.assertNotIn("chart_metric", response.context["definition_json"])
        self.assertContains(response, 'value="m1" selected>Count records</option>')

    def test_chart_uses_only_current_page_and_pagination_carries_metric(self):
        self.orders[1].active = False
        self.orders[1].save(update_fields=["active"])
        payload = summary_payload(
            group_by=["active"],
            metrics=[
                {"id": "m1", "function": "count", "field": None},
                {"id": "m2", "function": "sum", "field": "total"},
            ],
            ordering=[{"type": "group", "field": "active", "direction": "asc"}],
        )

        response = self.post(payload, page_size="1", page="2", chart_metric="m2")

        self.assertEqual(response.context["page"].page, 2)
        self.assertEqual(len(response.context["bar_chart"].bars), 1)
        self.assertEqual(response.context["bar_chart"].bars[0].label, "True")
        self.assertContains(response, 'name="chart_metric" value="m2"')
        self.assertContains(response, 'name="page" value="1"')

        changed_metric = self.post(payload, page_size="1", chart_metric="m1")
        self.assertEqual(changed_metric.context["page"].page, 1)

    def test_no_chart_for_ungrouped_multi_group_or_empty_results(self):
        cases = (
            summary_payload(),
            summary_payload(group_by=["active", "number"]),
        )
        for payload in cases:
            with self.subTest(group_by=payload["group_by"]):
                response = self.post(payload)
                self.assertIsNone(response.context["bar_chart"])
                self.assertContains(response, "Bar charts require one grouping field")

        Order.objects.filter(owner=self.user).delete()
        response = self.post(summary_payload(group_by=["active"]))
        self.assertIsNone(response.context["bar_chart"])
        self.assertContains(response, "No groups match your conditions")

    def test_category_labels_are_escaped_and_chart_selection_has_no_saved_definition(
        self,
    ):
        Order.objects.filter(pk=self.orders[0].pk).update(
            number="<img src=x onerror=alert(1)>"
        )
        payload = summary_payload(
            group_by=["number"],
            metrics=[{"id": "m1", "function": "count", "field": None}],
        )

        response = self.post(payload, chart_metric="m1")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Summary bar chart")
        self.assertContains(response, "&lt;img src=x onerror=alert(1)&gt;")
        self.assertNotContains(response, "<img src=x onerror=alert(1)>")
        self.assertNotIn("chart_metric", response.context["definition_json"])
