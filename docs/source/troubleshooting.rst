Troubleshooting
===============

No reports available
--------------------

Check that your business app is in ``INSTALLED_APPS`` and that its ``qbe.py`` uses
``@register``. The logged-in user must be active staff with model view permissions.
For a related field, also grant the target model's view permission. An empty
catalog is intentional until these requirements are met.

The report is empty although Admin shows rows
----------------------------------------------

The report combines the visible conditions with ``get_queryset(request)``.
Django Admin may use a different row policy. Remove conditions temporarily to
distinguish the query from the report's access scope. A superuser still follows
that scope; they do not automatically receive every row. See :doc:`reports`
for an explicit superuser policy. Empty results do not disclose how many rows
exist outside the user's scope.

Preview returns a generic error
-------------------------------

Look for ``Report request failed (<ExceptionClass>).`` in your application's
server logs. A ``FieldError`` can mean that ``get_queryset(request)`` refers to
a nonexistent field. The installation example uses ``owner`` because its models
have that field; adapt it to your model, such as ``user`` or a tenant relationship.
Keep SQL, credentials and real query data out of public bug reports.

A row disappears when I add a related column
--------------------------------------------

The target row is outside its report's ``get_queryset(request)`` policy. The root
row is excluded whenever that relationship is used. Fix the application policy
only if the user is authorized; do not remove the related-row check to reveal data.
See :doc:`reports`.

System checks fail
------------------

Run ``python manage.py check`` and correct the registration:

.. list-table::
   :header-rows: 1

   * - Check ID
     - Configuration problem
   * - ``django_qbe2.E001``
     - Missing/invalid nonempty fields tuple
   * - ``django_qbe2.E002``
     - Duplicate, malformed or unknown field paths
   * - ``django_qbe2.E003``
     - Unsupported field, relationship, multiple hop or composite key
   * - ``django_qbe2.E004``
     - Target report or terminal field is not registered
   * - ``django_qbe2.E005``
     - Labels do not map declared paths to text

A duplicate report or missing policy method can raise ``ImproperlyConfigured``
at startup before system checks run.

Login or static assets do not work
----------------------------------

Keep the default Django admin route, session/authentication/messages middleware
and CSRF middleware. The standard admin template configuration must be present.
Use ``collectstatic`` and your normal static serving setup outside development.
A custom AdminSite is not automatically adopted by this version.

A filter is rejected
--------------------

Use an operator offered for the field. Decimal values must be finite text, UUIDs
and dates must parse, and Boolean JSON values must be actual booleans. Use
``isnull`` for nulls and distinguish false, zero and empty text from missing input.
Review :doc:`querying` for format validators and text fragment lookups.

Report or CSV is incomplete
---------------------------

Check the report cap and truncation notice/header. A PostgreSQL timeout may abort
an expensive query. Add appropriate indexes in the host application and choose
budgets for your workload. CSV interrupted after its headers may end without an
HTML error page. Logs identify the exception class; inspect your own database
monitoring for the underlying failure without exposing sensitive query input.

A summary has two distinct bounds. ``QBE2_MAX_AGGREGATE_ROWS`` limits authorized
source rows and rejects the request before returning any partial total.
``QBE2_MAX_ROWS`` limits completed groups shown or exported and reports truncation.
Raise the source bound only after considering memory and request time.

Summary totals look different on SQLite
----------------------------------------

Django documents SQLite's decimal limitations. Django QBE 2 accumulates retrieved
``DecimalField`` values with Python ``Decimal`` and rounds Average half-even, but
SQLite may already have converted stored decimal values through binary floating
point. Use PostgreSQL when exact database decimal storage is required.

Unsupported behavior
--------------------

Generic relations, more than two relationship hops, multiple collection edges in
one field, database-native aggregates, multi-database selection, Excel and visual
diagrams are unsupported. Describe the intended workflow and constraints in a
GitHub issue instead of working around server-side restrictions with arbitrary SQL.
