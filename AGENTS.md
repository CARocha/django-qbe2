# Contributor and agent instructions

## Start here

Django QBE 2 is an experimental reusable reporting app for Python 3.13–3.14 and
Django 6.0–6.1. Read README.md for setup, docs/source/index.rst for the public
documentation, and CHANGELOG.md for the current scope. Check Git status and recent
commits before editing. Do not repeat completed work or overwrite another contributor's changes.

## Scope and architecture

- src/django_qbe2/ is the installable app; demo/ is a separate consumer;
  tests/ verifies the contract; docs/source/ contains the Sphinx sources.
- The current app supports explicit registration, selected columns, typed AND/OR/NOT
  condition groups, authorized Count/Sum/Average summaries, and up to two
  ForeignKey/OneToOne/ManyToMany relationship hops in either direction. Multi-valued
  paths support selected columns and existential filters with bounded one-row-per-root
  values, stable pagination and CSV.
- Declared model choices drive equality selectors and HTML labels. CSV, filters
  and ordering retain stored codes. Only equality validates membership; fragments
  and range thresholds may use values outside the choices. Preserve zero, false,
  empty-string options, null distinction, historical codes and request-local labels.
  Evaluate callable choices only for authorized catalog fields, never in checks.
- SavedQuery stores bounded JSON definitions and a page size, with swappable user
  ownership and explicit reader/copy recipients. Owner-only modifications apply
  even to superusers. Fresh catalog validation and executing-user row policies
  remain mandatory. Never store result rows or grant model permissions by sharing.
- ScheduledReport stores an owner-only independent definition snapshot and recurrence;
  every run reloads the active staff owner, rebuilds the authorized catalog and uses
  that owner's current row policies. Deliver bounded complete CSV/optional Excel
  only through the configured Django mailer, BCC recipients, and never persist rows
  or attachment contents. A permission loss disables the schedule. Database leases,
  unique occurrence records and bounded retries must remain safe on SQLite/PostgreSQL.
- Apply the package migration for saved queries; default database only. Preserve
  UUID custom user support. Definition updates preserve recipients; the settings
  route changes sharing explicitly. Public priorities live in docs/source/roadmap.rst.
- Default Admin registers SavedQuery only as navigation to the authorized QBE
  list. Never expose raw add/change/delete/history model routes or JSON editing;
  adding navigation must not bypass ownership or sharing policies.
- Generic relations, arbitrary SQL, visual diagrams, multiple databases and
  ASGI-native streaming need separate work.
- Runtime dependency is Django only. Documentation tools belong to the docs group,
  and test/lint tools belong to the dev group. Locked build/publishing tools belong
  to the release group; they are not runtime dependencies.
- Follow https://docs.djangoproject.com/en/6.1/intro/reusable-apps/ and public Django
  APIs. Namespace URLs, templates and assets under django_qbe2. Include the assets
  in the wheel and sdist. The app must not depend on the demo or import test models.

## Language and implementation

Write code, identifiers, comments, docstrings, commits, UI text and documentation
in English. Keep modules small and use typed public interfaces. Record technical
contracts in the public documentation rather than transcripts or session notes.
Do not add speculative abstractions or request-specific shared mutable state.

## Data access and input boundaries

- Nothing is available until a developer explicitly registers a report and fields.
- Require active authenticated staff and model view permissions. Each Report must
  define get_queryset(request), including related targets. Staff status alone does
  not authorize rows, and a superuser still follows the report's row policy.
- Use the same scope for columns, filters, ordering, results and CSV. Server-side
  authorization is mandatory even when a control is hidden in the browser.
- Validate unchanged JSON v1 and strict v2 condition trees, permitted paths/operators,
  typed values and positive limits. OR/NOT never includes root or related row policies.
- Never use eval, pickle or arbitrary client SQL. Do not commit real data or secrets.
- Default budgets: 50 rows/page (maximum 200), 20 columns, 20 filters, 3 sort keys,
  10 condition groups and three condition levels including the root, 3 summary
  group fields, 10 metrics, 10,000 summary source rows and output rows, and 10,000
  related values per result page or complete export; PostgreSQL report statements
  time out after 5 seconds.
- Scheduled reports default to 10 BCC recipients and 10 MiB per attachment; keep
  recipient and byte limits configurable and reject partial results.
- Escape text formulas in CSV and preserve numeric precision. Streaming targets
  synchronous WSGI; late failures abort the download and must release resources.

Group forms use bounded identifiers and parent links; reject cycles, disconnected nodes
and unknown assignments. Only the unnegated AND root may be empty on execution.
Add controls through server actions without executing reports; retain no-JavaScript
operation. Existing saved definitions need no new migration for groups or summaries.

Multi-valued filters use correlated existential predicates at the root level. Every
related report needs view permission and its own request queryset policy. A path may
contain at most one multi-valued edge. Multi-valued paths cannot be ordered, grouped
or used as numeric summary metrics. Saved definition versions remain v1-v3.

Summary v3 definitions contain exactly report, where, group_by, metrics and ordering
plus version. Count uses no field; Sum/Average accept registered integer/decimal
fields. Build a distinct authorized root-PK source before calculating aggregates.
Never return partial totals when the source cap is exceeded. Apply the output cap
only after complete calculations and deterministic ordering. Preserve exact Decimal
sums (scaled integer aggregation on SQLite when safe, numeric Sum on PostgreSQL) and
half-even Average rounding. Saved and shared v3 definitions always revalidate and
  execute with the current user's policies.

## Workflow

Create a feature branch from main for every significant change. Commit small,
verified increments. Review and run the full relevant suite before merging into
main. Retain feature branches when requested by the maintainer. Do not force-push,
rewrite shared history, publish packages or create releases without authorization.
Never weaken checks, suppress warnings or skip failing tests to obtain a green run.

Keep personal plans, transcripts and local tool state out of Git. Root .gitignore
covers .superpowers/, tasks/ and docs/superpowers/. Only public documentation belongs
under docs/source/. Generated HTML belongs under docs/_build/ and is not committed.

## Verification

Write meaningful tests before changing behavior; reproduce bugs before fixing them.
Use unit tests for pure logic and Django/database integration tests for permissions,
relations, HTTP, CSRF and streaming. Do not add tests that merely mirror prose or
configuration. Verify UI changes in a real browser. Document observed limitations.

Run from the repository root:

```sh
uv sync --python 3.14 --frozen --group dev --group docs
uv run python -m django test tests --settings=tests.settings -v 2
uv run python demo/manage.py test demo.reports -v 2
uv run python demo/manage.py check
uv run python demo/manage.py makemigrations --check --dry-run
uv run ruff check .
uv run ruff format --check .
uv run --group docs sphinx-build -n -W -b html docs/source docs/_build/html
uv run --group docs sphinx-build -n -W -b text docs/source docs/_build/text
uv audit --locked --preview-features audit-command
uv build
```

PostgreSQL tests use QBE2_TEST_DB=postgres and standard PG variables for an isolated
instance. Never run tests against a user's existing database. CI must run all four
Python/Django combinations on both SQLite and PostgreSQL; the PostgreSQL-only
cancellation test may skip only on SQLite.
Use the compatibility commands in docs/source/contributing.rst; a frozen lock alone
selects one Django version and does not verify the whole supported range. Keep Ruff
targeted at Python 3.13 so formatting does not introduce Python 3.14-only syntax.
A local workflow inspection is not evidence that remote CI or publication succeeded.

## Documentation and licensing

Keep installation, runnable examples, row policies, settings and limitations aligned
with the code. Sphinx builds must pass with warnings treated as errors. The documented
consumer examples are exercised by the external-wheel installation test.
Preserve the MIT license and attribution to versae/qbe as inspiration. Preserve any
upstream notices if code is reused in a future contribution.

## Package publication

Read docs/source/releases.rst. Publish uses release.yml and requires a matching v*
tag on main. TestPyPI publication must pass consumer smoke checks for all four
runtimes first. PyPI promotion reuses that successful run's exact artifacts, verifies
the commit and index SHA256 hashes, and uses the pypi environment approval. Never rebuild artifacts
for promotion, enable skip-existing to hide a mismatch, or expose OIDC credentials
to build/test jobs. Configure the environments and pending publishers before dispatch.
