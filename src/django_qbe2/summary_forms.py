from django import forms
from django.core.exceptions import ValidationError
from django.db import models
from django.forms import BaseFormSet
from django.utils.translation import gettext_lazy as _


def numeric_field_choices(fields):
    return [
        (path, spec.label)
        for path, spec in fields.items()
        if isinstance(spec.django_field, (models.IntegerField, models.DecimalField))
        and not isinstance(spec.django_field, models.BooleanField)
    ]


class SummaryMetricForm(forms.Form):
    id = forms.RegexField(regex=r"^m[1-9][0-9]{0,8}$", widget=forms.HiddenInput)
    function = forms.ChoiceField(
        label=_("Calculation"),
        choices=(
            ("", _("Choose calculation")),
            ("count", _("Count records")),
            ("sum", _("Sum")),
            ("avg", _("Average")),
        ),
        required=False,
    )
    field = forms.ChoiceField(label=_("Field"), required=False)

    def __init__(self, *args, fields, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["field"].choices = [("", _("No field"))] + numeric_field_choices(
            fields
        )


class SummaryOrderingForm(forms.Form):
    target = forms.ChoiceField(label=_("Value"), required=False)
    direction = forms.ChoiceField(
        label=_("Direction"),
        choices=(("asc", _("Ascending")), ("desc", _("Descending"))),
        initial="asc",
        required=False,
    )

    def __init__(self, *args, group_fields, metric_ids, fields, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [("", _("Choose value"))]
        choices.extend(
            (f"group:{path}", _("Group: %(field)s") % {"field": fields[path].label})
            for path in group_fields
            if path in fields
        )
        choices.extend(
            (f"metric:{metric_id}", _("Calculation %(id)s") % {"id": metric_id})
            for metric_id in metric_ids
        )
        self.fields["target"].choices = choices


class SummaryMetricFormSet(BaseFormSet):
    pass


def compact_metrics(data, formset, maximum):
    management = formset.management_form
    if not management.is_valid():
        raise ValidationError(_("Invalid calculation controls."))
    total = management.cleaned_data["TOTAL_FORMS"]
    initial = management.cleaned_data["INITIAL_FORMS"]
    if not 0 <= initial <= total <= maximum:
        raise ValidationError(_("Invalid calculation controls."))
    rows = []
    for index in range(total):
        if forms.CheckboxInput().value_from_datadict(
            data, {}, f"metrics-{index}-DELETE"
        ):
            continue
        rows.append(
            {
                key: data[f"metrics-{index}-{key}"]
                for key in ("id", "function", "field")
                if f"metrics-{index}-{key}" in data
            }
        )
    compacted = data.copy()
    for key in list(compacted):
        if key.startswith("metrics-"):
            del compacted[key]
    compacted.update(
        {
            "metrics-TOTAL_FORMS": str(len(rows)),
            "metrics-INITIAL_FORMS": "0",
            "metrics-MIN_NUM_FORMS": "0",
            "metrics-MAX_NUM_FORMS": str(maximum),
        }
    )
    for index, row in enumerate(rows):
        for key, value in row.items():
            compacted[f"metrics-{index}-{key}"] = value
    return compacted


def compact_summary_ordering(data, formset, maximum):
    management = formset.management_form
    if not management.is_valid():
        raise ValidationError(_("Invalid ordering controls."))
    total = management.cleaned_data["TOTAL_FORMS"]
    initial = management.cleaned_data["INITIAL_FORMS"]
    if not 0 <= initial <= total <= maximum:
        raise ValidationError(_("Invalid ordering controls."))
    rows = []
    for index in range(total):
        if forms.CheckboxInput().value_from_datadict(
            data, {}, f"summary_ordering-{index}-DELETE"
        ):
            continue
        rows.append(
            {
                key: data[f"summary_ordering-{index}-{key}"]
                for key in ("target", "direction")
                if f"summary_ordering-{index}-{key}" in data
            }
        )
    compacted = data.copy()
    for key in list(compacted):
        if key.startswith("summary_ordering-"):
            del compacted[key]
    compacted.update(
        {
            "summary_ordering-TOTAL_FORMS": str(len(rows)),
            "summary_ordering-INITIAL_FORMS": "0",
            "summary_ordering-MIN_NUM_FORMS": "0",
            "summary_ordering-MAX_NUM_FORMS": str(maximum),
        }
    )
    for index, row in enumerate(rows):
        for key, value in row.items():
            compacted[f"summary_ordering-{index}-{key}"] = value
    return compacted
