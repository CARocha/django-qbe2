Release status and publication
==============================

Current status
--------------

The current alpha candidate is ``0.1.0a15``. It is experimental: its configuration
API may change before a stable release. A metadata version or Git tag does not
prove publication; verify the corresponding PyPI/TestPyPI index entry and the
successful Publish workflow. Version metadata has one source: ``pyproject.toml``.

The MVP includes report registration, explicit row policies, related-row checks,
typed AND/OR/NOT groups, bounded Count/Sum/Average summaries, stable pages, safe
CSV and optional Excel exports and a synthetic demo. Saved definitions support
explicit reader/copy sharing.
See :doc:`roadmap` for remaining priorities.
See :download:`CHANGELOG.md <../../CHANGELOG.md>` for consumer-facing changes.

Configure Trusted Publishing
----------------------------

Create separate PyPI and TestPyPI accounts, verify their emails and configure 2FA.
In each account's Publishing page, add a new pending GitHub publisher:

.. list-table::
   :header-rows: 1

   * - Field
     - TestPyPI
     - PyPI
   * - Project name
     - ``django-qbe2``
     - ``django-qbe2``
   * - Owner
     - ``CARocha``
     - ``CARocha``
   * - Repository
     - ``django-qbe2``
     - ``django-qbe2``
   * - Workflow filename
     - ``release.yml``
     - ``release.yml``
   * - Environment
     - ``testpypi``
     - ``pypi``

A pending publisher creates the project on first upload; it does not reserve the
name. Do not create account-wide API tokens: this workflow uses GitHub OIDC.
The ``id-token: write`` permission is confined to the isolated upload jobs.

In GitHub Settings > Environments, create ``testpypi`` and ``pypi``. Under
Deployment branches, choose Selected branches and tags and add a **Tag** rule
``v*`` for each. In ``pypi``, configure the maintainer as a Required reviewer.
For a sole maintainer, leave Prevent self-review unchecked so they can approve
their own dispatch. Configure environments before dispatching: workflow references
alone do not create approval rules. No repository secret is required.

Publish to TestPyPI first
-------------------------

#. Review and integrate the release branch into ``main``. The metadata version,
   changelog and installation examples must agree.
#. Run the app/demo tests across all four Python/Django combinations on both databases, strict documentation builds,
   lint/format and the native dependency audit. Locked build/publishing dependencies
   live in the ``release`` group, outside the runtime requirements.
#. Create the annotated tag ``v0.1.0a15`` at the verified main commit and push only
   main and that tag. Personal/archived branches must remain local.
#. In GitHub Actions, select **Publish** > Run workflow. Select the release tag,
   choose destination ``testpypi`` and leave source_run_id empty.
#. The workflow checks the tag against metadata and confirms its commit belongs
   to main. It calls the same SQLite/PostgreSQL/documentation CI before building.
#. The build uses the locked backend, validates wheel/sdist metadata, stores the
   pair as an immutable ``release-dist`` artifact and uploads it using TestPyPI OIDC.
#. The final job checks the uploaded files' SHA256 hashes against the original
   artifacts and installs the package in a fresh external Django consumer. Django
   dependencies come from regular PyPI; the candidate comes from TestPyPI with
   ``--no-deps``. Django checks, template rendering and static discovery must pass.

Record the successful **workflow run ID** from its URL, for example the number
following ``actions/runs/``. Do not confuse it with a job ID. The artifact is kept
for 30 days, so promotion must occur while it remains available. A published version
cannot be silently replaced; do not use skip-existing to conceal duplicate uploads.

Promote the verified files to PyPI
----------------------------------

#. Dispatch **Publish** again from the **same release tag**, choose destination
   ``pypi`` and supply the successful TestPyPI workflow run ID.
#. Preflight rejects a different commit, workflow, failed run or missing successful
   TestPyPI installation check. The app/demo/documentation CI runs again.
#. Promotion downloads that run's original wheel and sdist without rebuilding.
   Their bytes must still match TestPyPI's published hashes. Metadata is rechecked.
#. Approve the waiting ``pypi`` environment deployment. The isolated upload job
   publishes those exact files using PyPI Trusted Publishing.
#. The last job checks PyPI's hashes and performs external consumer installs in all
   four supported Python/Django combinations.
   Confirm the public project/version page before announcing availability.

If a post-upload verification fails, inspect the error and repair the release
process; the uploaded version still exists. Rerun only the failed verification
job to retain the original uploaded files and run ID. A new dispatch/full rerun
attempts another upload of immutable filenames. Use a new version for code changes.
TestPyPI is temporary test infrastructure, not a permanent release archive.

Repository and documentation publication
----------------------------------------

Review tracked files and reachable history before pushing. Ignoring a file does
not remove existing commits. Publish only clean main and public feature branches;
never push all local branches or force-push shared history.

The separate Documentation workflow publishes Sphinx HTML/text to GitHub Pages
only when manually dispatched from main. Enable GitHub Pages with GitHub Actions
as its source first. Pull requests validate documentation without deploying.
Add the verified site URL to README/project metadata after deployment succeeds.

References
----------

- `PyPI Trusted Publisher setup
  <https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/>`_
- `Publishing with OIDC
  <https://docs.pypi.org/trusted-publishers/using-a-publisher/>`_
- `Python packaging tutorial
  <https://packaging.python.org/en/latest/tutorials/packaging-projects/>`_
- `GitHub deployment environments
  <https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments>`_
- `GitHub Pages workflows
  <https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages>`_
