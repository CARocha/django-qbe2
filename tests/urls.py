from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("qbe/", include("django_qbe2.urls")),
]
