Feature roadmap
===============

The package evolves as a reusable Django application. Features must work with
registered models, custom users and consumer-defined row policies. No feature
may depend on a particular business app's field names.

Completed increments
--------------------

- Explicit reports, typed AND filters, one forward relation hop, pagination and CSV.
- Python 3.13–3.14 and Django 6.0–6.1 compatibility, verified on SQLite/PostgreSQL.
- Generic Django model-choice selectors and readable HTML labels.
- Saved definitions with private defaults and explicit reader/copy sharing
  (``0.1.0a4``; see :doc:`saved_queries`).
- Native Django Admin navigation to the authorized saved-query list (``0.1.0a5``).

- Bounded AND/OR/NOT groups with versioned definitions and unchanged row policies
  (``0.1.0a6`` candidate; see :doc:`querying`).
- Authorized Count, Sum and Average summaries with up to three grouping fields,
  bounded source/output rows, saved definitions and CSV (``0.1.0a7`` candidate;
  see :doc:`querying`).

Next scoped increments
----------------------

#. **More relationships:** evaluate ManyToMany and reverse relations with explicit
   related-row policies and tests for duplicate rows and aggregate semantics.
#. **Visual exploration:** a diagram derived only from the authorized catalog,
   useful alongside the form rather than necessary to execute a report.

Each increment gets a scoped design, its own feature branch, regression tests,
public documentation and a compatibility check before integration. This order
sets priorities, not release dates or a promise of full SQL parity.

Other ideas needing separate design include custom operators, multiple database
aliases, database-native aggregate execution, Excel export, a public REST API,
group sharing and scheduled reports.
Arbitrary client SQL and Python evaluation remain outside the intended interface.
