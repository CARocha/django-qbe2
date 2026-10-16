# Changelog

## 0.1.0a12 — release candidate

### Changed

- Simplified the visual report explorer with collapsible model sections and one
  compact action menu per field for adding columns, filters and summary groups.
- Improved field search so matching models open automatically and unrelated models
  are hidden.

## 0.1.0a11 — release candidate

### Added

- A visual report explorer for browsing registered, authorized fields and relations,
  then adding columns, filters and summary groupings to a report.
- Bar charts for one-dimensional grouped summaries, with selectable Count, Sum or
  Average metrics and pagination-aware display.

## 0.1.0a10 — release candidate

### Added

- Optional ``django-qbe2[excel]`` workbooks for authorized row and summary reports,
  with bounded exports, typed cells, formula-safe text and joined relationship values.
- Excel stays hidden and CSV remains available when the optional dependency is absent.

## 0.1.0a9 — release candidate

### Added

- Reverse ForeignKey/OneToOne and forward/reverse ManyToMany paths up to two hops.
- Related-row permission and queryset-policy enforcement across each relationship.
- Existential filters and bounded, stable collection values in HTML and CSV, keeping
  one output row per root record.
- ``QBE2_MAX_RELATED_VALUES`` to bound related values materialized in each result
  page or complete export.
- Validation that keeps multi-valued paths out of row ordering, summary grouping and
  numeric summary metrics.

Saved definition versions remain unchanged; no package database migration is needed.

## 0.1.0a7 — 2026-10-14

### Added

- Rows/Summary report modes with bounded ungrouped and grouped Count, Sum and
  Average calculations over each request's authorized root rows.
- Strict JSON v3 definitions, numeric-only metric controls, stable metric IDs,
  deterministic summary ordering and complete-result pagination.
- Summary CSV and saved-query support using the existing owner, sharing, copy and
  current-user revalidation rules.
- Independent source and output caps, exact Python Decimal accumulation, explicit
  NULL semantics and half-even Average rounding.

No database migration is required for summaries. Existing v1 and v2 definitions
continue to open and execute unchanged.

## 0.1.0a6 — release candidate

### Added

- Visible nested AND/OR/NOT condition groups with keyboard-accessible controls
  and server-rendered additions that work without JavaScript.
- Bounded JSON v2 definitions, retaining unchanged v1 AND semantics and saved data.
- Global group/depth limits and tests proving root and related-row policies remain
  outside OR/NOT expressions, including shared execution, pagination and CSV.

No database migration is required for condition groups.

## 0.1.0a5 — 2026-10-14

### Added

- Django Admin app-list/sidebar navigation to saved queries, using the same
  ownership and sharing rules. The entry does not expose raw model editing.
- Navigation respects consumer-defined Admin and QBE URL prefixes.

Availability is confirmed by a successful publication workflow and index entry.

## 0.1.0a4 — 2026-10-14

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
