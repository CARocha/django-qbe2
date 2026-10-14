# Changelog

## 0.1.0a2 — release candidate

### Changed

- Support Python 3.13 and 3.14 with Django 6.0 and 6.1, so existing Django 6.0
  consumers can install QBE without upgrading their framework.
- Test all four combinations on SQLite and PostgreSQL, including external-wheel
  HTML/CSV policy checks and published-package installation at both indexes.

### Fixed

- Use exception syntax supported by Python 3.13; the original alpha failed to
  import its views on that interpreter. Ruff now preserves Python 3.13 syntax.

Availability is confirmed by a successful publication workflow and index entry.

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
