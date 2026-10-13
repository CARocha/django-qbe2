"""Bounded CSV streaming with the same queryset used by HTML reports."""

import csv
import logging
from datetime import date

from django.db.models import QuerySet
from django.http import StreamingHttpResponse

from django_qbe2.catalog import ReportSpec
from django_qbe2.definitions import QueryDefinition, Scalar
from django_qbe2.execution import bounded_count, query_timeout
from django_qbe2.limits import get_limits

logger = logging.getLogger(__name__)


class Echo:
    def write(self, value: str) -> str:
        return value


def csv_cell(value: Scalar) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        if value.lstrip(" \t\r\n\v\f\ufeff").startswith(("=", "+", "-", "@")):
            return "'" + value
        return value
    if isinstance(value, date):
        return value.isoformat()
    if type(value) is bool:
        return "true" if value else "false"
    return str(value)


def csv_response(
    queryset: QuerySet,
    definition: QueryDefinition,
    catalog: dict[str, ReportSpec],
) -> StreamingHttpResponse:
    limit = get_limits().max_rows
    _, truncated = bounded_count(queryset, max_rows=limit)
    with query_timeout():
        # Finish this preflight before returning from an ATOMIC_REQUESTS view.
        list(queryset.values(*definition.columns)[:1])
    labels = [
        catalog[definition.report].fields[path].label for path in definition.columns
    ]

    def rows():
        writer = csv.writer(Echo())
        try:
            with query_timeout():
                iterator = queryset.values(*definition.columns)[:limit].iterator(
                    chunk_size=200
                )
                try:
                    yield writer.writerow([csv_cell(label) for label in labels])
                    for row in iterator:
                        yield writer.writerow(
                            [csv_cell(row[path]) for path in definition.columns]
                        )
                finally:
                    iterator.close()
        except Exception as error:
            logger.error("CSV stream failed (%s).", type(error).__name__)
            raise

    response = StreamingHttpResponse(rows(), content_type="text/csv; charset=utf-8")
    filename = f"report-{definition.report.replace('.', '-')}.csv"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    if truncated:
        response["X-QBE-Truncated"] = "true"
    return response
