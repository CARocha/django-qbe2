from django.urls import path

from django_qbe2 import views

app_name = "django_qbe2"
urlpatterns = [
    path("", views.builder_view, name="builder"),
    path("results/", views.results_view, name="results"),
    path("export/", views.export_view, name="export"),
]
