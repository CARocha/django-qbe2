from uuid import UUID

from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.http import Http404
from django.test import TestCase, override_settings

from django_qbe2.catalog import get_catalog
from django_qbe2.forms import QueryBuilderForm, payload_form_data
from tests import test_engine
from tests.test_validation import order_payload


class SavedStorageTests(TestCase):
    setUp = test_engine.EngineTests.setUp

    def create(self, owner=None, **kwargs):
        from django_qbe2.models import SavedQuery

        return SavedQuery.objects.create(
            owner=owner or self.alice,
            name="My orders",
            definition=order_payload(),
            page_size=25,
            **kwargs,
        )

    def test_private_and_explicitly_shared_visibility(self):
        from django_qbe2.saved import accessible_queries, get_saved_query

        private = self.create(self.bob)
        shared = self.create(self.bob)
        shared.shared_with.add(self.alice)
        own = self.create()
        visible = accessible_queries(self.request, get_catalog(self.request))
        self.assertCountEqual(list(visible), [shared, own])
        self.assertIsInstance(own.pk, UUID)
        with self.assertRaises(Http404):
            get_saved_query(self.request, private.pk)
        with self.assertRaises(Http404):
            get_saved_query(self.request, shared.pk, owner_only=True)
        self.assertEqual(get_saved_query(self.request, shared.pk), shared)

    def test_superuser_cannot_read_another_private_query(self):
        from django_qbe2.saved import get_saved_query

        private = self.create(self.bob)
        self.alice.is_superuser = True
        self.alice.save()
        with self.assertRaises(Http404):
            get_saved_query(self.request, private.pk)

    def test_unsharing_revokes_access(self):
        from django_qbe2.saved import get_saved_query

        query = self.create(self.bob)
        query.shared_with.add(self.alice)
        self.assertEqual(get_saved_query(self.request, query.pk), query)
        query.shared_with.clear()
        with self.assertRaises(Http404):
            get_saved_query(self.request, query.pk)

    def test_shared_list_requires_current_report_visibility(self):
        from django_qbe2.saved import accessible_queries

        own = self.create()
        shared = self.create(self.bob)
        shared.shared_with.add(self.alice)
        self.assertEqual(list(accessible_queries(self.request, {})), [own])

    def test_sharing_validates_known_active_staff_identifiers(self):
        from django_qbe2.saved_forms import SavedQuerySettingsForm

        form = SavedQuerySettingsForm(
            {"name": "  Orders  ", "shared_with": "bob\nbob\nalice"},
            owner=self.alice,
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["name"], "Orders")
        self.assertEqual(form.cleaned_data["shared_with"], [self.bob])
        for identifier, change in (
            ("unknown", {}),
            ("bob", {"is_active": False}),
            ("bob", {"is_staff": False}),
        ):
            with self.subTest(identifier=identifier, change=change):
                self.bob.is_active = change.get("is_active", True)
                self.bob.is_staff = change.get("is_staff", True)
                self.bob.save()
                invalid = SavedQuerySettingsForm(
                    {"name": "Orders", "shared_with": identifier}, owner=self.alice
                )
                self.assertFalse(invalid.is_valid())
                self.assertEqual(
                    invalid.errors["shared_with"],
                    ["Use an active staff user's login identifier on each line."],
                )

    def test_name_and_recipient_bounds(self):
        from django_qbe2.saved_forms import SavedQuerySettingsForm

        for data, control in (
            ({"name": "   "}, "name"),
            ({"name": "x" * 121}, "name"),
            (
                {"name": "Orders", "shared_with": "\n".join(map(str, range(51)))},
                "shared_with",
            ),
        ):
            with self.subTest(control=control):
                form = SavedQuerySettingsForm(data, owner=self.alice)
                self.assertFalse(form.is_valid())
                self.assertIn(control, form.errors)

    @override_settings(QBE2_MAX_SAVED_QUERIES=1)
    def test_quota_preserves_existing_queries_and_shares(self):
        from django_qbe2.models import SavedQuery
        from django_qbe2.saved import create_saved_query
        from django_qbe2.saved_forms import SavedQuerySettingsForm

        form = QueryBuilderForm(
            payload_form_data(order_payload(), page_size="25"),
            catalog=get_catalog(self.request),
        )
        settings_form = SavedQuerySettingsForm(
            {"name": "Orders", "shared_with": "bob"}, owner=self.alice
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(settings_form.is_valid(), settings_form.errors)
        first = create_saved_query(self.request, form, settings_form)
        with self.assertRaisesMessage(ValidationError, "saved-query limit"):
            create_saved_query(self.request, form, settings_form)
        self.assertEqual(SavedQuery.objects.filter(owner=self.alice).count(), 1)
        self.assertEqual(list(first.shared_with.all()), [self.bob])
        self.assertEqual(first.definition, order_payload())
        self.assertEqual(first.page_size, 25)

    def test_definition_byte_limit_and_invalid_setting(self):
        from django_qbe2.limits import get_limits
        from django_qbe2.saved import check_definition_size

        check_definition_size({"value": "é" * 100})
        with self.assertRaises(ValidationError):
            check_definition_size({"value": "é" * 32768})
        with override_settings(QBE2_MAX_SAVED_QUERIES=0):
            with self.assertRaises(ImproperlyConfigured):
                get_limits()
