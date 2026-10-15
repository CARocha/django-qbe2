Build and export queries
========================

Choose registered columns, add conditions and choose sort keys. Conditions are
combined in visible AND, OR and NOT groups, including repeated conditions on
the same field. Existing flat conditions retain AND semantics. Only catalog
paths and operators are accepted; arbitrary SQL, Python expressions and regular
expression lookups are never accepted.

Supported values
----------------

.. list-table::
   :header-rows: 1
   :widths: 25 45 30

   * - Field type
     - Operators
     - Input
   * - CharField / TextField and supported subclasses
     - exact, iexact, contains, icontains, startswith, istartswith
     - Text, including an empty string
   * - IntegerField
     - exact, gt, gte, lt, lte
     - Integer or integer text; not a boolean
   * - DecimalField
     - exact, gt, gte, lt, lte
     - Finite decimal text such as ``"100.01"``
   * - DateField / DateTimeField
     - exact, gt, gte, lt, lte
     - Date/datetime text
   * - BooleanField
     - exact
     - JSON ``true`` or ``false``
   * - UUIDField
     - exact
     - UUID text
   * - Any nullable supported field
     - additionally isnull
     - JSON ``true`` or ``false``

Decimals are not accepted as JSON floats. Zero and false are preserved. Null
comparison uses ``isnull`` rather than a null value for another operator. Naive
datetime input uses Django's active timezone; ambiguous or nonexistent local
times are rejected. Floating point, JSON, binary/file fields and composite primary
keys are outside the initial supported types.

Full-value lookups run field conversion and validators. Text fragment lookups
(contains/icontains/startswith/istartswith) validate text type and maximum field
length without whole-value format or custom validators. This allows searches such
as EmailField contains ``@example.com`` or URLField contains ``example.com``.

Model choices and labels
------------------------

Declared Django ``choices`` work for any registered scalar field, including
``TextChoices``, ``IntegerChoices``, mappings, grouped options and callables.
The builder offers a selector for equality (``exact`` and ``iexact``), showing
the labels and submitting the stored codes. Text fragments and numeric/date
ranges keep their free-value inputs. Equality values are checked on the server;
changing the browser controls does not bypass validation. ``iexact`` accepts a
case-insensitive match to a declared text code.

Zero, false and explicitly declared empty-string choices remain valid values.
Use ``isnull`` to query NULL; a ``None`` choice is not an equality value. Naive
datetime choices and input use Django's active timezone. Grouped options are
flattened into one selector. JavaScript adapts controls immediately; without
JavaScript, entering a stored code still works and the edit form renders a selector.

HTML results display declared labels. Unknown historical codes remain visible
as their original values. Labels are plain text, including labels marked safe
by host code. Filtering, ordering, pagination and CSV continue to use stored values.
For example, HTML displays ``Open`` and CSV exports ``open``. Exported data does
not depend on the language of a label or on later label changes.

Choices are captured for authorized fields in each request's catalog. No option
is inferred from database rows or cached across requests. Callable choices are
application code: keep them inexpensive and suitable for every user who may
see that field. QBE's configuration checks do not evaluate these callables.

Pagination and ordering
-----------------------

Choose ascending or descending ordering for permitted fields. A primary-key
ordering tiebreaker makes pages stable for a fixed dataset. Pages are separate
reads, not snapshots: concurrent writes may change later pages.

The bounded count reads at most the row cap plus one to detect truncation. A
truncated report does not claim to know the global total. The default page size
is 50, the maximum is 200, and the default report cap is 10,000 rows. See
:doc:`configuration` for configurable budgets and PostgreSQL timeouts.

CSV behavior
------------

The CSV button exports all matching rows up to the report cap, not only the
current page. Column order, row policies and related-row checks match HTML.
UTF-8 text supports Unicode, quotes and embedded newlines. Dates/times use ISO
format, decimals preserve precision, booleans use ``true``/``false``, and null
becomes an empty cell.

Text starting with ``=``, ``+``, ``-`` or ``@`` after leading whitespace/BOM is
prefixed with an apostrophe for spreadsheet formula safety. Typed negative numbers
retain their sign. CSV is an interchange format; it cannot preserve spreadsheet
column types. The response header ``X-QBE-Truncated: true`` indicates a capped export.

The synchronous iterator targets **WSGI**. Django may buffer it when adapting to
ASGI; ASGI-native streaming is not advertised. A first-row preflight catches early
errors. Later errors abort the download and are logged by exception class without
SQL or query payloads. Headers already sent cannot change to a new error status.
Closing or failing the stream releases its cursor and timeout context.

Query definition v1
-------------------

The UI sends a versioned definition back on pagination, editing and export. This
is an HTTP form contract, not a REST API or an authorization token:

.. code-block:: json

   {
     "version": 1,
     "report": "sales.order",
     "columns": ["number", "customer__name", "total"],
     "filters": [{"field": "total", "operator": "gte", "value": "100.00"}],
     "ordering": [{"field": "total", "direction": "desc"}]
   }

All five keys are required. Empty filters and ordering arrays are valid. Columns
must be nonempty and distinct; ordering fields must be distinct. Extra keys,
unknown versions, paths, operators and invalid values are rejected. Result rows
are never stored in the session. Explicitly saved definitions are separate
database records; see :doc:`saved_queries`. No result rows are stored.


Condition groups and definition v2
----------------------------------

Use **Match all (AND)** when every child must match, **Match any (OR)** when at
least one must match, and **Exclude this group (NOT)** to negate the whole group.
For example, ``(status paid OR overdue) AND NOT delivered`` uses an AND root,
an OR child with two status conditions, and a negated child with one delivered
condition. These are generic controls for the fields each report exposes.

Add condition and Add group preserve entered values and refresh the builder;
they do not execute the report. Parent group and Condition group selectors move
controls between groups. Removing a group also removes its descendants on the
next builder submission. A failed preview keeps the pending group removal
separate from each condition's own deletion checkbox, so canceling it restores
its conditions. Add actions reclaim removed controls before allocating new ones.
The root cannot be removed. The controls work without JavaScript;
JavaScript additionally arranges moved controls immediately and adapts value widgets.

Group limits count the whole expression: by default 20 conditions, 10 groups
including the root, and three group levels including the root. Empty nested
groups are rejected on preview. Only an empty, unnegated AND root represents an
unfiltered report. A root using OR or NOT must contain a condition.

Flat, unnegated AND controls use v1. Nested groups, OR or NOT use v2, which replaces
the top-level ``filters`` key with ``where``:

.. code-block:: json

   {
     "version": 2,
     "report": "sales.order",
     "columns": ["number", "total"],
     "where": {
       "connector": "and",
       "negated": false,
       "children": [
         {"field": "total", "operator": "gte", "value": "100.00"},
         {
           "connector": "or",
           "negated": false,
           "children": [
             {"field": "status", "operator": "exact", "value": "paid"},
             {"field": "status", "operator": "exact", "value": "overdue"}
           ]
         }
       ]
     },
     "ordering": []
   }

All five top-level keys are required. Each group has exactly ``connector``,
``negated`` and ``children``; connector is ``and`` or ``or``, negated is a JSON
boolean, and children is a list of groups or ordinary filter leaves. Every branch
is validated against the current catalog. Unknown keys and excessive trees are
rejected. Form group identifiers do not appear in the saved definition. Rebuilding
controls may reorder siblings; AND/OR results do not depend on sibling order.

NULL and authorization semantics
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Groups compile to Django's `Q objects
<https://docs.djangoproject.com/en/6.1/topics/db/queries/#complex-lookups-with-q-objects>`_.
NOT uses Django's negated lookup semantics. For a nullable date, NOT equals
``2026-10-14`` also matches NULL dates. To require a different nonempty date, use
an AND group containing ``isnull = false`` and a negated equality subgroup.

Root row policies and related-object scopes are applied outside the whole user
expression. OR and NOT cannot negate these restrictions. Referencing a related
field anywhere applies its target scope to the entire report, even when a local
OR branch matches; the existing nullable-relation behavior remains unchanged.
Sharing a grouped definition does not share its creator's access to rows.

Preview and CSV read business data; they do not offer create, update or delete
operations. Saving, sharing and removing definitions writes the app's separate
SavedQuery storage. Consumer-provided policies, callable choices and field
validators are trusted application code, and database credentials remain the
consumer's responsibility. Group limits and report budgets bound the feature;
complex filters may still need appropriate database indexes. SQLite has no
package-enforced statement timeout.
