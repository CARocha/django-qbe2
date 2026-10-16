Feature roadmap
===============

The package evolves as a reusable Django application. Features must work with
registered models, custom users and consumer-defined row policies. No feature
may depend on a particular business app's field names.

Completed increments
--------------------

- Explicit reports, typed condition groups, authorized relationship paths, pagination
  and CSV.
- Python 3.13–3.14 and Django 6.0–6.1 compatibility, verified on SQLite/PostgreSQL.
- Generic Django model-choice selectors and readable HTML labels.
- Saved definitions with private defaults and explicit reader/copy sharing
  (``0.1.0a4``; see :doc:`saved_queries`).
- Native Django Admin navigation to the authorized saved-query list (``0.1.0a5``).

- Bounded AND/OR/NOT groups with versioned definitions and unchanged row policies
  (``0.1.0a6`` candidate; see :doc:`querying`).
- Authorized Count, Sum and Average summaries with up to three grouping fields,
  bounded source/output rows, saved definitions and CSV (``0.1.0a7``;
  see :doc:`querying`).
- Reverse ForeignKey/OneToOne and ManyToMany paths up to two relationship hops,
  with scoped related-row policies, existential filters and bounded one-row-per-root
  output (see :doc:`relationship-design`).
- Optional typed Excel exports for authorized row and summary reports; CSV remains
  the default dependency-free format.
- Authorized visual field and relationship explorer with builder shortcuts,
  a server-rendered fallback and no automatic model discovery.
- Summary bar charts for one grouping field with a selectable Count, Sum or
  Average metric. Charts show only the current page; the table and exports
  retain their existing behavior.
- Database-native Count, Sum and Average over authorized summary sources, with
  bounded source checks and exact Decimal handling across SQLite and PostgreSQL.

Future ideas requiring separate design
---------------------------------------

The next planned increment is scheduled reports: a saved, independent query
snapshot that can run on a daily or weekly schedule and email bounded CSV or
optional Excel attachments to configured recipients. Each run will recheck the
current user's report permissions and row policies. Further work will be chosen
from user feedback and receive a scoped design, regression tests, public
documentation and compatibility checks. Ideas that need separate design include
custom operators, multiple database aliases, a public REST API and group sharing.
This roadmap sets priorities, not release dates or a promise of full SQL parity.
Arbitrary client SQL and Python evaluation remain outside the intended interface.
