Settings and HTTP routes
========================

Report budgets
--------------

Set these in your host project's settings. All values must be positive integers;
booleans are rejected. ``QBE2_PAGE_SIZE`` cannot exceed ``QBE2_MAX_PAGE_SIZE``.

.. list-table::
   :header-rows: 1

   * - Setting
     - Default
     - Meaning
   * - ``QBE2_PAGE_SIZE``
     - 50
     - Initial rows per page
   * - ``QBE2_MAX_PAGE_SIZE``
     - 200
     - Maximum requested rows per page
   * - ``QBE2_MAX_COLUMNS``
     - 20
     - Maximum selected columns
   * - ``QBE2_MAX_FILTERS``
     - 20
     - Maximum AND conditions
   * - ``QBE2_MAX_ORDERING``
     - 3
     - Maximum explicit sort keys
   * - ``QBE2_MAX_ROWS``
     - 10,000
     - Maximum report/export rows

PostgreSQL report statements run with a 5-second statement timeout and restore the
previous connection setting. This timeout is currently an internal constant, not a
public Django setting. SQLite has the same row/page budgets but no equivalent
statement timeout. Choose row budgets for your data and existing database indexes.

Namespaced routes
-----------------

Mount ``django_qbe2.urls`` under a prefix of your choice. The route names remain:

.. list-table::
   :header-rows: 1

   * - Route name
     - Method
     - Purpose
   * - ``django_qbe2:builder``
     - GET
     - Select a report and construct a query
   * - ``django_qbe2:results``
     - POST
     - Validate, execute, paginate or edit a query
   * - ``django_qbe2:export``
     - POST
     - Validate and download bounded CSV

Results and export require Django CSRF protection. The builder accepts a ``report``
query parameter using the model's ``app_label.model_name`` identifier. The other
routes accept a ``definition`` JSON form field; result pagination also carries
``page`` and ``page_size``. There is no standalone JSON REST endpoint.

Authentication and errors
-------------------------

Anonymous users are redirected to the default admin login. Inactive/nonstaff users
are denied. Unavailable reports return 404; invalid input generally returns 400
with form errors; unsupported methods return 405. Unexpected execution failures
return a generic 500 without exposing SQL or payload details. CSV failures after
streaming begins abort the download; see :doc:`querying`.

Retain your application's authentication, session, CSRF, static serving and
production deployment configuration. The package provides reporting controls,
not a deployment configuration for your entire project.
