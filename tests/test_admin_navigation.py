from django.contrib import admin
from django.test import TestCase, override_settings
from django.urls import include, path, reverse

from django_qbe2.models import SavedQuery
from tests.fixtures import make_staff

urlpatterns = [
    path("petAdmon27/", admin.site.urls),
    path("qbe2/", include("django_qbe2.urls")),
]


class AdminNavigationTests(TestCase):
    def setUp(self):
        self.user = make_staff("reader")
        self.client.force_login(self.user)

    def test_staff_sees_qbe_entry_without_extra_model_permissions(self):
        response = self.client.get(reverse("admin:index"))
        self.assertContains(response, "Django QBE 2")
        self.assertContains(
            response, reverse("admin:django_qbe2_savedquery_changelist")
        )
        response = self.client.get(reverse("admin:django_qbe2_savedquery_changelist"))
        self.assertRedirects(response, reverse("django_qbe2:saved_list"))

    def test_admin_does_not_offer_raw_storage_routes(self):
        self.assertTrue(admin.site.is_registered(SavedQuery))
        for suffix in (
            "add/",
            "00000000-0000-0000-0000-000000000001/change/",
            "00000000-0000-0000-0000-000000000001/delete/",
            "00000000-0000-0000-0000-000000000001/history/",
        ):
            base = reverse("admin:django_qbe2_savedquery_changelist")
            response = self.client.get(base + suffix)
            self.assertEqual(response.status_code, 404)

    def test_admin_entry_keeps_private_queries_private_for_superusers(self):
        other = make_staff("other")
        SavedQuery.objects.create(
            owner=other, name="Private marker", definition={}, page_size=50
        )
        self.user.is_superuser = True
        self.user.save()
        response = self.client.get(
            reverse("admin:django_qbe2_savedquery_changelist"), follow=True
        )
        self.assertNotContains(response, "Private marker")

    def test_anonymous_admin_entry_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("admin:django_qbe2_savedquery_changelist"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("admin:login")))

    @override_settings(ROOT_URLCONF="tests.test_admin_navigation")
    def test_navigation_respects_consumer_url_prefixes(self):
        target = reverse("admin:django_qbe2_savedquery_changelist")
        self.assertTrue(target.startswith("/petAdmon27/"))
        self.assertRedirects(self.client.get(target), "/qbe2/saved/")
