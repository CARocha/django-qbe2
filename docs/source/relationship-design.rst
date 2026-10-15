More relationships: design proposal
====================================

.. warning::

   This is a design proposal for a future increment. It describes intended behavior;
   the currently published package does not support reverse or many-to-many paths.

Goal and compatibility
----------------------

Allow a report to traverse registered Django models in either direction and include
reverse ForeignKey and ManyToMany data without multiplying root rows. A generic
report such as subscriptions can show its user and that user's pets while remaining
independent of application-specific model or field names. The implementation must
work on SQLite and PostgreSQL with Django 6.0 and 6.1 and Python 3.13 and 3.14.

The saved-definition formats remain unchanged. Paths continue to use Django's
``__`` notation and must be declared by the root report; clients cannot invent paths.

Path contract
-------------

* A path may traverse at most two relationships and must end in a supported scalar
  field from a registered report.
* Supported edges are forward ForeignKey/OneToOne, reverse ForeignKey/OneToOne, and
  forward/reverse ManyToMany.
* At most one edge in a field path may have multiple related rows. A path may combine
  one to-one edge and one multi-valued edge, in either order.
* Every intermediate and terminal model must have a registered report and the
  executing user must have that model's Django ``view`` permission.
* Catalog construction and execution must apply the relevant report
  ``get_queryset(request)`` policies. Registration, staff status and superuser status
  do not replace those row policies.
* Multi-valued paths may be selected in row reports and used in conditions. They
  cannot be used for ordering, summary grouping or numeric summary metrics in this
  increment. Summary totals continue to count distinct root records.

Rows and filters
----------------

A row report returns one row per root object, even when several related objects match.
Each selected multi-valued scalar is collected independently and shown in one cell,
joined in related-object primary-key order with ``", "`` as the separator. Distinct
related objects remain distinct even when their scalar values are equal. Duplicate
many-to-many through-table links to the same target do not repeat that target.
Separate collection columns are evaluated independently so two collections do not
form a cross product.

Each condition leaf on a multi-valued path has existential semantics: a root matches
when at least one related object on that path satisfies the leaf. Boolean AND, OR and
NOT groups combine those root-level truth values. Therefore, two leaves under AND
may match different related objects. This behavior must be documented and covered by
tests.

For an empty collection, HTML uses the existing empty-value presentation and CSV
uses an empty cell. HTML choice fields display their declared labels; CSV retains
stored values, consistent with current scalar-field behavior. Joined output is plain
text and HTML-escaped.

Bounds and failure behavior
---------------------------

Collection values are fetched in batches per selected multi-valued path, never with
one query per root row. The root page is selected and paginated before collection
values are fetched. Related values use a stable order. A request-wide configurable
cap limits the total related values materialized while producing a page or CSV. If
the cap is exceeded, the request fails with a validation message; it must not return
a silently truncated cell or partial CSV. The proposed setting is
``QBE2_MAX_RELATED_VALUES``, defaulting to 10,000.

The root queryset remains the source of row policy, conditions and root ordering.
Related report policies constrain every traversed model, including intermediate
models. CSV uses the same path validation, policies, formatting and cap as HTML.
Saved and shared reports are revalidated against the current catalog and executing
user's policies on every request.

Verification contract
---------------------

Tests must cover forward and reverse traversal, both ManyToMany directions, paths
through an intermediate model, missing relationships, repeated scalar values,
duplicate through links, multiple collection columns without cross products,
existential filter semantics, every boolean group operator, row-policy isolation,
permission failures, saved-query revalidation, pagination, CSV, the related-value cap,
and SQLite/PostgreSQL behavior. Existing one-hop reports, aggregation semantics and
the formats of saved definitions must remain unchanged.
