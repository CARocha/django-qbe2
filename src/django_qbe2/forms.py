from django import forms
from django.core.exceptions import ValidationError
from django.db import models
from django.forms import formset_factory
from django.http import QueryDict
from django.utils.html import escape
from django.utils.translation import gettext_lazy as _

from django_qbe2.catalog import ReportSpec
from django_qbe2.choices import choice_value
from django_qbe2.group_forms import (
    GroupedFilterFormSet,
    build_where,
    default_group_data,
    display_groups,
    flatten_where,
    make_groups,
    validate_structure,
)
from django_qbe2.limits import get_limits
from django_qbe2.validation import validate_definition

OPERATOR_LABELS = {
    "exact": _("equals"),
    "iexact": _("equals, ignoring case"),
    "contains": _("contains"),
    "icontains": _("contains, ignoring case"),
    "startswith": _("starts with"),
    "istartswith": _("starts with, ignoring case"),
    "gt": _("greater than"),
    "gte": _("at least"),
    "lt": _("less than"),
    "lte": _("at most"),
    "isnull": _("is empty"),
}


class ChoiceSelect(forms.Select):
    """Display the canonical option while preserving the original query payload."""

    def __init__(self, *, spec, operator, choices):
        super().__init__(choices=choices)
        self.spec = spec
        self.operator = operator

    def format_value(self, value):
        try:
            typed = (
                forms.DateTimeField().clean(value)
                if isinstance(self.spec.django_field, models.DateTimeField)
                else self.spec.django_field.to_python(value)
            )
        except (ValidationError, ValueError, TypeError):
            return super().format_value(value)
        for key, _label in self.spec.choices:
            matches = (
                typed.casefold() == key.casefold()
                if self.operator == "iexact" and isinstance(typed, str)
                else typed == key
            )
            if matches:
                return super().format_value(choice_value(key))
        return super().format_value(value)


class FilterForm(forms.Form):
    group = forms.ChoiceField(label=_("Condition group"), required=False)
    field = forms.ChoiceField(label=_("Field"), required=False)
    operator = forms.ChoiceField(label=_("Condition"), required=False)
    value = forms.CharField(label=_("Value"), required=False, strip=False)

    def __init__(self, *args, fields, group_choices=None, **kwargs):
        super().__init__(*args, **kwargs)
        if "group" in self.fields:
            self.fields["group"].choices = group_choices or [
                ("root", _("All conditions"))
            ]
            self.fields["group"].initial = "root"
        self.fields["field"].choices = [("", _("Choose field"))] + [
            (path, field.label) for path, field in fields.items()
        ]
        operators = sorted(
            {operator for field in fields.values() for operator in field.operators}
        )
        self.fields["operator"].choices = [("", _("Choose condition"))] + [
            (operator, OPERATOR_LABELS[operator]) for operator in operators
        ]
        path = (
            self.data.get(self.add_prefix("field"))
            if self.is_bound
            else self.initial.get("field")
        )
        operator = (
            self.data.get(self.add_prefix("operator"))
            if self.is_bound
            else self.initial.get("operator")
        )
        spec = fields.get(path)
        if spec is None:
            return
        choices = None
        if operator == "isnull":
            choices = [("true", _("Yes (true)")), ("false", _("No (false)"))]
        elif operator in ("exact", "iexact") and spec.choices_declared:
            choices = [
                (choice_value(value), escape(label)) for value, label in spec.choices
            ]
        elif isinstance(spec.django_field, models.BooleanField):
            choices = [("true", _("Yes (true)")), ("false", _("No (false)"))]
        if choices is not None:
            if not any(value == "" for value, _label in choices):
                choices.insert(0, ("", _("Choose a value")))
            self.fields["value"].widget = ChoiceSelect(
                spec=spec,
                operator=operator,
                choices=choices,
            )


class OrderingForm(forms.Form):
    field = forms.ChoiceField(label=_("Field"), required=False)
    direction = forms.ChoiceField(
        label=_("Direction"),
        choices=[("asc", _("Ascending")), ("desc", _("Descending"))],
        initial="asc",
        required=False,
    )

    def __init__(self, *args, fields, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["field"].choices = [("", _("Choose field"))] + [
            (path, field.label) for path, field in fields.items()
        ]


class QueryBuilderForm(forms.Form):
    report = forms.ChoiceField(label=_("Report"))
    columns = forms.MultipleChoiceField(
        label=_("Columns"), widget=forms.CheckboxSelectMultiple
    )
    page_size = forms.IntegerField(label=_("Rows per page"), min_value=1)

    def __init__(
        self,
        data=None,
        *,
        catalog: dict[str, ReportSpec],
        initial=None,
        structure_only=False,
    ):
        limits = get_limits()
        data = default_group_data(data, limits)
        self.groups, group_choices = make_groups(data, limits)
        initial = dict(initial or {})
        selected = data.get("report") if data is not None else initial.get("report")
        selected = selected or next(iter(sorted(catalog)), "")
        fields = catalog[selected].fields if selected in catalog else {}
        initial.setdefault("report", selected)
        initial.setdefault("columns", list(fields)[:2])
        initial.setdefault("page_size", limits.page_size)
        super().__init__(data=data, initial=initial)
        self.structure_only = structure_only
        self.catalog = catalog
        self.report_id = selected
        self.fields["report"].choices = [
            (key, str(spec.report.model._meta.verbose_name_plural).title())
            for key, spec in sorted(catalog.items())
        ]
        self.fields["columns"].choices = [
            (path, field.label) for path, field in fields.items()
        ]
        self.fields["page_size"] = forms.IntegerField(
            label=_("Rows per page"), min_value=1, max_value=limits.max_page_size
        )
        self.filters = formset_factory(
            FilterForm,
            formset=GroupedFilterFormSet,
            extra=1,
            can_delete=True,
            max_num=limits.max_filters,
            validate_max=True,
            absolute_max=limits.max_filters,
        )(
            data=data,
            prefix="filters",
            form_kwargs={"fields": fields, "group_choices": group_choices},
        )
        self.ordering = formset_factory(
            OrderingForm,
            extra=1,
            can_delete=True,
            max_num=limits.max_ordering,
            validate_max=True,
            absolute_max=limits.max_ordering,
        )(data=data, prefix="ordering", form_kwargs={"fields": fields})

    def clean(self):
        cleaned = super().clean()
        groups_valid = self.groups.is_valid()
        nodes, removed = {}, set()
        if groups_valid:
            nodes, removed = validate_structure(self.groups.cleaned_data, get_limits())
            self.filters.removed_groups = removed
        filters_valid = self.filters.is_valid()
        ordering_valid = self.ordering.is_valid()
        if self.errors or not filters_valid or not ordering_valid or not groups_valid:
            if not filters_valid or not ordering_valid or not groups_valid:
                raise ValidationError(_("Correct the conditions or ordering below."))
            return cleaned
        if self.structure_only:
            validate_structure(self.groups.cleaned_data, get_limits())
            return cleaned
        fields = self.catalog[cleaned["report"]].fields
        filters = []
        for row in self.filters.cleaned_data:
            if not row or row.get("DELETE") or (row.get("group") or "root") in removed:
                continue
            if not row.get("field"):
                if row.get("operator") or row.get("value"):
                    raise ValidationError(_("Choose a field for each condition."))
                continue
            raw = row["value"]
            if row["operator"] == "isnull" or isinstance(
                fields[row["field"]].django_field, models.BooleanField
            ):
                if raw.lower() in ("true", "false"):
                    raw = raw.lower() == "true"
            filters.append(
                {
                    "field": row["field"],
                    "operator": row["operator"],
                    "value": raw,
                    "group": row.get("group") or "root",
                }
            )
        ordering = [
            {"field": row["field"], "direction": row["direction"]}
            for row in self.ordering.cleaned_data
            if row and row.get("field") and not row.get("DELETE")
        ]
        self.payload = {
            "version": 1,
            "report": cleaned["report"],
            "columns": cleaned["columns"],
            "filters": [
                {key: row[key] for key in ("field", "operator", "value")}
                for row in filters
            ],
            "ordering": ordering,
        }
        try:
            where = build_where(nodes, removed, filters)
            if (
                len(nodes.keys() - removed) == 1
                and where["connector"] == "and"
                and not where["negated"]
            ):
                self.payload["filters"] = where["children"]
            else:
                self.payload.pop("filters")
                self.payload.update(version=2, where=where)
            self.definition = validate_definition(self.payload, self.catalog)
        except ValidationError as error:
            for control, messages in (
                error.message_dict
                if hasattr(error, "message_dict")
                else {"filters": error.messages}
            ).items():
                self.add_error(control if control in self.fields else None, messages)
        return cleaned

    @property
    def condition_groups(self):
        return display_groups(self.groups, self.filters)


def payload_form_data(payload: object, *, page_size: str) -> QueryDict:
    """Reconstruct bounded controls for display; callers validate the original JSON."""
    data = QueryDict(mutable=True)
    payload = payload if isinstance(payload, dict) else {}
    data["report"] = str(payload.get("report", ""))
    columns = payload.get("columns", [])
    data.setlist(
        "columns",
        [str(value) for value in columns] if isinstance(columns, list) else [],
    )
    data["page_size"] = page_size
    limits = get_limits()
    if payload.get("version") == 2:
        try:
            groups, filters = flatten_where(payload.get("where"), limits)
        except ValidationError:
            groups, filters = [], []
        payload = {**payload, "groups": groups, "filters": filters}
    for prefix, maximum in (
        ("groups", limits.max_groups),
        ("filters", limits.max_filters),
        ("ordering", limits.max_ordering),
    ):
        if prefix == "groups" and "groups" not in payload:
            continue
        rows = payload.get(prefix, [])
        rows = rows if isinstance(rows, list) else []
        data[f"{prefix}-TOTAL_FORMS"] = str(max(1, len(rows)))
        data[f"{prefix}-INITIAL_FORMS"] = "0"
        data[f"{prefix}-MIN_NUM_FORMS"] = "0"
        data[f"{prefix}-MAX_NUM_FORMS"] = str(maximum)
        for index, row in enumerate(rows[:maximum]):
            if not isinstance(row, dict):
                continue
            for key, value in row.items():
                if key not in (
                    "field",
                    "operator",
                    "value",
                    "direction",
                    "id",
                    "parent",
                    "connector",
                    "negated",
                    "group",
                ):
                    continue
                if key == "negated":
                    value = "on" if value is True else ""
                elif type(value) is bool:
                    value = "true" if value else "false"
                data[f"{prefix}-{index}-{key}"] = str(value)
    return data
