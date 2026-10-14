Try the demo
============

The demo is a separate Django project that consumes the reusable app. It creates
only synthetic data: six customers and 24 orders split between two staff users.
Each user's reports and related customer fields are scoped to their own records.

Prepare the checkout
--------------------

Install Python 3.14 and `uv <https://docs.astral.sh/uv/getting-started/installation/>`_,
then run:

.. code-block:: console

   git clone https://github.com/CARocha/django-qbe2.git
   cd django-qbe2
   uv sync --python 3.14 --frozen --group dev
   uv run python demo/manage.py migrate
   uv run python demo/manage.py seed_demo
   uv run python demo/manage.py changepassword qbe2_demo_alice
   uv run python demo/manage.py runserver 127.0.0.1:8000

Choose your own password. The seed never assigns a shared password. It can be run
again without duplicating its records, and refuses to overwrite a non-demo account
with the same username. The second account is ``qbe2_demo_bob``; use
``changepassword`` separately if you want to test it.

.. note::

   The demo server and its SQLite database are for
   local development; retain your host project's normal production settings.

Build a report
--------------

#. Open ``http://127.0.0.1:8000/qbe/`` and log in as ``qbe2_demo_alice``.
#. Choose the Orders report.
#. Select Number, Customer and Total amount as columns.
#. Add a condition on Total amount, choose Greater than or equal to, and enter
   ``100.00``. Use decimal text rather than a JSON floating-point number.
#. Optionally add Delivered equals No (false). Conditions are combined with AND.
#. Choose Total amount descending and a page size, then run the report.
#. Navigate between pages or use Edit query to change conditions.
#. Download CSV to export all matching rows up to the configured report limit.

The CSV includes the complete bounded report, even when you are viewing page two.
Log in as Bob to check isolation: Alice's rows and customer data must not appear.
An optional superuser created with ``demo/manage.py createsuperuser`` can view all
synthetic rows because the demo explicitly implements that policy.

The app can run without JavaScript using its initial condition and ordering rows.
JavaScript adds multiple rows and adapts value controls to the selected field.

Next steps
----------

Use :doc:`installation` for your own project and :doc:`reports` to implement row
policies. :doc:`querying` explains supported values, relationships and CSV behavior.
