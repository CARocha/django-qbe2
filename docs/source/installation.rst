Install in your project
=======================

Requirements
------------

Supported environments are Python 3.13 and 3.14 with Django 6.0 and 6.1. Every
combination is exercised on SQLite and PostgreSQL. Use the latest patch release
of your Python and Django series. Other versions and databases are not part of
the current compatibility promise. Django is the only runtime dependency;
Sphinx, Ruff and database test drivers are development tools.

Install the alpha
-----------------

The current alpha candidate is ``0.1.0a9``. Check its availability on PyPI before
installing it in your host project's virtual environment:

.. code-block:: console

   python -m pip install django-qbe2==0.1.0a9

The explicit version opts into the alpha. You do not need to upgrade a host project
from Django 6.0 to 6.1 to use this release. Version 0.1.0a1 supported only Python
3.14/Django 6.1; Python 3.13/Django 6.0 consumers need 0.1.0a2 or later.

From the source checkout, you can always build and install a local wheel:

.. code-block:: console

   uv build

In your host project's environment, install that wheel using its absolute path:

.. code-block:: console

   python -m pip install /absolute/path/to/django-qbe2/dist/django_qbe2-0.1.0a9-py3-none-any.whl

The distribution name is ``django-qbe2``; the import and app name is
``django_qbe2``. The wheel contains namespaced templates and static assets. It
contains neither the demo database nor the host project's settings.

Excel export is optional. Install the extra in the host project's environment to
show the **Export Excel** button alongside CSV:

.. code-block:: console

   python -m pip install 'django-qbe2[excel]'

Without this extra, Django QBE 2 continues to provide CSV exports and does not
import ``openpyxl`` at runtime.

Configure Django
----------------

Keep Django Admin, auth, contenttypes, sessions, messages and staticfiles in your
existing ``INSTALLED_APPS``, and append the reporting app:

.. code-block:: python

   INSTALLED_APPS += ["django_qbe2"]

Keep your existing admin route and other routes, then append to your root URLconf:

.. code-block:: python

   from django.urls import include, path

   urlpatterns += [path("qbe/", include("django_qbe2.urls"))]

Retain the standard session, authentication, messages and CSRF middleware.
Templates need ``APP_DIRS=True`` and the standard request/auth/messages context
processors used by Django Admin. The initial implementation uses the default
``admin.site`` for its login and context; it does not automatically adopt a custom
AdminSite.

From the ``0.1.0a4`` candidate, QBE includes migrations for saved queries and their
recipient relationships, using your ``AUTH_USER_MODEL``. Apply them with
``manage.py migrate`` when upgrading; earlier alphas have no QBE tables.
Your host project's auth, sessions and business apps still need their normal migrations. In production,
serve the packaged static files through your existing Django static-file setup:

.. code-block:: console

   python manage.py check
   python manage.py migrate
   python manage.py collectstatic

Register your models
--------------------

The catalog starts empty. For a new installed app called ``sales``, example models
are shown below. If your application already has equivalent models, use those
instead of replacing them.

.. literalinclude:: examples/models.py
   :language: python
   :caption: sales/models.py

Put the report declarations in ``sales/qbe.py``. The app discovers ``qbe.py``
modules at startup without fetching report data:

.. literalinclude:: examples/qbe.py
   :language: python
   :caption: sales/qbe.py

Ensure ``sales`` is installed, create/apply its migrations if these are new models,
and give authorized users active staff status plus ``sales.view_order`` and
``sales.view_customer`` permissions. Registering a related target is mandatory.
Read :doc:`reports` for the policy contract before adapting this example.

.. note::

   These exact model and report files are installed into a temporary external
   Django consumer by the package test suite. The test checks the wheel outside
   the checkout with a UUID custom user, applies migrations, and verifies report
   HTML/CSV and shared saved queries preserve the executing user's row policy.

Run ``manage.py check`` after changing report configuration. Invalid field paths,
unsupported relations and missing target registrations are reported by system checks.
