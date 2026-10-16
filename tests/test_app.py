from django.apps import apps
from django.test import TestCase


class AppTests(TestCase):
    def test_setup_performs_no_queries(self):
        from django_qbe2.apps import QBEConfig
        from django_qbe2.models import SavedQuery, ScheduledReport, ScheduledReportRun

        config = apps.get_app_config("django_qbe2")
        self.assertIsInstance(config, QBEConfig)
        with self.assertNumQueries(0):
            config.ready()
        self.assertEqual(
            list(config.get_models()), [SavedQuery, ScheduledReport, ScheduledReportRun]
        )
