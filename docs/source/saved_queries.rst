Saved queries and sharing
=========================

This feature is included in the ``0.1.0a4`` candidate. Earlier published alphas
have no saved-query storage. Check :doc:`releases` for publication status.

Set up storage
--------------

After upgrading and adding ``django_qbe2`` to ``INSTALLED_APPS``, apply migrations:

.. code-block:: console

   python manage.py migrate

The package creates a saved-definition table and a recipient relation table on
the default database. Both user relationships use ``AUTH_USER_MODEL``; custom
users and UUID user primary keys are supported. No business models are changed.
Run your normal migrations and static deployment process when upgrading.

Find your queries
-----------------

Use **Saved queries** at the top of the QBE builder/results, or open
``<your-qbe-prefix>/saved/`` directly. From the ``0.1.0a5`` release, Django's
default Admin also shows **Django QBE 2 > Saved queries** in its app list and
sidebar. That entry opens the same authorized QBE list; **Build a report** returns
to the builder. It does not expose a separate model editor or grant data access.
No new database migration is needed for this navigation change.

Save and reuse a definition
---------------------------

#. Build a report and select **Preview report**.
#. Enter a name in **Save query**, then save it. The new query is private.
#. Use **Saved queries** to reopen the definition in the builder.
#. Preview again to query current data. Opening the builder does not run the report.
#. An owner can select **Update saved query** to replace the stored definition,
   or **Save a copy** to create another query. Previewing and editing alone never
   change the stored definition.

The definition contains versioned JSON columns, conditions and ordering, plus the saved
page size. It stores choice codes and exact decimal/date representations. It
does not store result rows, SQL, querysets or snapshots. Two executions may produce
different results as data or access policies change.

Share with named users
----------------------

The owner opens **Name and sharing** and enters known staff login identifiers,
one per line. The identifier comes from the consumer's custom user model
``USERNAME_FIELD``; it may be a username or email address. Recipients must exist
and be active staff. The UI does not provide a directory of user accounts.
Leave the field empty to make the query private again.

Recipients can open the definition, preview/export it and save a private copy.
Only the owner can modify the original, rename it, replace its recipients or
delete it. Superusers follow these saved-object rules too. Sharing a definition
does not grant model permissions or access to its owner's rows: each execution
uses the recipient's current permissions and ``Report.get_queryset(request)``.
Related fields retain their own permission and row-policy checks.

.. important::

   A query's name and filter values may contain sensitive information. Sharing
   intentionally exposes its definition to the selected recipients. Choose names
   and recipients accordingly. A copy is a separate definition owned by its
   creator; unsharing the original does not delete copies already made.

Updating the definition preserves its recipients. Use **Name and sharing** to
change sharing explicitly. Removing a recipient revokes their access to the
original. Deleting requires a confirmation and a CSRF-protected POST; the
confirmation page alone does not delete anything. Deleting the owner account
also removes its queries through Django's cascade behavior.

Changed permissions or configuration
------------------------------------

Every load, save, result and export validates against the current authorized
catalog. Shared queries with an unavailable root report disappear from the
recipient's list and return 404 when opened. Invalid stored fields, operators,
choice codes or page sizes produce a helpful 400 page without displaying the
raw definition. The owner can still rename, unshare or delete an obsolete query;
build a new report when its old definition cannot be used.

Bounds
------

- Names contain at most 120 characters and need not be unique.
- Definitions contain at most 64 KiB of UTF-8 JSON.
- At most 50 recipients may be selected for one query.
- Each owner may create 100 queries by default, configurable through the positive
  integer ``QBE2_MAX_SAVED_QUERIES``. Copies count towards the creator's quota.
- The list shows 25 entries per page. Existing report/page/filter/export budgets
  continue to apply when definitions are saved and executed.

Group sharing, collaborative editing and stored result snapshots are outside this
feature. Scheduled reports use a separate independent snapshot; see
:doc:`scheduled_reports`. The storage and form helpers are internal APIs; the supported
integration remains app installation, namespaced routes, settings and report registration.


Grouped and summary definitions
-------------------------------

Saved definitions accept both the original v1 AND filters and v2 AND/OR/NOT
trees. No migration or bulk rewrite is needed for condition groups. Opening an
existing v1 definition does not modify it. Saving edits with groups uses v2;
opening, copying, pagination and CSV/Excel exports preserve the expression. All branches are
revalidated against the executing user's current catalog and row policies.

Summary definitions use v3 and store only grouping fields, calculation choices,
conditions and ordering. They never store totals or source rows. No additional
database migration is needed. Opening, copying, sharing, updating, pagination and
CSV and Excel use the same owner/reader rules as row reports. Each execution recalculates the
summary from the executing user's current authorized rows and related-field scopes.
See :doc:`querying` for the formats, limits and NULL semantics.
