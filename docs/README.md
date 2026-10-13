# Public documentation

Read [source/index.rst](source/index.rst) directly or build the Sphinx site:

```sh
uv sync --python 3.14 --frozen --group dev --group docs
uv run --group docs sphinx-build -n -W -b html docs/source docs/_build/html
uv run --group docs sphinx-build -n -W -b text docs/source docs/_build/text
python -m http.server 8001 --bind 127.0.0.1 --directory docs/_build/html
```

Open http://127.0.0.1:8001/. Sources are English reStructuredText. The documentation
build does not import Django or connect to a database. Generated files are ignored.
The `docs` group adds no runtime dependencies to the reusable app.

Installation: [source/installation.rst](source/installation.rst).
Demo: [source/quickstart.rst](source/quickstart.rst).
Permissions: [source/reports.rst](source/reports.rst).
Contributor and CI checks: [source/contributing.rst](source/contributing.rst).
Publication: [source/releases.rst](source/releases.rst).
