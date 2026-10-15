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
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--index", choices=("testpypi", "pypi"))
    source.add_argument("--wheel", type=Path)
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
        if args.wheel:
            install_args = [str(args.wheel.resolve())]
        else:
            host = "test.pypi.org" if args.index == "testpypi" else "pypi.org"
            install_args = [
                "--index-url",
                f"https://{host}/simple/",
                f"django-qbe2=={release}",
            ]
        run(
            "uv",
            "pip",
            "install",
            "--python",
            python,
            "--no-deps",
            *install_args,
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
        run(python, "manage.py", "startapp", "sales", cwd=consumer)
        for filename in ("models.py", "qbe.py"):
            (consumer / "sales" / filename).write_text(
                (root / "docs/source/examples" / filename).read_text()
            )
        settings.write_text(
            settings.read_text()
            + '\nINSTALLED_APPS += ["sales", "django_qbe2"]\n'
            + 'ALLOWED_HOSTS = ["testserver"]\n'
        )
        urls = consumer / "consumer/urls.py"
        urls.write_text(
            urls.read_text()
            + "\nfrom django.urls import include\n"
            + 'urlpatterns.append(path("qbe/", include("django_qbe2.urls")))\n'
        )
        run(python, "manage.py", "check", cwd=consumer)
        run(python, "manage.py", "makemigrations", "sales", cwd=consumer)
        run(python, "manage.py", "migrate", "--noinput", cwd=consumer)
        run(
            python,
            "-c",
            """
import os, sys
from pathlib import Path
import json
os.environ['DJANGO_SETTINGS_MODULE'] = 'consumer.settings'
import django
django.setup()
import django_qbe2
assert Path(django_qbe2.__file__).is_relative_to(Path(sys.prefix))
from django.contrib.auth.models import User
from django.contrib.auth.models import Permission
from django.test import Client
from django.contrib.staticfiles import finders
user = User.objects.create_user('qbe2_smoke', is_staff=True)
client = Client()
client.force_login(user)
response = client.get('/qbe/')
assert response.status_code == 200, response.content
assert b'No reports available' in response.content
assert finders.find('django_qbe2/builder.js')
print('Published package installation, Django checks, templates and assets passed.')
from decimal import Decimal
from sales.models import Customer, Order
user = User.objects.create_user('summary-user', is_staff=True)
user.user_permissions.add(*Permission.objects.filter(
    content_type__app_label='sales', codename__in=['view_order', 'view_customer']))
customer = Customer.objects.create(owner=user, name='Summary customer')
Order.objects.create(owner=user, customer=customer, number='S100', total='12.30')
Order.objects.create(owner=user, customer=customer, number='S200', total='7.70')
client.force_login(user)
base = {
    'version': 3, 'report': 'sales.order',
    'where': {'connector': 'and', 'negated': False, 'children': []},
    'group_by': [],
    'metrics': [
        {'id': 'm1', 'function': 'count', 'field': None},
        {'id': 'm2', 'function': 'sum', 'field': 'total'},
    ],
    'ordering': [],
}
summary = client.post('/qbe/results/', {'definition': json.dumps(base)})
assert summary.status_code == 200, summary.content
assert b'2 source records' in summary.content and b'20.00' in summary.content
assert b'Export CSV' in summary.content and b'Export Excel' not in summary.content
grouped = {**base, 'group_by': ['status'], 'ordering': [
    {'type': 'group', 'field': 'status', 'direction': 'asc'}]}
grouped_result = client.post('/qbe/results/', {'definition': json.dumps(grouped)})
assert grouped_result.status_code == 200, grouped_result.content
assert b'1 group' in grouped_result.content and b'20.00' in grouped_result.content
print('Installed wheel ungrouped and grouped v3 summaries passed.')
""",
            cwd=consumer,
        )


if __name__ == "__main__":
    main()
