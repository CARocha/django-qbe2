import os
import runpy
from pathlib import Path
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase


class SettingsSelectionTests(SimpleTestCase):
    def test_unknown_backend_fails_instead_of_falling_back(self):
        with patch.dict(
            os.environ, {"QBE2_TEST_DB": "unknown", "DJANGO_DEBUG": "true"}
        ):
            for path in (
                Path(__file__).with_name("settings.py"),
                Path(__file__).resolve().parent.parent / "demo/config/settings.py",
            ):
                with (
                    self.subTest(path=path),
                    self.assertRaisesRegex(
                        ImproperlyConfigured, "QBE2_TEST_DB must be sqlite or postgres"
                    ),
                ):
                    runpy.run_path(str(path))
