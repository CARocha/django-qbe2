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

Choose ascending or descending ordering for single-valued fields. A primary-key
ordering tiebreaker makes pages stable for a fixed dataset. Pages are separate
reads, not snapshots: concurrent writes may change later pages.

The bounded count reads at most the row cap plus one to detect truncation. A
truncated report does not claim to know the global total. The default page size
is 50, the maximum is 200, and the default report cap is 10,000 rows. See
:doc:`configuration` for configurable budgets and PostgreSQL timeouts.

CSV behavior
------------

The CSV button exports all matching rows up to the report cap, not only the
current page. For a Summary report it exports completed groups and calculations,
ordered exactly like the preview. Column order, row policies and related-row checks match HTML.
Multi-valued report columns are joined into one cell per root row, in related
primary-key order. The related-value limit applies to HTML pages and the complete
CSV; when exceeded, CSV returns an error before streaming begins.
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
Summary execution finishes before CSV headers are returned, so a source-limit or
calculation error produces an ordinary error response rather than a partial file.

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

Summary reports and definition v3
---------------------------------

Choose **Summary** under Report type and apply it. Select zero to three grouping
fields and one to ten calculations. **Count records** needs no field; **Sum** and
**Average** offer only registered integer and decimal fields. Add calculation
works with or without JavaScript and assigns stable ``m1``, ``m2`` identifiers.
Switching report type preserves the report and conditions while resetting output
columns, calculations and ordering. It does not update a saved query until you
explicitly save or update it.

With no grouping fields, a summary returns one row. Count is zero for an empty
source; Sum and Average are empty. With grouping fields, an empty source returns
no groups. NULL forms its own group and renders/exports as an empty cell. Count
includes every authorized source row. Sum and Average ignore NULL metric values;
if all values are NULL their result is empty. Decimal values remain ``Decimal``;
Average uses at least six fractional places and half-even rounding. Integer Average
also returns a decimal value.

The source is a distinct set of authorized root primary keys selected from
``Report.get_queryset(request)`` after conditions and related-field policies. This
prevents joins from counting one root row repeatedly while preserving consumer
annotations, filters and valid distinct semantics. Calculations run in bounded
Python over selected group/metric values. They do not execute client SQL or mutate
business data.

.. code-block:: json

   {
     "version": 3,
     "report": "sales.order",
     "where": {
       "connector": "and",
       "negated": false,
       "children": [
         {"field": "status", "operator": "exact", "value": "paid"}
       ]
     },
     "group_by": ["customer__city"],
     "metrics": [
       {"id": "m1", "function": "count", "field": null},
       {"id": "m2", "function": "sum", "field": "total"},
       {"id": "m3", "function": "avg", "field": "total"}
     ],
     "ordering": [
       {"type": "metric", "id": "m2", "direction": "desc"},
       {"type": "group", "field": "customer__city", "direction": "asc"}
     ]
   }

All six top-level keys are required. Grouping fields and calculations must be
distinct and currently authorized. Metric IDs use ``m`` followed by a positive
integer and ordering references a selected group field or metric ID. Every branch
of ``where`` uses the same v2 condition-tree rules. Unknown keys, client-provided
labels, unsupported numeric fields and excessive controls are rejected.

The default source cap is 10,000 authorized roots. Crossing it fails the entire
summary without returning partial totals. The ordinary 10,000-row output cap is
applied later to complete, deterministically ordered groups; preview and CSV then
show truncation. Related grouping or metric fields activate the same target report
permissions and target row policy used by row reports. Sharing a v3 definition
never shares its creator's source rows or totals.

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
