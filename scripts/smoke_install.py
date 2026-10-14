"""Install from the selected public index in a fresh external Django consumer."""

import argparse
import os
import subprocess
import sys
import tempfile
import tomllib
from importlib.metadata import version as installed_version
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", choices=("testpypi", "pypi"), required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    release = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    environment = os.environ.copy()
    environment.pop("DJANGO_SETTINGS_MODULE", None)
    environment.pop("PYTHONPATH", None)

    def run(*command: str, cwd: Path) -> None:
        subprocess.run(command, cwd=cwd, env=environment, check=True, timeout=120)

    with tempfile.TemporaryDirectory(prefix="qbe2-index-consumer-") as directory:
        temporary = Path(directory)
        venv = temporary / "venv"
        run("uv", "venv", "--python", sys.executable, str(venv), cwd=temporary)
        python = str(venv / "bin/python")
        run(
            "uv",
            "pip",
            "install",
            "--python",
            python,
            f"Django=={installed_version('Django')}",
            cwd=temporary,
        )
        host = "test.pypi.org" if args.index == "testpypi" else "pypi.org"
        run(
            "uv",
            "pip",
            "install",
            "--python",
            python,
            "--no-deps",
            "--index-url",
            f"https://{host}/simple/",
            f"django-qbe2=={release}",
            cwd=temporary,
        )
        consumer = temporary / "consumer-project"
        consumer.mkdir()
        run(
            python,
            "-m",
            "django",
            "startproject",
            "consumer",
            str(consumer),
            cwd=temporary,
        )
        settings = consumer / "consumer/settings.py"
        settings.write_text(
            settings.read_text()
            + '\nINSTALLED_APPS.append("django_qbe2")\nALLOWED_HOSTS = ["testserver"]\n'
        )
        urls = consumer / "consumer/urls.py"
        urls.write_text(
            urls.read_text()
            + "\nfrom django.urls import include\n"
            + 'urlpatterns.append(path("qbe/", include("django_qbe2.urls")))\n'
        )
        run(python, "manage.py", "check", cwd=consumer)
        run(python, "manage.py", "migrate", "--noinput", cwd=consumer)
        run(
            python,
            "-c",
            """
import os, sys
from pathlib import Path
os.environ['DJANGO_SETTINGS_MODULE'] = 'consumer.settings'
import django
django.setup()
import django_qbe2
assert Path(django_qbe2.__file__).is_relative_to(Path(sys.prefix))
from django.contrib.auth.models import User
from django.contrib.staticfiles import finders
from django.test import Client
user = User.objects.create_user('qbe2_smoke', is_staff=True)
client = Client()
client.force_login(user)
response = client.get('/qbe/')
assert response.status_code == 200, response.content
assert b'No reports available' in response.content
assert finders.find('django_qbe2/builder.js')
print('Published package installation, Django checks, templates and assets passed.')
""",
            cwd=consumer,
        )


if __name__ == "__main__":
    main()
