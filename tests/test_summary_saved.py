import csv
import io
import json

from django.contrib.auth.models import Permission
from django.test import TransactionTestCase
from django.urls import reverse

from django_qbe2.models import SavedQuery
from tests import test_engine
from tests.fixtures import grant_view
from tests.models import Customer, Order
from tests.test_summary_validation import summary_payload
from tests.test_validation import order_payload


class SummarySavedQueryTests(TransactionTestCase):
    setUp = test_engine.EngineTests.setUp

    def url(self, name, query=None):
        args = [query.pk] if query else []
        return reverse(f"django_qbe2:saved_{name}", args=args)

    def data(self, payload, **extra):
        return {
            "name": "Order summary",
            "definition": json.dumps(payload),
            "page_size": "1",
            **extra,
        }

    def create_summary(self, owner=None, payload=None):
        return SavedQuery.objects.create(
            owner=owner or self.alice,
            name="Order summary",
            definition=payload or summary_payload(),
            page_size=1,
        )

    def test_create_open_and_update_store_only_the_v3_definition(self):
        self.client.force_login(self.alice)
        payload = summary_payload(
            group_by=["active"],
            metrics=[
                {"id": "m1", "function": "count", "field": None},
                {"id": "m2", "function": "sum", "field": "total"},
            ],
        )
        created = self.client.post(self.url("create"), self.data(payload))
        self.assertEqual(created.status_code, 302)
        query = SavedQuery.objects.get()
        self.assertEqual(query.definition, payload)
        self.assertEqual(set(query.definition), set(payload))

        from unittest.mock import patch

        with patch("django_qbe2.views.execute_summary", side_effect=AssertionError):
            opened = self.client.get(self.url("open", query))
        self.assertEqual(opened.status_code, 200)
        self.assertEqual(opened.context["form"].payload, payload)

        updated_payload = summary_payload(
            group_by=["m1"],
            metrics=[{"id": "m2", "function": "avg", "field": "total"}],
        )
        updated = self.client.post(
            self.url("update", query),
            self.data(updated_payload, name="Updated summary"),
        )
        self.assertEqual(updated.status_code, 302)
        query.refresh_from_db()
        self.assertEqual(query.definition, updated_payload)
        self.assertEqual(query.name, "Updated summary")

    def test_reader_executes_pages_exports_and_copies_with_own_scope(self):
        grant_view(self.bob, Order, Customer)
        payload = summary_payload(
            group_by=["number"],
            metrics=[{"id": "m1", "function": "sum", "field": "total"}],
            ordering=[{"type": "group", "field": "number", "direction": "asc"}],
        )
        query = self.create_summary(payload=payload)
        query.shared_with.add(self.bob)
        self.client.force_login(self.bob)

        result = self.client.post(
            reverse("django_qbe2:results"),
            self.data(payload, saved_query=str(query.pk), page="2"),
        )
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.context["page"].rows[0]["group:number"], "B200")
        self.assertNotContains(result, "A100")

        exported = self.client.post(reverse("django_qbe2:export"), self.data(payload))
        rows = list(
            csv.reader(io.StringIO(b"".join(exported.streaming_content).decode()))
        )
        exported.close()
        self.assertEqual([row[0] for row in rows[1:]], ["B100", "B200"])

        copied = self.client.post(
            self.url("create"), self.data(payload, name="My copy")
        )
        self.assertEqual(copied.status_code, 302)
        copy = SavedQuery.objects.get(owner=self.bob)
        self.assertEqual(copy.definition, payload)
        self.assertFalse(copy.shared_with.exists())

    def test_related_permission_revocation_invalidates_summary_freshly(self):
        payload = summary_payload(
            group_by=["customer__name"],
            metrics=[
                {"id": "m1", "function": "sum", "field": "customer__credit_limit"}
            ],
        )
        query = self.create_summary(payload=payload)
        self.alice.user_permissions.remove(
            Permission.objects.get(
                content_type__app_label="tests", codename="view_customer"
            )
        )
        self.client.force_login(self.alice)
        response = self.client.get(self.url("open", query))
        self.assertEqual(response.status_code, 400)
        self.assertNotContains(response, "customer__credit_limit", status_code=400)

    def test_definition_update_preserves_readers_and_owner_only_mutation(self):
        query = self.create_summary()
        query.shared_with.add(self.bob)
        self.client.force_login(self.alice)
        response = self.client.post(
            self.url("update", query), self.data(summary_payload(group_by=["active"]))
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(list(query.shared_with.all()), [self.bob])

        self.bob.is_superuser = True
        self.bob.save()
        self.client.force_login(self.bob)
        self.assertEqual(
            self.client.post(
                self.url("update", query), self.data(summary_payload())
            ).status_code,
            404,
        )

    def test_row_v1_and_v2_definitions_still_open_alongside_v3(self):
        from tests.test_condition_validation import grouped_payload

        queries = [
            self.create_summary(payload=order_payload()),
            self.create_summary(payload=grouped_payload()),
            self.create_summary(payload=summary_payload()),
        ]
        self.client.force_login(self.alice)
        for query in queries:
            with self.subTest(version=query.definition["version"]):
                response = self.client.get(self.url("open", query))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["form"].payload, query.definition)
