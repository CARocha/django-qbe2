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
     - Maximum conditions across all groups
   * - ``QBE2_MAX_GROUPS``
     - 10
     - Maximum condition groups including the root
   * - ``QBE2_MAX_GROUP_DEPTH``
     - 3
     - Maximum nested group levels including the root
   * - ``QBE2_MAX_ORDERING``
     - 3
     - Maximum explicit sort keys
   * - ``QBE2_MAX_GROUP_BY``
     - 3
     - Maximum fields used to group a summary
   * - ``QBE2_MAX_METRICS``
     - 10
     - Maximum count, sum and average calculations in a summary
   * - ``QBE2_MAX_AGGREGATE_ROWS``
     - 10,000
     - Maximum authorized source rows used to calculate a summary
   * - ``QBE2_MAX_ROWS``
     - 10,000
     - Maximum row results or completed summary groups returned/exported
   * - ``QBE2_MAX_SAVED_QUERIES``
     - 100
     - Maximum stored definitions per owner, including copies

PostgreSQL report statements run with a 5-second statement timeout and restore the
previous connection setting. Summary source reads use the same timeout. This timeout is currently an internal constant, not a
public Django setting. SQLite has the same row/page budgets but no equivalent
statement timeout. Choose both source and output budgets for your data and existing
database indexes. A summary exceeding the source cap fails without partial totals;
an output exceeding ``QBE2_MAX_ROWS`` is truncated only after complete calculations.

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
     - Validate, execute, paginate, edit or add builder controls
   * - ``django_qbe2:export``
     - POST
     - Validate and download bounded CSV
   * - ``django_qbe2:saved_list``
     - GET
     - Paginated owned/accessible shared definitions
   * - ``django_qbe2:saved_open``
     - GET
     - Revalidate a saved definition and open the builder
   * - ``django_qbe2:saved_create``
     - POST
     - Save a validated definition or a new copy
   * - ``django_qbe2:saved_update``
     - POST
     - Owner-only definition update
   * - ``django_qbe2:saved_settings``
     - GET, POST
     - Owner-only name and recipient management
   * - ``django_qbe2:saved_delete``
     - GET, POST
     - Owner-only confirmation and deletion

Results and export require Django CSRF protection. The builder accepts a ``report``
query parameter using the model's ``app_label.model_name`` identifier. The other
report routes accept a ``definition`` JSON form field; result pagination also carries
``page`` and ``page_size``. There is no standalone JSON REST endpoint.
Saved-object routes use a UUID ``pk``. All mutations require CSRF. Results opened
from a saved definition carry ``saved_query`` through editing and pagination;
its identifier never grants access by itself. See :doc:`saved_queries`.

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
