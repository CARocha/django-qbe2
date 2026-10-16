import json
from datetime import time

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from django_qbe2.models import SavedQuery, ScheduledReport
from tests.fixtures import grant_view, make_staff
from tests.models import Customer, Order
from tests.test_summary_validation import summary_payload
from tests.test_validation import order_payload


class ScheduledReportViewsTests(TestCase):
    def setUp(self):
        self.owner = make_staff("schedule-view-owner")
        self.other = make_staff("schedule-view-other")
        grant_view(self.owner, Order, Customer)
        self.client.force_login(self.owner)

    def schedule(self, owner=None, **changes):
        defaults = {
            "owner": owner or self.owner,
            "name": "Daily orders",
            "definition": order_payload(),
            "page_size": 25,
            "frequency": "daily",
            "weekday": None,
            "local_time": time(9),
            "timezone": "America/Managua",
            "recipients": ["reports@example.com"],
            "format": "csv",
            "next_run_at": timezone.now(),
        }
        defaults.update(changes)
        return ScheduledReport.objects.create(**defaults)

    def begin_create(self, definition):
        return self.client.post(
            reverse("django_qbe2:scheduled_create"),
            {"definition": json.dumps(definition), "page_size": "25"},
        )

    def finish_create(self, response, **changes):
        data = {
            "definition": response.context["definition_json"],
            "page_size": str(response.context["page_size"]),
            "schedule_config": "1",
            "name": "Weekly orders",
            "frequency": "weekly",
            "weekday": "0",
            "local_time": "09:30",
            "timezone": "America/Managua",
            "recipients": " Sales@example.com \nsales@EXAMPLE.com ",
            "format": "csv",
            "confirm_recipients": "on",
        }
        data.update(changes)
        return self.client.post(reverse("django_qbe2:scheduled_create"), data)

    def test_create_schedule_copies_validated_row_definition(self):
        definition = order_payload()
        response = self.begin_create(definition)
        self.assertEqual(response.status_code, 200)
        created = self.finish_create(response)

        self.assertEqual(created.status_code, 302)
        schedule = ScheduledReport.objects.get(owner=self.owner)
        self.assertEqual(schedule.definition, definition)
        self.assertEqual(schedule.page_size, 25)
        self.assertEqual(schedule.recipients, ["Sales@example.com"])
        self.assertGreater(schedule.next_run_at, timezone.now())

    def test_schedule_form_groups_fields_in_responsive_layout(self):
        response = self.begin_create(order_payload())

        self.assertContains(response, "qbe-schedule-form")
        self.assertContains(response, "qbe-schedule-grid")
        self.assertContains(response, "qbe-schedule-field--wide")
        self.assertContains(response, "qbe-schedule-field--full")
        self.assertContains(response, 'id="id_recipients"')

    def test_create_schedule_copies_summary_definition(self):
        definition = summary_payload(
            group_by=["active"],
            metrics=[{"id": "m1", "function": "count", "field": None}],
        )
        response = self.begin_create(definition)
        self.assertEqual(response.status_code, 200)
        created = self.finish_create(response)

        self.assertEqual(created.status_code, 302)
        self.assertEqual(
            ScheduledReport.objects.get(owner=self.owner).definition, definition
        )

    @override_settings(QBE2_SCHEDULED_EMAIL_DOMAIN_ALLOWLIST=("example.com",))
    def test_optional_domain_allowlist_rejects_unapproved_domain(self):
        response = self.begin_create(order_payload())
        created = self.finish_create(response, recipients="person@blocked.test")

        self.assertEqual(created.status_code, 400)
        self.assertContains(created, "not allowed", status_code=400)
        self.assertFalse(ScheduledReport.objects.exists())

    def test_only_owner_can_view_edit_pause_or_delete_schedule(self):
        schedule = self.schedule(owner=self.other)
        self.client.force_login(self.owner)

        for name, method in (
            ("scheduled_detail", "get"),
            ("scheduled_edit", "get"),
            ("scheduled_definition", "get"),
            ("scheduled_delete", "get"),
            ("scheduled_pause", "post"),
            ("scheduled_resume", "post"),
            ("scheduled_delete", "post"),
            ("scheduled_definition_update", "post"),
        ):
            with self.subTest(route=name):
                response = getattr(self.client, method)(
                    reverse(f"django_qbe2:{name}", args=[schedule.pk]),
                    data={"definition": json.dumps(order_payload())},
                )
                self.assertEqual(response.status_code, 404)
        self.assertTrue(ScheduledReport.objects.filter(pk=schedule.pk).exists())

    def test_superuser_does_not_bypass_schedule_ownership(self):
        schedule = self.schedule(owner=self.other)
        self.owner.is_superuser = True
        self.owner.save(update_fields=["is_superuser"])

        response = self.client.get(
            reverse("django_qbe2:scheduled_detail", args=[schedule.pk])
        )

        self.assertEqual(response.status_code, 404)

    def test_owner_can_open_schedule_detail_before_first_run(self):
        schedule = self.schedule()

        response = self.client.get(
            reverse("django_qbe2:scheduled_detail", args=[schedule.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, schedule.name)
        self.assertContains(response, "CSV attachment · 1 recipient")
        self.assertContains(response, "No runs yet.")

    def test_saved_query_sharing_does_not_share_schedule(self):
        query = SavedQuery.objects.create(
            owner=self.other,
            name="Shared orders",
            definition=order_payload(),
            page_size=25,
        )
        query.shared_with.add(self.owner)
        schedule = self.schedule(owner=self.other, name="Private schedule")

        response = self.client.get(reverse("django_qbe2:scheduled_list"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, schedule.name)
        self.assertEqual(
            self.client.get(
                reverse("django_qbe2:scheduled_detail", args=[schedule.pk])
            ).status_code,
            404,
        )

    def test_edit_schedule_keeps_definition_snapshot_and_pause_resume(self):
        schedule = self.schedule()
        original = schedule.definition.copy()
        response = self.client.post(
            reverse("django_qbe2:scheduled_edit", args=[schedule.pk]),
            {
                "schedule_config": "1",
                "name": "Changed schedule",
                "frequency": "daily",
                "weekday": "",
                "local_time": "10:00",
                "timezone": "America/Managua",
                "recipients": "reports@example.com",
                "format": "csv",
                "confirm_recipients": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        schedule.refresh_from_db()
        self.assertEqual(schedule.definition, original)
        self.assertEqual(schedule.name, "Changed schedule")

        self.client.post(reverse("django_qbe2:scheduled_pause", args=[schedule.pk]))
        schedule.refresh_from_db()
        self.assertFalse(schedule.enabled)
        self.client.post(reverse("django_qbe2:scheduled_resume", args=[schedule.pk]))
        schedule.refresh_from_db()
        self.assertTrue(schedule.enabled)
        self.assertGreater(schedule.next_run_at, timezone.now())
