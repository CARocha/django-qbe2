from django.http import HttpResponse
from django.test import Client, TestCase, override_settings
from django.urls import path, reverse

from tests.fixtures import grant_view, make_staff
from tests.models import Order


def protected(request):
    from django_qbe2.access import require_qbe_access, visible_report

    @require_qbe_access
    def handler(request):
        visible_report(request, "tests.order")
        return HttpResponse("Authorized")

    return handler(request)


urlpatterns = [path("protected/", protected)]


@override_settings(ROOT_URLCONF="tests.test_access")
class AccessTests(TestCase):
    def test_staff_is_not_model_permission(self):
        user = make_staff("alice")
        self.client.force_login(user)
        self.assertEqual(self.client.get("/protected/").status_code, 404)
        grant_view(user, Order)
        self.assertEqual(self.client.get("/protected/").content, b"Authorized")
        user.is_staff = False
        user.save()
        self.assertEqual(self.client.get("/protected/").status_code, 403)

    @override_settings(ROOT_URLCONF="tests.urls")
    def test_anonymous_redirects_to_admin_login(self):
        from django.test import RequestFactory

        from django_qbe2.access import require_qbe_access

        request = RequestFactory().get("/qbe/")
        from django.contrib.auth.models import AnonymousUser

        request.user = AnonymousUser()
        response = require_qbe_access(lambda request: HttpResponse())(request)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("admin:login")))

    def test_csrf_is_not_bypassed(self):
        user = make_staff("alice")
        grant_view(user, Order)
        client = Client(enforce_csrf_checks=True)
        client.force_login(user)
        self.assertEqual(client.post("/protected/", {}).status_code, 403)
