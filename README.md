# Django QBE 2

A reusable Django app for building authorized reports without writing SQL.
Choose columns, add typed conditions, follow model relationships, preview paginated
results, build grouped summaries and export CSV. Supports **Python 3.13–3.14 and Django 6.0–6.1**.

**Experimental alpha:** this is the initial implementation, not a production
release or a drop-in replacement for the original package. The current release
candidate is `0.1.0a7`; check [PyPI](https://pypi.org/project/django-qbe2/) for its
availability. Inspired by [versae/qbe](https://github.com/versae/qbe), rebuilt around
Django's ORM, explicit permissions and typed query definitions.

## Try the demo

From a checkout containing this implementation:

```sh
uv sync --python 3.14 --frozen --group dev
uv run python demo/manage.py migrate
uv run python demo/manage.py seed_demo
uv run python demo/manage.py changepassword qbe2_demo_alice
uv run python demo/manage.py runserver 127.0.0.1:8000
```

Open [the report builder](http://127.0.0.1:8000/qbe/) and log in as
`qbe2_demo_alice` with the password you chose. The seed creates six synthetic
customers and 24 orders for two users. Each user can view only their own records.
It never sets a shared password or overwrites an existing non-demo account.
An optional superuser created with `createsuperuser` can inspect all demo records.

## Install in another project

In your project's virtual environment, install the explicit alpha version after
checking its availability on PyPI:

```sh
python -m pip install django-qbe2==0.1.0a7
```

To try the checkout before publication, build and install its wheel:

```sh
uv build
python -m pip install /absolute/path/to/dist/django_qbe2-0.1.0a7-py3-none-any.whl
```

Add the app and mount its namespaced URLs alongside Django Admin:

```python
# Keep your existing Django apps, including admin, auth, sessions and messages.
INSTALLED_APPS += ["django_qbe2"]
```

```python
from django.urls import include, path

# Keep your existing admin URL and other routes.
urlpatterns += [path("qbe/", include("django_qbe2.urls"))]
```

Keep standard authentication, sessions and CSRF middleware, APP_DIRS template
discovery and the admin context processors. Serve the packaged assets with your
usual Django static-file setup. Run `python manage.py migrate` to create the
saved-query tables when installing or upgrading to the `0.1.0a4` candidate.
The catalog is empty until you register reports.

## Register reports and their policies

Create `qbe.py` in your own installed app. Modules are discovered at startup,
without fetching report data. Register related targets as well as root models:

```python
from django_qbe2.registry import Report, register
from .models import Customer, Order


@register
class CustomerReport(Report):
    model = Customer
    fields = ("name",)

    def get_queryset(self, request):
        return Customer.objects.filter(owner=request.user)


@register
class OrderReport(Report):
    model = Order
    fields = ("number", "customer__name", "total", "status")
    field_labels = {"customer__name": "Customer", "total": "Total amount"}

    def get_queryset(self, request):
        return Order.objects.filter(owner=request.user)
```

Users need active staff status and Django `view` permissions for the root and any
related model used. Staff status alone does not grant report access. Every report
must provide an explicit row policy; Django model permissions do not imply row
authorization. The same policies apply to columns, filters, ordering, HTML and CSV.

Django model `choices` require no QBE-specific configuration. Register the field,
and equality filters offer its options automatically. The complete documentation
example defines an Order status using `TextChoices`. Adapt the example's fields
and ownership policy to your own models; `owner` is not a required field name.

For saved queries introduced in `0.1.0a4`, run `python manage.py migrate` after
upgrading. Preview a report to save its definition, then use **Saved queries** to
reopen it or manage named recipients. Sharing never grants model permissions or
access to the creator's rows. See the [saved-query guide](docs/source/saved_queries.rst)
and [roadmap](docs/source/roadmap.rst). Condition groups preserve existing saved
definitions and require no additional migration. Summary definitions use the same
storage, sharing and current-user authorization rules.

## What is included

- Text, integer, decimal, boolean, date, datetime and UUID fields.
- Generic model-choice selectors and readable HTML labels; CSV keeps stored codes.
- Saved definitions, private by default, with explicit reader/copy sharing.
- Bounded nested AND/OR/NOT groups, ascending/descending order and stable pagination.
- Grouped or ungrouped Count, Sum and Average reports over authorized source rows.
- Up to two relationship hops, including reverse and ManyToMany relations, with
  explicit related-row authorization and bounded collection columns.
- Bounded CSV streaming, exact decimals, Unicode and safe text formula handling.
- Django Admin styling, light/dark modes and responsive, keyboard-accessible controls.

Database-native aggregates, arbitrary joins, multi-database selection, Excel and
the visual diagram are later work.
CSV uses a synchronous streaming iterator intended for WSGI deployment.
See the [public documentation](https://github.com/CARocha/django-qbe2/blob/main/docs/README.md) for installation, row policies,
settings, API reference and troubleshooting. Sources are plain English
reStructuredText under [docs/source](https://github.com/CARocha/django-qbe2/blob/main/docs/source/index.rst), readable by developers
and agents. Contributor instructions live in [AGENTS.md](https://github.com/CARocha/django-qbe2/blob/main/AGENTS.md).

## Build the documentation

```sh
uv sync --python 3.14 --frozen --group dev --group docs
uv run --group docs sphinx-build -n -W -b html docs/source docs/_build/html
uv run --group docs sphinx-build -n -W -b text docs/source docs/_build/text
python -m http.server 8001 --bind 127.0.0.1 --directory docs/_build/html
```

Open http://127.0.0.1:8001/. Sphinx is a documentation dependency only. CI checks
HTML and plain-text builds with warnings treated as errors. A manual GitHub Pages
workflow is prepared; the documentation site is not yet published.

## License and attribution

MIT, copyright Carlos A. Rocha. The project acknowledges Javier de la Rosa and the
contributors to `versae/qbe` as its inspiration. The current code is a new
implementation; preserve upstream notices if you reuse upstream code in a future change.
