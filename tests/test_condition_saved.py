import csv
import io
import json

from django.db import connection
from django.test import TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from django_qbe2.models import SavedQuery
from tests import test_engine
from tests.fixtures import grant_view
from tests.models import Customer, Order
from tests.test_condition_validation import group, grouped_payload, leaf
from tests.test_validation import order_payload


class ConditionSavedTests(TransactionTestCase):
    setUp = test_engine.EngineTests.setUp

    def post(self, route_name, payload, **extra):
        return self.client.post(
            reverse(f"django_qbe2:{route_name}"),
            {"definition": json.dumps(payload), "page_size": 1, **extra},
        )

    def test_saved_tree_open_copy_and_owner_update(self):
        payload = grouped_payload(
            group(
                leaf("total", "100.01", "gte"),
                group(leaf(value="missing"), negated=True),
            )
        )
        self.client.force_login(self.alice)
        response = self.post(
            "saved_create", payload, name="Grouped orders", shared_with="bob"
        )
        self.assertEqual(response.status_code, 302)
        query = SavedQuery.objects.get()
        self.assertEqual(query.definition, payload)
        opened = self.client.get(reverse("django_qbe2:saved_open", args=[query.pk]))
        self.assertEqual(opened.context["form"].payload, payload)
        changed = grouped_payload(group(leaf(), leaf(value="A200"), connector="or"))
        updated = self.client.post(
            reverse("django_qbe2:saved_update", args=[query.pk]),
            {"definition": json.dumps(changed), "page_size": 2, "name": "Updated"},
        )
        self.assertEqual(updated.status_code, 302)
        query.refresh_from_db()
        self.assertEqual(query.definition, changed)
        grant_view(self.bob, Order)
        self.client.force_login(self.bob)
        copied = self.post("saved_create", changed, name="My copy")
        self.assertEqual(copied.status_code, 302)
        self.assertEqual(SavedQuery.objects.get(owner=self.bob).definition, changed)
        denied = self.client.post(
            reverse("django_qbe2:saved_update", args=[query.pk]),
            {"definition": json.dumps(payload), "name": "Denied", "page_size": 1},
        )
        self.assertEqual(denied.status_code, 404)

    def test_shared_tree_pages_and_csv_use_reader_scope_and_read_only_sql(self):
        grant_view(self.bob, Order)
        payload = grouped_payload(
            group(
                group(leaf("total", "100", "gte"), leaf(value="A100"), connector="or"),
                group(leaf(value="missing"), negated=True),
            )
        )
        query = SavedQuery.objects.create(
            owner=self.alice, name="Shared", definition=payload
        )
        query.shared_with.add(self.bob)
        self.client.force_login(self.bob)
        before = list(Order.objects.order_by("pk").values())
        with CaptureQueriesContext(connection) as captured:
            numbers = []
            for page in (1, 2):
                response = self.post(
                    "results", payload, page=page, saved_query=str(query.pk)
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    json.loads(response.context["definition_json"]), payload
                )
                numbers.extend(row["number"] for row in response.context["page"].rows)
            exported = self.post("export", payload)
            self.assertEqual(exported.status_code, 200)
            rows = list(
                csv.reader(io.StringIO(b"".join(exported.streaming_content).decode()))
            )
            exported.close()
        self.assertEqual(numbers, ["B100", "B200"])
        self.assertEqual([row[0] for row in rows[1:]], numbers)
        business_queries = [
            item["sql"].strip().upper()
            for item in captured
            if '"tests_order"' in item["sql"] or '"tests_customer"' in item["sql"]
        ]
        self.assertTrue(business_queries)
        self.assertTrue(
            all(sql.startswith("SELECT") for sql in business_queries), business_queries
        )
        self.assertEqual(list(Order.objects.order_by("pk").values()), before)

    def test_revocation_and_v1_storage_remain_unchanged(self):
        self.client.force_login(self.alice)
        old = SavedQuery.objects.create(
            owner=self.alice, name="Legacy", definition=order_payload()
        )
        self.assertEqual(
            self.client.get(
                reverse("django_qbe2:saved_open", args=[old.pk])
            ).status_code,
            200,
        )
        old.refresh_from_db()
        self.assertEqual(old.definition, order_payload())
        grant_view(self.bob, Order, Customer)
        payload = grouped_payload(
            group(
                leaf("customer__name", "Customer", "contains"),
                leaf("total", "0", "gte"),
                connector="or",
            )
        )
        query = SavedQuery.objects.create(
            owner=self.alice, name="Related", definition=payload
        )
        query.shared_with.add(self.bob)
        self.bob.user_permissions.filter(codename="view_customer").delete()
        self.client.force_login(self.bob)
        self.assertEqual(
            self.client.get(
                reverse("django_qbe2:saved_open", args=[query.pk])
            ).status_code,
            400,
        )
        self.assertEqual(
            self.post("results", payload, saved_query=str(query.pk)).status_code, 400
        )
        self.bob.user_permissions.clear()
        self.assertEqual(
            self.post("results", payload, saved_query=str(query.pk)).status_code, 404
        )
