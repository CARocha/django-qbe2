from importlib import import_module

from django.apps import AppConfig
from django.utils.module_loading import autodiscover_modules


class QBEConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "django_qbe2"
    verbose_name = "Query by Example"

    def ready(self):
        import_module("django_qbe2.checks")
        autodiscover_modules("qbe")
