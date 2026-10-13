Release status and publication
==============================

Current status
--------------

The initial implementation is experimental and unreleased. The metadata version
is ``0.1.0`` for local wheel testing; no corresponding PyPI release is claimed.
Before a first public release, use an explicit prerelease such as ``0.1.0a1`` and
keep the package metadata, module version and changelog consistent.

The MVP includes report registration, explicit row policies, related-row checks,
typed AND conditions, stable bounded pages, safe CSV and a synthetic demo.
Saved queries, aggregates, OR/NOT and visual diagrams need later scoped plans.
See :download:`CHANGELOG.md <../../CHANGELOG.md>`
for consumer-facing changes. Compatibility is limited to environments actually
verified by the test suite.

Repository and documentation publication
----------------------------------------

Before the first implementation push, review the tracked file list and reachable
Git history. Ignoring a file does not remove existing commits. Personal development
history and its backup branches must remain local; never use ``git push --all``.
Only reviewed public ``main`` and subsequent public feature branches belong on
GitHub. No force push is needed when the prepared main descends from the existing
remote main and that remote has not advanced.

Run the documented checks before pushing and inspect the real GitHub Actions runs
afterward. A local build is not proof that remote CI passed. The Pages workflow is
manual: enable GitHub Pages with GitHub Actions as its source, then dispatch the
Documentation workflow from ``main``. It rebuilds strict HTML/plain-text docs,
uploads a Pages artifact and deploys through the ``github-pages`` environment.
Pull requests only validate documentation; they do not deploy it.

See `GitHub's custom Pages workflows
<https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages>`_
for repository settings. The site is not considered published until the deployment
actually succeeds. Add its verified URL to README and project metadata then.

First PyPI release
------------------

#. Create separate PyPI and TestPyPI accounts, verify the email addresses and
   configure account security. PyPI requires two-factor authentication.
#. Choose the prerelease version and update metadata, module version and changelog.
#. Build fresh wheel and sdist, validate metadata and install the wheel into an
   external project. Repeat the app and demo suites on supported databases.
#. Configure GitHub Actions Trusted Publishing with a matching repository,
   workflow filename and protected publication environment. A pending publisher
   can create a project on first upload, but it does not reserve its name.
#. Publish to TestPyPI first. Install dependencies from regular PyPI and test the
   uploaded package with TestPyPI and ``--no-deps`` in a fresh environment.
#. With explicit maintainer authorization, publish the reviewed artifacts to PyPI,
   create the matching release/tag and verify installation from the public index.

This repository-preparation change does not publish packages or configure an
account on the maintainer's behalf. The release workflow is a later scoped change.
Read the `Python packaging tutorial
<https://packaging.python.org/en/latest/tutorials/packaging-projects/>`_,
`PyPI account help <https://pypi.org/help/>`_ and
`Trusted Publisher project creation
<https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/>`_
for the current publication procedure.
