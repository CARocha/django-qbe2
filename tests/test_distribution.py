import os
import shutil
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
                    "aggregation.py",
                    "summary_forms.py",
                    "templates/django_qbe2/builder.html",
                    "templates/django_qbe2/saved_list.html",
                    "migrations/0001_initial.py",
                    "migrations/0002_scheduledreport_scheduledreportrun_and_more.py",
                    "static/django_qbe2/builder.js",
                    "scheduled_execution.py",
                    "scheduled_exports.py",
                    "templates/django_qbe2/scheduled_list.html",
                    "static/django_qbe2/qbe.css",
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
            run(str(python), "manage.py", "startapp", "sales", cwd=consumer)
            run(str(python), "manage.py", "startapp", "accounts", cwd=consumer)
            (consumer / "accounts/models.py").write_text(
                "from uuid import uuid4\n"
                "from django.contrib.auth.models import AbstractUser\n"
                "from django.db import models\n\n"
                "class User(AbstractUser):\n"
                "    id = models.UUIDField(primary_key=True, default=uuid4)\n"
            )
            settings_file = consumer / "consumer/settings.py"
            settings_file.write_text(
                settings_file.read_text()
                + '\nINSTALLED_APPS += ["accounts", "sales", "django_qbe2"]\n'
                + 'AUTH_USER_MODEL = "accounts.User"\n'
                + 'ALLOWED_HOSTS = ["testserver"]\n'
            )
            for filename in ("models.py", "qbe.py"):
                shutil.copy2(
                    root / "docs/source/examples" / filename,
                    consumer / "sales" / filename,
                )
            urls_file = consumer / "consumer/urls.py"
            urls_file.write_text(
                urls_file.read_text()
                + "\nfrom django.urls import include\n"
                + 'urlpatterns.append(path("qbe/", include("django_qbe2.urls")))\n'
            )
            run(str(python), "manage.py", "check", cwd=consumer)
            run(
                str(python),
                "manage.py",
                "makemigrations",
                "accounts",
                "sales",
                cwd=consumer,
            )
            run(str(python), "manage.py", "migrate", "--noinput", cwd=consumer)
            output = run(
                str(python),
                "-c",
                """
import os, sys
import csv, io, json
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
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from uuid import UUID
User = get_user_model()
from django.test import Client
from sales.models import Customer, Order
alice = User.objects.create_user('alice', is_staff=True)
bob = User.objects.create_user('bob', is_staff=True)
assert isinstance(alice.pk, UUID)
alice.user_permissions.add(*Permission.objects.filter(
    content_type__app_label='sales', codename__in=['view_customer', 'view_order']))
own_customer = Customer.objects.create(owner=alice, name='Alice customer')
other_customer = Customer.objects.create(owner=bob, name='Bob customer')
Order.objects.create(owner=alice, customer=own_customer, number='A100', total='100.01')
Order.objects.create(
    owner=alice, customer=other_customer, number='Hidden', total='150.00')
Order.objects.create(owner=bob, customer=other_customer, number='B200', total='200.00')
Order.objects.create(owner=bob, customer=None, number='B201', total='201.00')
client = Client()
assert client.get('/qbe/').status_code == 302
client.force_login(alice)
assert client.get('/qbe/?report=sales.order').status_code == 200
definition = {
    'version': 1, 'report': 'sales.order',
    'columns': ['number', 'customer__name', 'total', 'status'],
    'filters': [{'field': 'total', 'operator': 'gte', 'value': '100.00'}],
    'ordering': [{'field': 'number', 'direction': 'asc'}],
}
data = {'definition': json.dumps(definition)}
result = client.post('/qbe/results/', data)
assert result.status_code == 200, result.content
assert b'A100' in result.content and b'Alice customer' in result.content
assert b'Hidden' not in result.content and b'Bob customer' not in result.content
assert b'>Open</td>' in result.content
export = client.post('/qbe/export/', data)
assert export.status_code == 200
rows = list(csv.reader(io.StringIO(b''.join(export.streaming_content).decode())))
assert rows[1:] == [['A100', 'Alice customer', '100.01', 'open']], rows
export.close()
print('Documented consumer report policies, HTML and CSV passed.')
grouped = {key: value for key, value in definition.items() if key != 'filters'}
grouped.update(version=2, where={
    'connector': 'and', 'negated': False, 'children': [
        {'connector': 'or', 'negated': False, 'children': [
            {'field': 'total', 'operator': 'gte', 'value': '0.00'},
            {'field': 'number', 'operator': 'exact', 'value': 'Hidden'},
        ]},
        {'connector': 'and', 'negated': True, 'children': [
            {'field': 'number', 'operator': 'exact', 'value': 'B200'},
        ]},
    ],
})
grouped_data = {'definition': json.dumps(grouped)}
grouped_result = client.post('/qbe/results/', grouped_data)
assert grouped_result.status_code == 200, grouped_result.content
assert b'>A100</td>' in grouped_result.content
assert b'>Hidden</td>' not in grouped_result.content
assert b'>B200</td>' not in grouped_result.content
print('Installed wheel condition groups retain root and related scopes.')
summary = {
    'version': 3, 'report': 'sales.order',
    'where': {'connector': 'and', 'negated': False, 'children': []},
    'group_by': [],
    'metrics': [
        {'id': 'm1', 'function': 'count', 'field': None},
        {'id': 'm2', 'function': 'sum', 'field': 'total'},
    ],
    'ordering': [],
}
summary_result = client.post('/qbe/results/', {'definition': json.dumps(summary)})
assert summary_result.status_code == 200, summary_result.content
assert (
    b'2 source records' in summary_result.content
    and b'250.01' in summary_result.content
)
grouped_summary = {**summary, 'group_by': ['status'], 'ordering': [
    {'type': 'group', 'field': 'status', 'direction': 'asc'}]}
grouped_result = client.post(
    '/qbe/results/', {'definition': json.dumps(grouped_summary)})
assert grouped_result.status_code == 200, grouped_result.content
assert b'1 group' in grouped_result.content and b'250.01' in grouped_result.content
summary_export = client.post(
    '/qbe/export/', {'definition': json.dumps(grouped_summary)})
assert summary_export.status_code == 200 and summary_export.streaming
summary_rows = list(csv.reader(io.StringIO(
    b''.join(summary_export.streaming_content).decode())))
assert summary_rows[1] == ['open', '2', '250.01'], summary_rows
summary_export.close()
print('Installed wheel ungrouped/grouped summaries and summary CSV passed.')

from django_qbe2.models import SavedQuery
saved = client.post('/qbe/saved/create/', {
    **data, 'name': 'Shared order definition', 'shared_with': 'bob', 'page_size': '25'})
assert saved.status_code == 302, saved.content
query = SavedQuery.objects.get(owner=alice)
assert query.definition == definition
assert query.page_size == 25
bob.user_permissions.add(*Permission.objects.filter(
    content_type__app_label='sales', codename__in=['view_customer', 'view_order']))
client.force_login(bob)
assert client.get(f'/qbe/saved/{query.pk}/').status_code == 200
result = client.post('/qbe/results/', {**data, 'saved_query': str(query.pk)})
assert result.status_code == 200, result.content
assert b'B200' in result.content and b'A100' not in result.content
assert client.post(f'/qbe/saved/{query.pk}/update/', {
    **data, 'name': 'Unauthorized overwrite'}).status_code == 404
assert client.post('/qbe/saved/create/', {
    **data, 'name': 'My copy'}).status_code == 302
copy = SavedQuery.objects.get(owner=bob)
assert copy.pk != query.pk and not copy.shared_with.exists()
print('Custom-user migration, shared definitions, scoped execution and copy passed.')

from datetime import time, timedelta
from unittest.mock import patch
from django.core.management import call_command
from django.utils import timezone
from django_qbe2.models import ScheduledReport, ScheduledReportRun
schedule = ScheduledReport.objects.create(
    owner=alice, name='Daily orders', definition=definition, page_size=25,
    frequency='daily', weekday=None, local_time=time(9), timezone='UTC',
    recipients=['reports@example.com'], format='csv',
    next_run_at=timezone.now() - timedelta(hours=1))
with patch('django_qbe2.scheduled_exports.send_scheduled_report', return_value=1):
    call_command('qbe2_run_scheduled_reports', limit=5, stdout=io.StringIO())
run = ScheduledReportRun.objects.get(schedule=schedule)
assert run.status == ScheduledReportRun.Status.SUCCEEDED
assert run.attempts == 1
print('Installed wheel scheduled report command passed.')
""",
                cwd=consumer,
            )
            self.assertIn("Clean consumer installation and render passed.", output)
            self.assertIn(
                "Documented consumer report policies, HTML and CSV passed.", output
            )
            self.assertIn(
                "Installed wheel ungrouped/grouped summaries and summary CSV passed.",
                output,
            )
            self.assertIn(
                "Installed wheel scheduled report command passed.",
                output,
            )
