"""Create bounded in-memory report attachments and deliver them privately."""

from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage
from django.http import FileResponse, StreamingHttpResponse
from django.utils.translation import gettext as _

from django_qbe2.definitions import QueryDefinition, SummaryDefinition
from django_qbe2.engine import build_queryset, build_summary_source
from django_qbe2.execution import bounded_count, execute_summary
from django_qbe2.exports import (
    XLSX_CONTENT_TYPE,
    csv_response,
    excel_available,
    summary_csv_response,
    summary_xlsx_response,
    xlsx_response,
)
from django_qbe2.limits import get_limits
from django_qbe2.models import ScheduledReport
from django_qbe2.scheduled_execution import ScheduledExecutionContext

CSV_CONTENT_TYPE = "text/csv; charset=utf-8"


@dataclass(frozen=True)
class ReportAttachment:
    filename: str
    content_type: str
    content: bytes


def _read_bounded_response(response, maximum: int) -> bytes:
    content = bytearray()
    oversized = False
    try:
        if isinstance(response, StreamingHttpResponse):
            chunks = response.streaming_content
        elif isinstance(response, FileResponse):
            chunks = response.streaming_content
        else:
            chunks = (response.content,)
        for chunk in chunks:
            if isinstance(chunk, str):
                chunk = chunk.encode(response.charset or "utf-8")
            if len(content) + len(chunk) > maximum:
                oversized = True
            elif not oversized:
                content.extend(chunk)
        if oversized:
            raise ValidationError(
                {
                    "attachment": _(
                        "The report attachment exceeds the configured size limit."
                    )
                }
            )
    finally:
        if isinstance(response, FileResponse):
            response.close()
    return bytes(content)


def build_report_attachment(
    execution: ScheduledExecutionContext, schedule: ScheduledReport
) -> ReportAttachment:
    limits = get_limits()
    if schedule.format == ScheduledReport.OutputFormat.XLSX and not excel_available():
        raise ValidationError(
            _(
                "Excel export requires the optional dependency. "
                "Install django-qbe2[excel]."
            )
        )
    definition = execution.definition
    if isinstance(definition, QueryDefinition):
        queryset = build_queryset(definition, execution.catalog, execution.request)
        _count, truncated = bounded_count(queryset, max_rows=limits.max_rows)
        if truncated:
            raise ValidationError(
                _("Too many report rows. Refine the report before scheduling it.")
            )
        response = (
            xlsx_response(
                queryset, definition, execution.catalog, request=execution.request
            )
            if schedule.format == ScheduledReport.OutputFormat.XLSX
            else csv_response(
                queryset, definition, execution.catalog, request=execution.request
            )
        )
        extension = "xlsx" if schedule.format == "xlsx" else "csv"
        content_type = XLSX_CONTENT_TYPE if extension == "xlsx" else CSV_CONTENT_TYPE
    elif isinstance(definition, SummaryDefinition):
        source = build_summary_source(definition, execution.catalog, execution.request)
        result = execute_summary(source, definition, execution.catalog)
        if len(result.rows) > limits.max_rows:
            raise ValidationError(
                _("Too many summary rows. Refine the report before scheduling it.")
            )
        response = (
            summary_xlsx_response(result, definition)
            if schedule.format == ScheduledReport.OutputFormat.XLSX
            else summary_csv_response(result, definition)
        )
        extension = "xlsx" if schedule.format == "xlsx" else "csv"
        content_type = XLSX_CONTENT_TYPE if extension == "xlsx" else CSV_CONTENT_TYPE
    else:
        raise ValidationError(_("Invalid scheduled report definition."))

    content = _read_bounded_response(response, limits.max_scheduled_attachment_bytes)
    filename = f"report-{definition.report.replace('.', '-')}.{extension}"
    return ReportAttachment(filename, content_type, content)


def send_scheduled_report(
    schedule: ScheduledReport, attachment: ReportAttachment
) -> int:
    message = EmailMessage(
        subject=_("Scheduled report: %(name)s") % {"name": schedule.name},
        body=_("Your scheduled report is attached."),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[],
        bcc=list(schedule.recipients),
    )
    message.attach(attachment.filename, attachment.content, attachment.content_type)
    delivered = message.send(fail_silently=False)
    if delivered != 1:
        raise OSError("The configured email backend did not deliver the report.")
    return delivered
