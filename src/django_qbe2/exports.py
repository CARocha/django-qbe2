"""Bounded CSV streaming with the same queryset used by HTML reports."""

import csv
import logging
from datetime import date, datetime
from decimal import Decimal
from importlib.util import find_spec
from tempfile import SpooledTemporaryFile

from django.core.exceptions import ValidationError
from django.db.models import QuerySet
from django.http import FileResponse, StreamingHttpResponse
from django.utils import timezone

from django_qbe2.aggregation import SummaryResult, paginate_summary
from django_qbe2.catalog import ReportSpec
from django_qbe2.definitions import QueryDefinition, Scalar, SummaryDefinition
from django_qbe2.execution import bounded_count, get_page, query_timeout
from django_qbe2.limits import get_limits

logger = logging.getLogger(__name__)
XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def excel_available() -> bool:
    """Return whether the optional Excel dependency can be imported."""
    return find_spec("openpyxl") is not None


class Echo:
    def write(self, value: str) -> str:
        return value


def csv_cell(value: Scalar | tuple[Scalar, ...]) -> str:
    if isinstance(value, tuple):
        return ", ".join(csv_cell(item) for item in value)
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


def _xlsx_cell(worksheet, value):
    from openpyxl.cell import WriteOnlyCell

    if isinstance(value, tuple):
        value = ", ".join(csv_cell(item) for item in value)
    if value is None:
        return None
    if isinstance(value, str):
        cell = WriteOnlyCell(worksheet, value=value)
        cell.data_type = "s"
        return cell
    if isinstance(value, datetime) and timezone.is_aware(value):
        value = timezone.localtime(value).replace(tzinfo=None)
    if isinstance(value, (date, datetime, bool, int, float, Decimal)):
        return value
    cell = WriteOnlyCell(worksheet, value=str(value))
    cell.data_type = "s"
    return cell


def _xlsx_response(rows, labels, report_id, truncated=False):
    from openpyxl import Workbook

    temporary = SpooledTemporaryFile(max_size=1024 * 1024, mode="w+b")
    try:
        workbook = Workbook(write_only=True)
        worksheet = workbook.create_sheet(title="Report")
        worksheet.append([_xlsx_cell(worksheet, label) for label in labels])
        for row in rows:
            worksheet.append([_xlsx_cell(worksheet, value) for value in row])
        workbook.save(temporary)
        workbook.close()
        temporary.seek(0)
    except Exception:
        temporary.close()
        raise
    filename = f"report-{report_id.replace('.', '-')}.xlsx"
    response = FileResponse(
        temporary,
        content_type=XLSX_CONTENT_TYPE,
        as_attachment=True,
        filename=filename,
    )
    if truncated:
        response["X-QBE-Truncated"] = "true"
    return response


def xlsx_response(
    queryset: QuerySet,
    definition: QueryDefinition,
    catalog: dict[str, ReportSpec],
    request=None,
) -> FileResponse:
    if not excel_available():
        raise ValidationError(
            "Excel export requires the optional dependency. Install django-qbe2[excel]."
        )
    limit = get_limits().max_rows
    report = catalog[definition.report]
    collection_paths = [
        path for path in definition.columns if report.fields[path].multi_valued
    ]
    labels = [report.fields[path].label for path in definition.columns]
    if collection_paths:
        if request is None:
            raise ValidationError("A request is required to export related values.")
        page_size = min(get_limits().max_page_size, limit)
        first_page = get_page(
            queryset, definition, catalog, request=request, page=1, page_size=page_size
        )
        values = list(first_page.rows)
        for page_number in range(2, first_page.num_pages + 1):
            values.extend(
                get_page(
                    queryset,
                    definition,
                    catalog,
                    request=request,
                    page=page_number,
                    page_size=page_size,
                ).rows
            )
        related_count = sum(
            len(row[path]) for row in values for path in collection_paths
        )
        if related_count > get_limits().max_related_values:
            raise ValidationError(
                "Too many related values. Refine the report and try again."
            )
        rows = (
            [
                row[path] if isinstance(row, dict) else row[index]
                for index, path in enumerate(definition.columns)
            ]
            for row in values
        )
        return _xlsx_response(rows, labels, definition.report, first_page.truncated)
    else:
        _, truncated = bounded_count(queryset, max_rows=limit)
        with query_timeout():
            iterator = queryset.values(*definition.columns)[:limit].iterator(
                chunk_size=200
            )
            try:
                rows = ([row[path] for path in definition.columns] for row in iterator)
                return _xlsx_response(rows, labels, definition.report, truncated)
            finally:
                close = getattr(iterator, "close", None)
                if close:
                    close()


def csv_response(
    queryset: QuerySet,
    definition: QueryDefinition,
    catalog: dict[str, ReportSpec],
    request=None,
) -> StreamingHttpResponse:
    limit = get_limits().max_rows
    report = catalog[definition.report]
    collection_paths = [
        path for path in definition.columns if report.fields[path].multi_valued
    ]
    collection_rows = None
    if collection_paths:
        if request is None:
            raise ValidationError("A request is required to export related values.")
        page_size = min(get_limits().max_page_size, limit)
        first_page = get_page(
            queryset, definition, catalog, request=request, page=1, page_size=page_size
        )
        collection_rows = list(first_page.rows)
        for page_number in range(2, first_page.num_pages + 1):
            collection_rows.extend(
                get_page(
                    queryset,
                    definition,
                    catalog,
                    request=request,
                    page=page_number,
                    page_size=page_size,
                ).rows
            )
        related_count = sum(
            len(row[path]) for row in collection_rows for path in collection_paths
        )
        if related_count > get_limits().max_related_values:
            raise ValidationError(
                "Too many related values. Refine the report and try again."
            )
        truncated = first_page.truncated
    else:
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
                iterator = (
                    iter(collection_rows)
                    if collection_rows is not None
                    else queryset.values(*definition.columns)[:limit].iterator(
                        chunk_size=200
                    )
                )
                try:
                    yield writer.writerow([csv_cell(label) for label in labels])
                    for row in iterator:
                        yield writer.writerow(
                            [
                                csv_cell(
                                    row[path] if isinstance(row, dict) else row[index]
                                )
                                for index, path in enumerate(definition.columns)
                            ]
                        )
                finally:
                    close = getattr(iterator, "close", None)
                    if close:
                        close()
        except Exception as error:
            logger.error("CSV stream failed (%s).", type(error).__name__)
            raise

    response = StreamingHttpResponse(rows(), content_type="text/csv; charset=utf-8")
    filename = f"report-{definition.report.replace('.', '-')}.csv"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    if truncated:
        response["X-QBE-Truncated"] = "true"
    return response


def summary_csv_response(
    result: SummaryResult,
    definition: SummaryDefinition,
) -> StreamingHttpResponse:
    """Return a bounded CSV from an already materialized summary."""
    limits = get_limits()
    page_size = min(limits.max_page_size, limits.max_rows)
    first_page = paginate_summary(
        result,
        definition,
        page=1,
        page_size=page_size,
        max_rows=limits.max_rows,
    )
    rows = list(first_page.rows)
    for page_number in range(2, first_page.num_pages + 1):
        rows.extend(
            paginate_summary(
                result,
                definition,
                page=page_number,
                page_size=page_size,
                max_rows=limits.max_rows,
            ).rows
        )
    columns = result.columns

    def content():
        writer = csv.writer(Echo())
        yield writer.writerow([csv_cell(column.label) for column in columns])
        for row in rows:
            yield writer.writerow([csv_cell(row[column.key]) for column in columns])

    response = StreamingHttpResponse(content(), content_type="text/csv; charset=utf-8")
    filename = f"report-{definition.report.replace('.', '-')}.csv"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    if first_page.truncated:
        response["X-QBE-Truncated"] = "true"
    return response


def summary_xlsx_response(
    result: SummaryResult,
    definition: SummaryDefinition,
) -> FileResponse:
    if not excel_available():
        raise ValidationError(
            "Excel export requires the optional dependency. Install django-qbe2[excel]."
        )
    limits = get_limits()
    page_size = min(limits.max_page_size, limits.max_rows)
    first_page = paginate_summary(
        result,
        definition,
        page=1,
        page_size=page_size,
        max_rows=limits.max_rows,
    )
    rows = list(first_page.rows)
    for page_number in range(2, first_page.num_pages + 1):
        rows.extend(
            paginate_summary(
                result,
                definition,
                page=page_number,
                page_size=page_size,
                max_rows=limits.max_rows,
            ).rows
        )
    columns = result.columns
    output = ([row[column.key] for column in columns] for row in rows)
    return _xlsx_response(
        output,
        [column.label for column in columns],
        definition.report,
        first_page.truncated,
    )
