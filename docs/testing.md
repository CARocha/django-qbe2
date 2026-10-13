# Testing and contributing

Read `AGENTS.md`, then `tasks/todo.md` and the current task in `tasks/plan.md`.
Use English for code, comments and public documentation. Start important features
from local main in their own branch. Add meaningful tests before behavior changes.

## Local checks

```sh
uv sync --python 3.14 --frozen --group dev
uv run python -m django test tests --settings=tests.settings -v 2
uv run python demo/manage.py test demo.reports -v 2
uv run python demo/manage.py check
uv run python demo/manage.py makemigrations --check --dry-run
uv run ruff check .
uv run ruff format --check .
uv audit --locked --preview-features audit-command
uv build
```

SQLite is the default. The PostgreSQL cancellation test is intentionally skipped
in the SQLite job and must pass in the PostgreSQL job. No other skips are expected.
Streaming tests consume a real data row before closing the response. PostgreSQL
checks assert an active cursor first, then no remaining cursor and a restored
statement timeout. A late database timeout must propagate without HTML in the CSV
and leave the connection usable; SQLite exercises a late application exception.

## PostgreSQL

Use an isolated test instance, never a production database. Django creates and
removes `test_<PGDATABASE>` during its test run. The selected role needs CREATEDB.

```sh
export QBE2_TEST_DB=postgres
export PGHOST=127.0.0.1
export PGPORT=55432
export PGDATABASE=qbe2_tests
export PGUSER=qbe2_test
# Set PGPASSWORD only if your isolated instance requires it; never commit it.
uv run python -m django test tests --settings=tests.settings -v 2
uv run python demo/manage.py test demo.reports -v 2
```

CI uses a disposable PostgreSQL18 container bound to runner loopback. It contains
only synthetic data and uses trust authentication so fork PRs do not need repository
secrets. This is a test-only choice, not a production database configuration.
Actions are pinned to verified release commits and checkout does not persist tokens.
The pinned uv version supports its experimental native audit command; CI opts into
that feature explicitly and fails on reported vulnerabilities without ignore rules.

## Browser verification

Run the demo, set a password yourself for a synthetic account, and open `/qbe/`.
Check selecting a report/columns, typed filters, adding/removing rows, ordering,
pagination, editing, CSV across all pages, errors and an account without permissions.
Check keyboard focus, 375px/desktop layouts, clear/dark modes and the console.
Wide result tables should scroll inside their container, not widen the page.

CI configuration is checked locally. A remote CI success is only recorded after
an authorized push and an actual successful GitHub Actions run.
