Build and export queries
========================

Choose registered columns, add conditions and choose sort keys. Conditions are
combined with AND, including multiple conditions on the same field. Only catalog
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
are never stored in the session. No saved-query model exists in this version.
