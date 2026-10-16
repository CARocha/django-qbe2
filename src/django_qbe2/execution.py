from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from math import ceil
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import connections, transaction
from django.db.models import QuerySet
from django.http import HttpRequest

from django_qbe2.catalog import ReportSpec
from django_qbe2.definitions import QueryDefinition, Scalar, SummaryDefinition
from django_qbe2.limits import get_limits
from django_qbe2.relations import related_value_rows

if TYPE_CHECKING:
    from django_qbe2.aggregation import SummaryResult

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
        try:
            yield
        finally:
            cursor.execute(
                "SELECT set_config('statement_timeout', %s, true)", [previous]
            )


@dataclass(frozen=True)
class ResultPage:
    rows: list[dict[str, Scalar | tuple[Scalar, ...]]]
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
    request: HttpRequest,
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
    fields = catalog[definition.report].fields
    collection_paths = [
        path for path in definition.columns if fields[path].multi_valued
    ]
    scalar_paths = [path for path in definition.columns if path not in collection_paths]
    root_values = queryset.values("pk", *scalar_paths)
    related_count = 0
    with query_timeout():
        rows = list(root_values[start : min(start + page_size, total)])
        root_ids = [row.pop("pk") for row in rows]
        for path in collection_paths:
            related_by_root = {root_id: [] for root_id in root_ids}
            for root_id, _target_id, value in related_value_rows(
                fields[path], catalog, request, root_ids
            ).iterator(chunk_size=200):
                related_count += 1
                if related_count > limits.max_related_values:
                    raise ValidationError(
                        "Too many related values. Refine the report and try again."
                    )
                related_by_root[root_id].append(value)
            for root_id, row in zip(root_ids, rows, strict=True):
                row[path] = tuple(related_by_root[root_id])
    return ResultPage(
        rows,
        tuple(fields[path].label for path in definition.columns),
        page,
        page_size,
        total,
        num_pages,
        truncated,
    )


def execute_summary(
    queryset: QuerySet,
    definition: SummaryDefinition,
    catalog: dict[str, ReportSpec],
) -> SummaryResult:
    from django_qbe2.summary_sql import execute_database_summary

    limits = get_limits()
    with query_timeout(using=queryset.db):
        return execute_database_summary(
            queryset,
            definition,
            catalog[definition.report],
            source_limit=limits.max_aggregate_rows,
        )
