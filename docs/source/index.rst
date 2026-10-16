Django QBE 2
============

Build reports without writing SQL: choose columns, add typed conditions or summary
calculations, preview pages and download CSV or optional Excel workbooks. Django QBE 2 is a reusable app for **Python 3.13–3.14 and
Django 6.0–6.1**, inspired by `versae/qbe <https://github.com/versae/qbe>`_.

.. warning::

   This is an experimental alpha. Check PyPI for the ``0.1.0a12`` candidate's
   availability, or use the checkout/a locally built wheel. The public
   configuration API may change before a stable release.

Start with :doc:`quickstart` to try the synthetic demo, or :doc:`installation` to
add the app to an existing project. Read :doc:`reports` before exposing real data:
Django model permissions and each report's row policy are both required.

.. toctree::
   :maxdepth: 2
   :caption: User guide

   quickstart
   installation
   reports
   querying
   saved_queries
   scheduled_reports
   configuration
   troubleshooting

.. toctree::
   :maxdepth: 2
   :caption: Developer guide

   api
   contributing
   releases
   roadmap
   relationship-design

Sources are plain reStructuredText under ``docs/source/``. Developers and agents
can read them directly from the repository without running the demo. Sphinx also
produces HTML with search and plain-text output; see :doc:`contributing`.

The code is licensed under MIT. This is a new implementation rather than a
migration of the original package. Preserve upstream notices when reusing code.
