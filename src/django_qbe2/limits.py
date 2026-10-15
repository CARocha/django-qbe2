from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


@dataclass(frozen=True)
class Limits:
    page_size: int = 50
    max_page_size: int = 200
    max_columns: int = 20
    max_filters: int = 20
    max_groups: int = 10
    max_group_depth: int = 3
    max_ordering: int = 3
    max_rows: int = 10_000
    max_aggregate_rows: int = 10_000
    max_group_by: int = 3
    max_metrics: int = 10
    max_saved_queries: int = 100


def get_limits() -> Limits:
    defaults = Limits()
    values = {}
    for name in defaults.__dataclass_fields__:
        value = getattr(settings, f"QBE2_{name.upper()}", getattr(defaults, name))
        if type(value) is not int or value < 1:
            raise ImproperlyConfigured(
                f"QBE2_{name.upper()} must be a positive integer."
            )
        values[name] = value
    if values["page_size"] > values["max_page_size"]:
        raise ImproperlyConfigured("QBE2_PAGE_SIZE exceeds QBE2_MAX_PAGE_SIZE.")
    return Limits(**values)
