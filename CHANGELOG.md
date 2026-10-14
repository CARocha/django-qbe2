# Changelog

## 0.1.0a4 — release candidate

### Added

- Save named query definitions and page sizes, reopen them and explicitly update
  or copy them without storing result rows.
- Share definitions with named active staff users for reading and copying; only
  the creator can modify the original, manage recipients or delete it.
- Owner/recipient-scoped access, current-permission validation and bounded storage.
- Package migrations with swappable user relationships, verified with UUID users
  in a clean external consumer. Run `python manage.py migrate` after upgrading.
- Public documentation for sharing, storage, privacy and future feature priorities.

### Fixed

- Enforce the configured page-size bound during form validation and saving,
  rather than relying only on execution-time checks.

Availability is confirmed by a successful publication workflow and index entry.

## 0.1.0a3 — 2026-10-13

### Added

- Generic equality selectors for declared Django model choices, including text,
  numeric, boolean, grouped and callable options and permitted related fields.
- Readable choice labels in HTML results; CSV continues to export stored codes.
- Empty-result guidance explaining conditions and the report's row policy.
- Installation examples for model choices and explicit superuser row policies.

### Changed

- Equality filters validate choice membership on the server. Existing queries
  using undeclared codes need updating; fragment searches and range thresholds
  retain their existing behavior. Unknown stored codes still display unchanged.
- Editing retains selected options, including zero, false, integer-text aliases
  and case-insensitive text codes. Date/time choices use the active timezone.

Generic choices alpha published to TestPyPI and PyPI.

## 0.1.0a2 — 2026-10-13

### Changed

- Support Python 3.13 and 3.14 with Django 6.0 and 6.1, so existing Django 6.0
  consumers can install QBE without upgrading their framework.
- Test all four combinations on SQLite and PostgreSQL, including external-wheel
  HTML/CSV policy checks and published-package installation at both indexes.

### Fixed

- Use exception syntax supported by Python 3.13; the original alpha failed to
  import its views on that interpreter. Ruff now preserves Python 3.13 syntax.

Compatibility alpha published to TestPyPI and PyPI.

## 0.1.0a1 — 2026-10-13

### Added

- Public Sphinx documentation covering installation, demo, report policies,
  query types, settings, API reference, troubleshooting and contribution.
- Strict HTML/plain-text documentation checks and a manual Pages workflow.
- External-wheel verification of the documented consumer's row policies,
  HTML results and CSV export.

- Explicit report registration and row policies for Python 3.14/Django 6.1.
- Authorized typed queries, forward relationships, stable bounded pagination.
- Admin-integrated report builder, editing and responsive light/dark presentation.
- Scoped CSV streaming with formula-safe text and PostgreSQL timeout cleanup.
- Synthetic customer/order demo and idempotent seed command.
- Unit/integration tests, PostgreSQL/SQLite CI and external wheel installation checks.

Initial experimental alpha published to TestPyPI and PyPI.
