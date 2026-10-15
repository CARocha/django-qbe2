Related model paths
===================

This page documents supported reverse ForeignKey, reverse OneToOne and
ManyToMany behavior, including its authorization rules and materialization bounds.

Goal and compatibility
----------------------

Reports can traverse registered Django models in either direction and include
multi-valued data without multiplying root rows. A generic report can show its
related records while remaining independent of application-specific model and
field names. The implementation supports SQLite and PostgreSQL with Django 6.0 and
6.1 and Python 3.13 and 3.14.

Saved-definition formats remain unchanged. Paths use Django's ``__`` notation and
must be declared by the root report; clients cannot invent paths.

Path contract
-------------

* A path may traverse at most two relationships and must end in a supported scalar
  field from a registered report.
* Supported edges are forward/reverse ForeignKey and OneToOne, and forward/reverse
  ManyToMany.
* At most one edge in a field path may have multiple related rows.
* Every intermediate and terminal model must have a registered report and the
  executing user must have that model's Django ``view`` permission.
* Catalog construction and execution apply each target report's
  ``get_queryset(request)`` policy. Staff or superuser status does not replace row
  policies.
* Multi-valued paths may be selected and filtered. They cannot be used for row
  ordering, summary grouping or numeric summary metrics. Summary totals count
  distinct root records.

Rows and filters
----------------

A row report returns one row per root object, even when several related objects
match. Each selected multi-valued scalar is collected independently and shown in
one cell, joined in related-object primary-key order with ``", "`` as the separator.
Distinct related objects remain distinct even when their scalar values are equal.
Duplicate many-to-many through-table links to the same target do not repeat that
target. Separate collection columns are evaluated independently, with no cross
product.

Each condition leaf on a multi-valued path has existential semantics: a root matches
when at least one related object on that path satisfies the leaf. Boolean AND, OR
and NOT groups combine those root-level truth values. Two leaves under AND may
therefore match different related objects.

For an empty collection, HTML uses the existing empty-value presentation and CSV
uses an empty cell. HTML choice fields display their declared labels; CSV retains
stored values. Joined output is plain text and HTML-escaped.

Bounds and failure behavior
---------------------------

Collection values are fetched in batches per selected multi-valued path, never with
one query per root row. The root page is selected and paginated before collection
values are fetched. Related values use a stable order. ``QBE2_MAX_RELATED_VALUES``
defaults to 10,000 and limits values materialized for a result page or complete
CSV. If the cap is exceeded, the request fails; it does not return a silently
truncated cell or partial CSV.

The root queryset remains the source of row policy, conditions and root ordering.
Related report policies constrain every traversed model, including intermediates.
CSV uses the same path validation, policies, formatting and cap as HTML. Saved and
shared reports are revalidated against the current catalog and executing user's
policies on every request.

Verification
------------

The test suite covers forward and reverse traversal, both ManyToMany directions,
intermediate paths, duplicate through links, independent collection columns,
existential filters, boolean groups, row-policy isolation, permissions, pagination,
CSV and the related-value cap. SQLite and PostgreSQL are both supported by the
compatibility suite. Existing saved-definition formats remain unchanged.
