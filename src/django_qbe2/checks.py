from django.core.checks import Error, Tags, register

from django_qbe2.catalog import CatalogConfigurationError, describe_report
from django_qbe2.registry import get_reports


@register(Tags.models)
def check_reports(app_configs=None, **kwargs):
    reports = {report.model._meta.label_lower: report for report in get_reports()}
    errors = []
    for report in reports.values():
        try:
            describe_report(report, reports)
        except CatalogConfigurationError as error:
            errors.append(Error(str(error), obj=type(report), id=error.check_id))
    return errors
