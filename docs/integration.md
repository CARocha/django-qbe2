# Integration contract

## Configuration

The app exposes `Report` and `register` in `django_qbe2.registry`.
`get_queryset(request)` is mandatory and must return instances of the declared
model on the default database, without slices or values()/values_list() projections.
Return your application's authorized queryset, not a new unscoped manager query.
If your admin already implements this policy, call that policy from the report.
The package does not infer tenant rules or automatically adopt a custom AdminSite.

`fields` is a nonempty tuple of unique paths. `field_labels` maps only those paths
to display text. Paths are local scalar fields or one forward FK/OneToOne hop.
The related target and its terminal field must also be registered. Configuration
checks report unsupported fields/relations and missing targets before serving requests.
Registering the same model twice raises ImproperlyConfigured immediately.

The package uses the documented model metadata and QuerySet APIs, following
[Django's reusable-app guidance](https://docs.djangoproject.com/en/6.1/intro/reusable-apps/).
Templates and static files are scoped under `django_qbe2` and included in both archives.

## Access and data scopes

Entry requires an authenticated, active staff user. Catalog entries also require
`<app_label>.view_<model_name>`. A related path requires view permission for its
target. Superuser row access still depends on your report's explicit policy.
The demo deliberately allows its superuser to see all synthetic records.

If a related object is outside its report policy, the root row is excluded whenever
that relationship is used in a column, filter or ordering. A null FK can remain.
This rule also handles ForeignKey.to_field and applies to CSV. No request-specific
catalog or result is cached in a global registry or shared mutable class attribute.

## Types and operators

| Type | Operators |
|---|---|
| CharField/TextField | exact, iexact, contains, icontains, startswith, istartswith |
| IntegerField/DecimalField/DateField/DateTimeField | exact, gt, gte, lt, lte |
| BooleanField/UUIDField | exact |
| Nullable supported field | additionally isnull with a JSON boolean |

Decimal input is text, never a JSON float. UUID and ISO dates/times are text.
Naive datetime inputs use Django's active timezone; ambiguous times are rejected.
Boolean input is true/false; integer input excludes bool. Field conversion and
validators reject invalid values without querying the report data.
Text fragment lookups (contains/icontains/startswith/istartswith) check the input
type and field maximum length, rather than full-value format or custom validators.
This permits searching EmailField and URLField by fragments. Exact text lookups
still run the field's validators.
JSON, floating point, file/binary fields, generic relations and composite keys are
not offered in this initial version. Regular-expression lookups are not allowed.

## Limits

| Setting | Default |
|---|---:|
| QBE2_PAGE_SIZE | 50 |
| QBE2_MAX_PAGE_SIZE | 200 |
| QBE2_MAX_COLUMNS | 20 |
| QBE2_MAX_FILTERS | 20 |
| QBE2_MAX_ORDERING | 3 |
| QBE2_MAX_ROWS | 10000 |

Settings must be positive integers; bool is rejected. PAGE_SIZE cannot exceed
MAX_PAGE_SIZE. A PK tiebreaker makes ordering stable for a fixed dataset. Pages
are separate reads, not snapshots: concurrent inserts/updates can change later pages.
The bounded count checks at most cap+1 rows and never claims a global count beyond
the cap. PostgreSQL evaluates report reads with a 5-second statement timeout,
restoring the previous setting afterward. SQLite supports the app but not that timeout.
Row limits and statement timeouts are different controls; choose budgets for your data.

## HTTP flow and query definitions

Mount `django_qbe2.urls` under your chosen prefix. Route names are
`django_qbe2:builder`, `django_qbe2:results` and `django_qbe2:export`.
Builder accepts GET; results/export accept POST and require CSRF.
Invalid definitions return 400 with form errors, unauthenticated requests go to the
admin login, nonstaff requests receive 403, unavailable reports receive 404, and
unsupported methods receive 405. Unexpected failures return generic 500 responses
without SQL/payload details. Query definitions are not authorization tokens.

```json
{
  "version": 1,
  "report": "sales.order",
  "columns": ["number", "customer__name", "total"],
  "filters": [{"field": "total", "operator": "gte", "value": "100.00"}],
  "ordering": [{"field": "total", "direction": "desc"}]
}
```

All keys are required; empty filters/ordering lists are valid. Unsupported keys,
versions, paths, operators and malformed structures are rejected. Pagination and
editing carry an escaped JSON definition and validate access again on the server.
No result rows are stored in the session. There is no REST API or saved-query model.

## CSV

CSV includes all matching rows up to MAX_ROWS, not just the displayed page.
Column order and policies match the report. Text is UTF-8; dates/times use ISO,
decimals preserve precision, booleans use true/false and null becomes an empty cell.
Text beginning with a spreadsheet formula marker (including after whitespace)
is prefixed with an apostrophe. Typed negative numbers retain their sign.
CSV is an interchange format and does not preserve spreadsheet column types.

`X-QBE-Truncated: true` signals a limited export. The result screen explains the cap.
The synchronous iterator is intended for WSGI. Django can adapt it for ASGI, but
that may buffer the response; ASGI-native streaming is not advertised yet.
The first projected row is checked before returning a response. A failure during
later streaming is logged and aborts the download; headers already sent cannot be
changed to a new status. Cursor and timeout contexts close on interruption.

Use the app as a report tool for authorized internal users, and retain your host
project's normal deployment settings, static serving and authentication configuration.
