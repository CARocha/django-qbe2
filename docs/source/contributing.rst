Contributing and documentation
==============================

Read ``AGENTS.md`` for project boundaries and verification commands. Use English
for code, comments, commits, UI text and public documentation. Start each
significant feature from ``main`` in its own branch. Add meaningful tests before
changing behavior and review the diff before integration.

Install development tools
-------------------------

.. code-block:: console

   uv sync --python 3.14 --frozen --group dev --group docs
   uv run ruff check .
   uv run ruff format --check .
   uv run python -m django test tests --settings=tests.settings -v 2
   uv run python demo/manage.py test demo.reports -v 2
   uv run python demo/manage.py check
   uv run python demo/manage.py makemigrations --check --dry-run
   uv audit --locked --preview-features audit-command
   uv build

The external-wheel test installs a real consumer outside the checkout, copies the
documented model/report examples, and verifies authorized HTML and CSV. Keep those
examples aligned with the app contract. The wheel/sdist omit the demo, test data,
local credentials and development tools.

Compatibility matrix
--------------------

CI runs Python 3.13 and 3.14 with Django 6.0 and 6.1 on both databases. The frozen
lock is the default development/build environment, not a replacement for the
matrix. Use ``--with`` to select another Django series without rewriting the lock:

.. code-block:: console

   uv run --frozen --python 3.13 --group dev --with 'Django==6.0.*' python -m django test tests --settings=tests.settings -v 2
   uv run --frozen --python 3.13 --group dev --with 'Django==6.0.*' python demo/manage.py test demo.reports -v 2

Repeat both commands for Python 3.13/Django 6.1, Python 3.14/Django 6.0 and
Python 3.14/Django 6.1 to cover the remaining three combinations. The external
wheel consumer uses the same interpreter and Django patch version as each test
runner. Release verification also installs from each index in all four runtimes.
Keep Ruff's target at Python 3.13 so generated formatting remains importable there.

PostgreSQL tests
----------------

Use an isolated instance and a role with CREATEDB. Django creates and removes
``test_<PGDATABASE>``; never point tests at production or a user's existing database.

.. code-block:: console

   export QBE2_TEST_DB=postgres
   export PGHOST=127.0.0.1
   export PGPORT=55432
   export PGDATABASE=qbe2_tests
   export PGUSER=qbe2_test
   uv run python -m django test tests --settings=tests.settings -v 2
   uv run python demo/manage.py test demo.reports -v 2

Set ``PGPASSWORD`` outside version control only if your test instance requires it.
The SQLite job skips only the PostgreSQL statement-cancellation test. PostgreSQL
must run it. Streaming tests consume a real row, assert a live cursor and verify
closure and restored timeouts after disconnects and late failures.

CI uses a disposable PostgreSQL 18 container bound to runner loopback, trust
authentication and synthetic data. This allows fork PR testing without repository
secrets; it is not a production authentication configuration.

Build the documentation
-----------------------

Sources are in ``docs/source/`` as reStructuredText; no Django settings or database
are needed to build them. Sphinx lives in the separate ``docs`` dependency group.

.. code-block:: console

   uv run --group docs sphinx-build -n -W -b html docs/source docs/_build/html
   uv run --group docs sphinx-build -n -W -b text docs/source docs/_build/text
   python -m http.server 8001 --bind 127.0.0.1 --directory docs/_build/html

Open ``http://127.0.0.1:8001/``. ``-n -W`` rejects missing references and warnings;
CI uses the same strict commands. Plain-text output supports offline reading and
agents. Do not commit generated output. Link-check external references with:

.. code-block:: console

   uv run --group docs sphinx-build -W -b linkcheck docs/source docs/_build/linkcheck

A transient external site failure needs investigation rather than a warning
suppression. GitHub Pages publication is a separate maintainer action; see
:doc:`releases`.

Browser checks
--------------

Run the demo and choose your own synthetic-user password. Check report/column
selection, typed conditions, row addition/deletion, ordering, pagination, editing,
CSV across pages and users without permissions. Verify keyboard focus, 375px and
desktop layouts, light/dark themes and the console. Wide result tables must scroll
inside their container instead of widening the entire page.

Keep local state out of Git
---------------------------

Only public code, tests, documentation, synthetic demo fixtures and reproducible
tooling belong in commits. Keep personal plans, transcripts, tool state, secrets,
local databases, caches and build output ignored. ``AGENTS.md`` contains shared
contributor instructions, not a record of one person's chat session.
