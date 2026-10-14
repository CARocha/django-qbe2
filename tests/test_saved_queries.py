import csv
import io
import json

from django.contrib.auth.models import Permission
from django.test import Client, TransactionTestCase, override_settings
from django.urls import reverse

from django_qbe2.models import SavedQuery
from tests import test_engine
from tests.fixtures import grant_view
from tests.models import Order
from tests.test_validation import order_payload


class SavedQueryTests(TransactionTestCase):
    setUp = test_engine.EngineTests.setUp

    def url(self, name, query=None):
        return reverse(f"django_qbe2:saved_{name}", args=[query.pk] if query else [])

    def saved(self, owner=None, **kwargs):
        return SavedQuery.objects.create(
            owner=owner or self.alice,
            name=kwargs.pop("name", "My saved orders"),
            definition=kwargs.pop("definition", order_payload()),
            page_size=kwargs.pop("page_size", 1),
            **kwargs,
        )

    def data(self, **extra):
        return {
            "name": "My orders",
            "definition": json.dumps(order_payload()),
            "page_size": "1",
            **extra,
        }

    def test_create_stores_definition_and_can_open_without_running_report(self):
        self.client.force_login(self.alice)
        payload = order_payload(
            columns=["total", "number"],
            filters=[{"field": "total", "operator": "gte", "value": "100.01"}],
        )
        response = self.client.post(
            self.url("create"), self.data(definition=json.dumps(payload))
        )
        self.assertEqual(response.status_code, 302)
        query = SavedQuery.objects.get()
        self.assertEqual(query.owner, self.alice)
        self.assertEqual(query.definition, payload)
        self.assertEqual(query.page_size, 1)
        from unittest.mock import patch

        with patch("django_qbe2.views.build_queryset", side_effect=AssertionError):
            opened = self.client.get(self.url("open", query))
        self.assertEqual(opened.status_code, 200)
        self.assertEqual(opened.context["form"].payload, payload)
        self.assertContains(opened, f'name="saved_query" value="{query.pk}"')
        self.assertContains(
            opened,
            f'<form method="get" action="{reverse("django_qbe2:builder")}"',
        )

    def test_owner_updates_definition_explicitly_and_preview_does_not_save(self):
        query = self.saved()
        self.client.force_login(self.alice)
        payload = order_payload(columns=["number"])
        preview = self.client.post(
            reverse("django_qbe2:results"),
            self.data(definition=json.dumps(payload), saved_query=str(query.pk)),
        )
        self.assertEqual(preview.status_code, 200)
        self.assertContains(preview, "Update saved query")
        query.refresh_from_db()
        self.assertEqual(query.definition, order_payload())
        updated = self.client.post(
            self.url("update", query),
            self.data(name="Updated", definition=json.dumps(payload), page_size="2"),
        )
        self.assertEqual(updated.status_code, 302)
        query.refresh_from_db()
        self.assertEqual(query.definition, payload)
        self.assertEqual(query.page_size, 2)
        self.assertEqual(query.name, "Updated")

    def test_recipient_reads_executes_and_copies_using_their_own_row_policy(self):
        grant_view(self.bob, Order)
        query = self.saved()
        query.shared_with.add(self.bob)
        self.client.force_login(self.bob)
        opened = self.client.get(self.url("open", query))
        self.assertEqual(opened.status_code, 200)
        result = self.client.post(
            reverse("django_qbe2:results"), self.data(saved_query=str(query.pk))
        )
        self.assertContains(result, "B100")
        self.assertNotContains(result, "A100")
        self.assertContains(result, "Save a copy")
        self.assertNotContains(result, "Update saved query")
        exported = self.client.post(reverse("django_qbe2:export"), self.data())
        rows = list(
            csv.reader(io.StringIO(b"".join(exported.streaming_content).decode()))
        )
        exported.close()
        self.assertEqual(rows[1][0], "B100")
        copied = self.client.post(self.url("create"), self.data(name="My copy"))
        self.assertEqual(copied.status_code, 302)
        copy = SavedQuery.objects.get(owner=self.bob)
        self.assertNotEqual(copy.pk, query.pk)
        self.assertFalse(copy.shared_with.exists())

    def test_other_users_and_superusers_cannot_read_private_queries(self):
        query = self.saved()
        for superuser in (False, True):
            with self.subTest(superuser=superuser):
                self.bob.is_superuser = superuser
                self.bob.save()
                self.client.force_login(self.bob)
                self.assertEqual(
                    self.client.get(self.url("open", query)).status_code, 404
                )
                self.assertNotContains(self.client.get(self.url("list")), query.name)
                self.assertEqual(
                    self.client.post(
                        reverse("django_qbe2:results"),
                        self.data(saved_query=str(query.pk)),
                    ).status_code,
                    404,
                )

    def test_shared_readers_cannot_update_rename_reshare_or_delete(self):
        query = self.saved()
        query.shared_with.add(self.bob)
        self.bob.is_superuser = True
        self.bob.save()
        self.client.force_login(self.bob)
        for action in ("update", "settings", "delete"):
            with self.subTest(action=action):
                self.assertEqual(
                    self.client.post(self.url(action, query), self.data()).status_code,
                    404,
                )
        query.refresh_from_db()
        self.assertEqual(query.name, "My saved orders")
        self.assertEqual(list(query.shared_with.all()), [self.bob])

    def test_owner_can_rename_share_and_revoke_access(self):
        query = self.saved()
        self.client.force_login(self.alice)
        response = self.client.post(
            self.url("settings", query), {"name": "Shared orders", "shared_with": "bob"}
        )
        self.assertEqual(response.status_code, 302)
        query.refresh_from_db()
        self.assertEqual(query.name, "Shared orders")
        grant_view(self.bob, Order)
        self.client.force_login(self.bob)
        self.assertContains(self.client.get(self.url("list")), "Shared orders")
        self.client.force_login(self.alice)
        self.client.post(self.url("settings", query), {"name": "Private again"})
        self.client.force_login(self.bob)
        self.assertEqual(self.client.get(self.url("open", query)).status_code, 404)

    def test_revoked_report_permission_hides_shared_query(self):
        query = self.saved(name="Sensitive saved name")
        query.shared_with.add(self.bob)
        self.client.force_login(self.bob)
        self.assertEqual(self.client.get(self.url("open", query)).status_code, 404)
        self.assertNotContains(self.client.get(self.url("list")), query.name)

    def test_owner_can_cleanup_after_report_permission_is_revoked(self):
        query = self.saved()
        permission = Permission.objects.get(
            content_type__app_label="tests", codename="view_order"
        )
        self.alice.user_permissions.remove(permission)
        self.client.force_login(self.alice)
        self.assertEqual(self.client.get(self.url("open", query)).status_code, 404)
        renamed = self.client.post(self.url("settings", query), {"name": "Obsolete"})
        self.assertEqual(renamed.status_code, 302)
        confirmation = self.client.get(self.url("delete", query))
        self.assertEqual(confirmation.status_code, 200)
        self.assertTrue(SavedQuery.objects.filter(pk=query.pk).exists())
        self.client.post(self.url("delete", query))
        self.assertFalse(SavedQuery.objects.filter(pk=query.pk).exists())

    def test_stale_definition_does_not_disclose_raw_payload(self):
        query = self.saved(
            definition=order_payload(
                filters=[
                    {
                        "field": "removed_field",
                        "operator": "exact",
                        "value": "secret-marker",
                    }
                ]
            )
        )
        self.client.force_login(self.alice)
        response = self.client.get(self.url("open", query))
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "no longer valid", status_code=400)
        self.assertNotContains(response, "secret-marker", status_code=400)
        self.assertNotContains(response, "removed_field", status_code=400)

    def test_invalid_save_and_update_leave_storage_unchanged(self):
        query = self.saved()
        self.client.force_login(self.alice)
        for data in (
            self.data(name=" "),
            self.data(page_size="201"),
            self.data(definition="{"),
            self.data(shared_with="unknown"),
            self.data(
                definition=json.dumps(order_payload(columns=["owner__password"]))
            ),
        ):
            with self.subTest(data=data):
                self.assertEqual(
                    self.client.post(self.url("create"), data).status_code, 400
                )
                self.assertEqual(
                    self.client.post(self.url("update", query), data).status_code, 400
                )
                query.refresh_from_db()
                self.assertEqual(query.definition, order_payload())
                self.assertEqual(query.name, "My saved orders")
                self.assertEqual(SavedQuery.objects.count(), 1)

    @override_settings(QBE2_MAX_SAVED_QUERIES=1)
    def test_full_quota_still_allows_updating_existing_query(self):
        query = self.saved()
        self.client.force_login(self.alice)
        response = self.client.post(self.url("create"), self.data())
        self.assertContains(response, "saved-query limit", status_code=400)
        self.assertEqual(
            self.client.post(self.url("update", query), self.data()).status_code, 302
        )

    def test_saved_list_is_bounded_and_names_are_escaped(self):
        self.client.force_login(self.alice)
        for number in range(26):
            self.saved(name=f"Saved {number}")
        response = self.client.get(self.url("list"))
        self.assertEqual(len(response.context["saved_page"]), 25)
        response = self.client.get(self.url("list") + "?page=2")
        self.assertEqual(len(response.context["saved_page"]), 1)
        self.saved(name="<script>bad()</script>")
        response = self.client.get(self.url("list"))
        self.assertContains(response, "&lt;script&gt;bad()&lt;/script&gt;")
        self.assertNotContains(response, "<script>bad()</script>")

    def test_saved_context_survives_edit_and_pagination(self):
        query = self.saved()
        self.client.force_login(self.alice)
        for extra in ({"action": "edit"}, {"page": "2"}):
            response = self.client.post(
                reverse("django_qbe2:results"),
                self.data(saved_query=str(query.pk), **extra),
            )
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, f'name="saved_query" value="{query.pk}"')

    def test_methods_access_and_csrf(self):
        query = self.saved()
        self.assertEqual(self.client.get(self.url("list")).status_code, 302)
        self.client.force_login(self.alice)
        self.assertEqual(self.client.get(self.url("create")).status_code, 405)
        self.assertEqual(self.client.get(self.url("update", query)).status_code, 405)
        self.assertEqual(self.client.post(self.url("open", query)).status_code, 405)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.alice)
        for action in ("create", "update", "settings", "delete"):
            target = self.url(action, None if action == "create" else query)
            self.assertEqual(client.post(target, self.data()).status_code, 403)
        self.alice.is_staff = False
        self.alice.save()
        self.client.force_login(self.alice)
        self.assertEqual(self.client.get(self.url("list")).status_code, 403)

    def test_definition_update_preserves_recipients(self):
        query = self.saved()
        query.shared_with.add(self.bob)
        self.client.force_login(self.alice)
        response = self.client.post(self.url("update", query), self.data())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(list(query.shared_with.all()), [self.bob])

    def test_failed_update_retry_cannot_misrepresent_sharing(self):
        query = self.saved()
        query.shared_with.add(self.bob)
        self.client.force_login(self.alice)
        failed = self.client.post(self.url("update", query), self.data(name=""))
        self.assertEqual(failed.status_code, 400)
        self.assertNotContains(failed, 'name="shared_with"', status_code=400)
        self.assertNotContains(
            failed, "Leave empty for a private query", status_code=400
        )
        self.assertContains(failed, self.url("settings", query), status_code=400)
        corrected = self.client.post(self.url("update", query), self.data(name="Fixed"))
        self.assertEqual(corrected.status_code, 302)
        query.refresh_from_db()
        self.assertEqual(query.name, "Fixed")
        self.assertEqual(list(query.shared_with.all()), [self.bob])
        rejected = self.client.post(
            self.url("update", query), self.data(shared_with="")
        )
        self.assertEqual(rejected.status_code, 400)
        self.assertEqual(list(query.shared_with.all()), [self.bob])

    def test_payload_size_limit_is_enforced_before_storage(self):
        self.client.force_login(self.alice)
        payload = order_payload(
            filters=[{"field": "note", "operator": "contains", "value": "é" * 32768}]
        )
        response = self.client.post(
            self.url("create"), self.data(definition=json.dumps(payload))
        )
        self.assertContains(response, "64 KiB", status_code=400)
        self.assertFalse(SavedQuery.objects.exists())

    @override_settings(QBE2_PAGE_SIZE=1, QBE2_MAX_PAGE_SIZE=1)
    def test_changed_limits_revalidate_stored_page_size(self):
        query = self.saved(page_size=2)
        self.client.force_login(self.alice)
        self.assertEqual(self.client.get(self.url("open", query)).status_code, 400)

    def test_revoked_related_permission_rejects_stored_columns(self):
        query = self.saved(definition=order_payload(columns=["customer__name"]))
        self.alice.user_permissions.remove(
            Permission.objects.get(
                content_type__app_label="tests", codename="view_customer"
            )
        )
        self.client.force_login(self.alice)
        response = self.client.get(self.url("open", query))
        self.assertEqual(response.status_code, 400)
        self.assertNotContains(response, "customer__name", status_code=400)

    def test_changed_choices_revalidate_saved_equality(self):
        query = self.saved(
            definition=order_payload(
                filters=[{"field": "number", "operator": "exact", "value": "A100"}]
            )
        )
        field = Order._meta.get_field("number")
        original = field.choices
        self.client.force_login(self.alice)
        try:
            field.choices = [("A200", "Other order")]
            response = self.client.get(self.url("open", query))
        finally:
            field.choices = original
        self.assertEqual(response.status_code, 400)
        self.assertNotContains(response, "A100", status_code=400)
