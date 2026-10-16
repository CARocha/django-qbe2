from django.urls import path

from django_qbe2 import saved_views, scheduled_views, views

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
    path("scheduled/", scheduled_views.list_view, name="scheduled_list"),
    path("scheduled/create/", scheduled_views.create_view, name="scheduled_create"),
    path(
        "scheduled/<uuid:pk>/",
        scheduled_views.detail_view,
        name="scheduled_detail",
    ),
    path(
        "scheduled/<uuid:pk>/edit/",
        scheduled_views.edit_view,
        name="scheduled_edit",
    ),
    path(
        "scheduled/<uuid:pk>/definition/",
        scheduled_views.definition_view,
        name="scheduled_definition",
    ),
    path(
        "scheduled/<uuid:pk>/definition/update/",
        scheduled_views.update_definition_view,
        name="scheduled_definition_update",
    ),
    path(
        "scheduled/<uuid:pk>/pause/",
        scheduled_views.pause_view,
        name="scheduled_pause",
    ),
    path(
        "scheduled/<uuid:pk>/resume/",
        scheduled_views.resume_view,
        name="scheduled_resume",
    ),
    path(
        "scheduled/<uuid:pk>/delete/",
        scheduled_views.delete_view,
        name="scheduled_delete",
    ),
]
