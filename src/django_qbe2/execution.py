from contextlib import contextmanager
from dataclasses import dataclass
from math import ceil

from django.core.exceptions import ValidationError
from django.db import connections, transaction
from django.db.models import QuerySet

from django_qbe2.catalog import ReportSpec
from django_qbe2.definitions import QueryDefinition, Scalar
from django_qbe2.limits import get_limits

STATEMENT_TIMEOUT_MS = 5000


@contextmanager
def query_timeout(*, using: str = "default"):
    connection = connections[using]
    if connection.vendor != "postgresql":
        yield
        return
    with transaction.atomic(using=using), connection.cursor() as cursor:
        cursor.execute("SHOW statement_timeout")
        previous = cursor.fetchone()[0]
        cursor.execute(
            "SELECT set_config('statement_timeout', %s, true)",
            [str(STATEMENT_TIMEOUT_MS)],
        )
        yield
        cursor.execute("SELECT set_config('statement_timeout', %s, true)", [previous])


@dataclass(frozen=True)
class ResultPage:
    rows: list[dict[str, Scalar]]
    labels: tuple[str, ...]
    page: int
    page_size: int
    total_limited: int
    num_pages: int
    truncated: bool


def bounded_count(queryset: QuerySet, *, max_rows: int) -> tuple[int, bool]:
    with query_timeout():
        count = queryset[: max_rows + 1].count()
    return min(count, max_rows), count > max_rows


def get_page(
    queryset: QuerySet,
    definition: QueryDefinition,
    catalog: dict[str, ReportSpec],
    *,
    page: int,
    page_size: int,
) -> ResultPage:
    limits = get_limits()
    if type(page) is not int or page < 1:
        raise ValidationError({"page": "Choose a positive page number."})
    if type(page_size) is not int or not 1 <= page_size <= limits.max_page_size:
        raise ValidationError(
            {"page_size": f"Choose 1–{limits.max_page_size} rows per page."}
        )
    total, truncated = bounded_count(queryset, max_rows=limits.max_rows)
    num_pages = max(1, ceil(total / page_size))
    if page > num_pages:
        raise ValidationError({"page": "This page does not exist."})
    start = (page - 1) * page_size
    with query_timeout():
        rows = list(
            queryset.values(*definition.columns)[start : min(start + page_size, total)]
        )
    fields = catalog[definition.report].fields
    return ResultPage(
        rows,
        tuple(fields[path].label for path in definition.columns),
        page,
        page_size,
        total,
        num_pages,
        truncated,
    )
