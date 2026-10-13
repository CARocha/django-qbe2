import os
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

import django
from django.test import SimpleTestCase


class DistributionTests(SimpleTestCase):
    def test_wheel_resources_and_clean_consumer_install(self):
        root = Path(__file__).resolve().parent.parent
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        environment.pop("DJANGO_SETTINGS_MODULE", None)

        def run(*arguments, cwd):
            result = subprocess.run(
                arguments,
                cwd=cwd,
                env=environment,
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return result.stdout

        with tempfile.TemporaryDirectory(prefix="qbe2-consumer-") as directory:
            temporary = Path(directory)
            artifacts = temporary / "dist"
            run("uv", "build", "--out-dir", str(artifacts), cwd=root)
            wheel = next(artifacts.glob("*.whl"))
            sdist = next(artifacts.glob("*.tar.gz"))
            with zipfile.ZipFile(wheel) as archive:
                wheel_names = archive.namelist()
            with tarfile.open(sdist) as archive:
                source_names = archive.getnames()
            for names in (wheel_names, source_names):
                for asset in (
                    "templates/django_qbe2/builder.html",
                    "static/django_qbe2/builder.js",
                ):
                    self.assertTrue(any(name.endswith(asset) for name in names))
                self.assertFalse(
                    any(
                        set(Path(name).parts) & {"demo", "tests", ".env"}
                        or name.endswith(".sqlite3")
                        for name in names
                    )
                )
            virtualenv = temporary / "venv"
            run(
                "uv", "venv", "--python", sys.executable, str(virtualenv), cwd=temporary
            )
            python = virtualenv / "bin/python"
            run(
                "uv",
                "pip",
                "install",
                "--python",
                str(python),
                str(wheel),
                f"Django=={django.get_version()}",
                cwd=temporary,
            )
            consumer = temporary / "consumer-project"
            consumer.mkdir()
            run(
                str(python),
                "-m",
                "django",
                "startproject",
                "consumer",
                str(consumer),
                cwd=temporary,
            )
            settings_file = consumer / "consumer/settings.py"
            settings_file.write_text(
                settings_file.read_text() + '\nINSTALLED_APPS.append("django_qbe2")\n'
            )
            urls_file = consumer / "consumer/urls.py"
            urls_file.write_text(
                urls_file.read_text()
                + "\nfrom django.urls import include\n"
                + 'urlpatterns.append(path("qbe/", include("django_qbe2.urls")))\n'
            )
            run(str(python), "manage.py", "check", cwd=consumer)
            output = run(
                str(python),
                "-c",
                """
import os, sys
os.environ['DJANGO_SETTINGS_MODULE'] = 'consumer.settings'
import django
django.setup()
import django_qbe2
assert sys.prefix in django_qbe2.__file__
from django.template.loader import get_template
from django.contrib.staticfiles import finders
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory
from django.urls import resolve
assert resolve('/qbe/').view_name == 'django_qbe2:builder'
assert finders.find('django_qbe2/builder.js')
request = RequestFactory().get('/qbe/')
request.user = AnonymousUser()
html = get_template('django_qbe2/builder.html').render(
    {'has_reports': False, 'available_apps': [], 'title': 'Reports'}, request=request)
assert 'No reports available' in html
print('Clean consumer installation and render passed.')
""",
                cwd=consumer,
            )
            self.assertIn("Clean consumer installation and render passed.", output)
