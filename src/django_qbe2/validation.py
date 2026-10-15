"""Parse only authorized field paths and typed values; never execute expressions."""

import re
from decimal import Decimal, InvalidOperation

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator
from django.db import models

from django_qbe2.catalog import FieldSpec, ReportSpec
from django_qbe2.conditions import iter_filters, validate_group
from django_qbe2.definitions import FilterSpec, OrderingSpec, QueryDefinition, Scalar
from django_qbe2.limits import get_limits


def invalid(control: str, message: str):
    raise ValidationError({control: message})


def typed_value(spec: FieldSpec, operator: str, raw: object) -> Scalar:
    if operator == "isnull":
        if type(raw) is not bool:
            raise ValidationError("Use a boolean for isnull.")
        return raw
    field = spec.django_field
    if raw is None:
        raise ValidationError("Use isnull to test null values.")
    if isinstance(field, models.BooleanField):
        if type(raw) is not bool:
            raise ValidationError("Use a boolean value.")
    elif isinstance(field, models.IntegerField):
        if type(raw) is not int and not (
            isinstance(raw, str) and re.fullmatch(r"[+-]?\d+", raw)
        ):
            raise ValidationError("Use an integer value.")
    elif isinstance(field, models.DecimalField):
        if not isinstance(raw, str):
            raise ValidationError("Represent decimal values as text.")
        try:
            if not Decimal(raw).is_finite():
                raise ValidationError("Use a finite decimal value.")
        except InvalidOperation as error:
            raise ValidationError("Use a decimal value.") from error
    elif not isinstance(raw, str):
        raise ValidationError("Use a text value.")
    if isinstance(field, models.DateTimeField):
        value = forms.DateTimeField().clean(raw)
    else:
        value = field.to_python(raw)
    if isinstance(field, (models.CharField, models.TextField)) and operator in (
        "contains",
        "icontains",
        "startswith",
        "istartswith",
    ):
        # A search fragment is not a stored email, URL or other complete value.
        if field.max_length is not None:
            MaxLengthValidator(field.max_length)(value)
    else:
        field.run_validators(value)
    if spec.choices_declared and operator in ("exact", "iexact"):
        permitted = any(
            value.casefold() == choice.casefold()
            if operator == "iexact"
            else value == choice
            for choice, _label in spec.choices
        )
        if not permitted:
            raise ValidationError("Choose a listed value for this field.")
    return value


def validate_filter(row: object, fields: dict[str, FieldSpec]) -> FilterSpec:
    if not isinstance(row, dict) or set(row) != {"field", "operator", "value"}:
        invalid("filters", "Each filter needs a field, operator and value.")
    path, operator = row["field"], row["operator"]
    if not isinstance(path, str) or path not in fields:
        invalid("filters", "Choose a permitted filter field.")
    if not isinstance(operator, str) or operator not in fields[path].operators:
        invalid("filters", "Choose a permitted operator for this field.")
    try:
        value = typed_value(fields[path], operator, row["value"])
    except (ValidationError, ValueError, OverflowError) as error:
        messages = (
            error.messages if isinstance(error, ValidationError) else ["Invalid value."]
        )
        invalid("filters", f"{fields[path].label}: {' '.join(messages)}")
    return FilterSpec(path, operator, value)


def validate_definition(
    payload: object, catalog: dict[str, ReportSpec]
) -> QueryDefinition:
    if not isinstance(payload, dict):
        invalid("definition", "Use the complete versioned query definition.")
    version = payload.get("version")
    if type(version) is not int or version not in (1, 2):
        invalid("definition", "Unsupported query version.")
    keys = {
        "version",
        "report",
        "columns",
        "filters" if version == 1 else "where",
        "ordering",
    }
    if set(payload) != keys:
        invalid("definition", "Use the complete versioned query definition.")
    report_id = payload["report"]
    if not isinstance(report_id, str) or report_id not in catalog:
        invalid("report", "Choose an available report.")
    fields = catalog[report_id].fields
    limits = get_limits()
    for key, maximum in (
        ("columns", limits.max_columns),
        ("filters", limits.max_filters),
        ("ordering", limits.max_ordering),
    ):
        if key == "filters" and version == 2:
            continue
        if not isinstance(payload[key], list) or len(payload[key]) > maximum:
            invalid(key, f"Use at most {maximum} {key}.")
    columns = payload["columns"]
    if not columns or any(
        not isinstance(path, str) or path not in fields for path in columns
    ):
        invalid("columns", "Choose at least one permitted column.")
    if len(set(columns)) != len(columns):
        invalid("columns", "Choose each column once.")
    where = None
    if version == 1:
        filters = [validate_filter(row, fields) for row in payload["filters"]]
    else:
        where = validate_group(
            payload["where"],
            limits=limits,
            validate_leaf=lambda row: validate_filter(row, fields),
        )
        filters = list(iter_filters(where))
    ordering = []
    ordered_fields = set()
    for row in payload["ordering"]:
        if not isinstance(row, dict) or set(row) != {"field", "direction"}:
            invalid("ordering", "Each ordering needs a field and direction.")
        path, direction = row["field"], row["direction"]
        if not isinstance(path, str) or path not in fields or path in ordered_fields:
            invalid("ordering", "Choose distinct permitted ordering fields.")
        if direction not in ("asc", "desc"):
            invalid("ordering", "Choose ascending or descending order.")
        ordered_fields.add(path)
        ordering.append(OrderingSpec(path, direction))
    return QueryDefinition(
        version, report_id, tuple(columns), tuple(filters), tuple(ordering), where
    )
