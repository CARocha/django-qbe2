"""Snapshot declared choices without inferring values from a model's rows."""

from datetime import date

from django import forms
from django.db import models

from django_qbe2.definitions import Scalar


def field_choices(field: models.Field) -> tuple[tuple[Scalar, str], ...]:
    choices = []
    for value, label in field.choices or ():
        items = label if isinstance(label, (list, tuple)) else ((value, label),)
        for key, text in items:
            if key is not None:
                value = (
                    forms.DateTimeField().clean(key)
                    if isinstance(field, models.DateTimeField)
                    else field.to_python(key)
                )
                if value is not None:
                    choices.append((value, str(text)))
    return tuple(choices)


def choice_value(value: Scalar) -> str:
    if type(value) is bool:
        return "true" if value else "false"
    if isinstance(value, date):
        return value.isoformat()
    return str(value)
