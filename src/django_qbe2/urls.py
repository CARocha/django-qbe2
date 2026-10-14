from django.urls import path

from django_qbe2 import saved_views, views

app_name = "django_qbe2"
urlpatterns = [
    path("", views.builder_view, name="builder"),
    path("results/", views.results_view, name="results"),
    path("export/", views.export_view, name="export"),
    path("saved/", saved_views.list_view, name="saved_list"),
    path("saved/create/", saved_views.create_view, name="saved_create"),
    path("saved/<uuid:pk>/", saved_views.open_view, name="saved_open"),
    path("saved/<uuid:pk>/update/", saved_views.update_view, name="saved_update"),
    path("saved/<uuid:pk>/settings/", saved_views.settings_view, name="saved_settings"),
    path("saved/<uuid:pk>/delete/", saved_views.delete_view, name="saved_delete"),
]
