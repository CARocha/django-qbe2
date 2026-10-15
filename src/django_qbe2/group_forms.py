"""Bounded form metadata for visible condition groups."""

from django import forms
from django.core.exceptions import ValidationError
from django.forms import BaseFormSet, formset_factory
from django.utils.translation import gettext_lazy as _

from django_qbe2.limits import Limits


class GroupedFilterFormSet(BaseFormSet):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.removed_groups = set()

    def _should_delete_form(self, form):
        # Implicit subtree removal must never alter the submitted checkbox state.
        return form[
            "group"
        ].value() in self.removed_groups or super()._should_delete_form(form)


class GroupForm(forms.Form):
    id = forms.RegexField(
        regex=r"^(root|g[0-9]+)$", max_length=64, widget=forms.HiddenInput
    )
    parent = forms.ChoiceField(label=_("Parent group"), required=False)
    connector = forms.ChoiceField(
        label=_("Match"),
        choices=[("and", _("Match all (AND)")), ("or", _("Match any (OR)"))],
    )
    negated = forms.BooleanField(label=_("Exclude this group (NOT)"), required=False)

    def __init__(self, *args, group_choices, **kwargs):
        super().__init__(*args, **kwargs)
        identity = (
            self.data.get(self.add_prefix("id"))
            if self.is_bound
            else self.initial.get("id")
        )
        self.fields["parent"].choices = [("", _("No parent (root only)"))] + [
            choice for choice in group_choices if choice[0] != identity
        ]
        if identity == "root":
            self.fields["parent"].widget = forms.HiddenInput()


def default_group_data(data, limits: Limits):
    if data is None or "groups-TOTAL_FORMS" in data:
        return data
    data = data.copy()
    data.update(
        {
            "groups-TOTAL_FORMS": "1",
            "groups-INITIAL_FORMS": "0",
            "groups-MAX_NUM_FORMS": str(limits.max_groups),
            "groups-0-id": "root",
            "groups-0-parent": "",
            "groups-0-connector": "and",
        }
    )
    return data


def make_groups(data, limits: Limits):
    identifiers = ["root"]
    if data is not None:
        for index in range(limits.max_groups):
            identity = data.get(f"groups-{index}-id")
            if identity and identity not in identifiers:
                identifiers.append(identity)
    choices = [
        (
            identity,
            _("All conditions")
            if identity == "root"
            else _("Group %(id)s") % {"id": identity},
        )
        for identity in identifiers
    ]
    formset = formset_factory(
        GroupForm,
        extra=0,
        can_delete=True,
        max_num=limits.max_groups,
        validate_max=True,
        absolute_max=limits.max_groups,
    )(
        data=data,
        prefix="groups",
        initial=[{"id": "root", "parent": "", "connector": "and"}],
        form_kwargs={"group_choices": choices},
    )
    for form in formset:
        form.empty_permitted = False
        if form["id"].value() == "root":
            form.fields["DELETE"].widget = forms.HiddenInput()
        else:
            form.fields["DELETE"].label = _("Remove group and its conditions")
    return formset, choices


def validate_structure(rows, limits: Limits):
    nodes = {}
    for row in rows:
        identity = row.get("id")
        if not identity or identity in nodes:
            raise ValidationError(_("Use distinct condition group identifiers."))
        nodes[identity] = row
    root = nodes.get("root")
    if not root or root.get("parent") or root.get("DELETE"):
        raise ValidationError(_("Keep one root group without a parent."))
    for identity in nodes:
        seen = set()
        current = identity
        while current != "root":
            if current not in nodes or current in seen:
                raise ValidationError(
                    _("Every group must belong to the root without cycles.")
                )
            seen.add(current)
            current = nodes[current].get("parent")
            if len(seen) >= limits.max_group_depth:
                raise ValidationError(
                    _("The condition group depth limit was exceeded.")
                )
    removed = set()
    for identity in nodes:
        current = identity
        while current:
            if nodes[current].get("DELETE"):
                removed.add(identity)
                break
            current = nodes[current].get("parent")
    return nodes, removed


def build_where(nodes, removed, filters):
    branches = {
        identity: {
            "connector": row["connector"],
            "negated": row.get("negated", False),
            "children": [],
        }
        for identity, row in nodes.items()
        if identity not in removed
    }
    for row in filters:
        identity = row.get("group") or "root"
        if identity not in nodes:
            raise ValidationError(_("Choose an available group for each condition."))
        if identity not in removed:
            branches[identity]["children"].append(
                {key: row[key] for key in ("field", "operator", "value")}
            )
    for identity, row in nodes.items():
        if identity != "root" and identity not in removed:
            branches[row["parent"]]["children"].append(branches[identity])
    return branches["root"]


def flatten_where(where, limits: Limits):
    groups, filters = [], []

    def visit(node, parent, depth):
        if depth > limits.max_group_depth or len(groups) >= limits.max_groups:
            raise ValidationError("Condition groups exceed the configured limits.")
        if (
            not isinstance(node, dict)
            or set(node) != {"connector", "negated", "children"}
            or not isinstance(node["children"], list)
        ):
            raise ValidationError("Invalid condition group.")
        identity = "root" if not groups else f"g{len(groups)}"
        groups.append(
            {
                "id": identity,
                "parent": parent,
                "connector": node["connector"],
                "negated": node["negated"],
            }
        )
        for child in node["children"]:
            if isinstance(child, dict) and "children" in child:
                visit(child, identity, depth + 1)
            elif isinstance(child, dict) and len(filters) < limits.max_filters:
                filters.append({**child, "group": identity})
            else:
                raise ValidationError("Invalid or excessive conditions.")

    visit(where, "", 1)
    return groups, filters


def display_groups(groups, filters):
    """Render even invalid metadata without following untrusted cycles."""
    nodes = {}
    for form in groups:
        identity = form["id"].value()
        if identity not in nodes:
            nodes[identity] = {
                "id": identity,
                "form": form,
                "filters": [],
                "children": [],
                "parent": form["parent"].value(),
            }
    root = nodes.get("root") or {
        "id": "root",
        "form": None,
        "filters": [],
        "children": [],
    }
    for form in filters:
        target = nodes.get(form["group"].value() or "root", root)
        target["filters"].append(form)
    attached = {"root"}
    for _iteration in range(len(nodes)):
        for identity, node in nodes.items():
            parent = node.get("parent")
            if identity not in attached and parent in attached and parent in nodes:
                nodes[parent]["children"].append(node)
                attached.add(identity)
    for identity, node in nodes.items():
        if identity not in attached:
            root["children"].append(node)
    return root


def compact_controls(data, groups, filters, removed, limits: Limits):
    """Reclaim deleted controls while preserving unfinished active inputs."""
    compacted = data.copy()
    for prefix, formset, maximum, keys in (
        ("groups", groups, limits.max_groups, ("id", "parent", "connector", "negated")),
        (
            "filters",
            filters,
            limits.max_filters,
            ("group", "field", "operator", "value"),
        ),
    ):
        management = formset.management_form
        if not management.is_valid():
            raise ValidationError(_("Invalid condition controls."))
        total = management.cleaned_data["TOTAL_FORMS"]
        initial = management.cleaned_data["INITIAL_FORMS"]
        if not 0 <= initial <= total <= maximum:
            raise ValidationError(_("The condition limit was exceeded."))
        rows = []
        for index in range(total):
            identity = (
                data.get(f"{prefix}-{index}-id")
                if prefix == "groups"
                else data.get(f"{prefix}-{index}-group") or "root"
            )
            deleted = forms.CheckboxInput().value_from_datadict(
                data, {}, f"{prefix}-{index}-DELETE"
            )
            if identity in removed or deleted:
                continue
            rows.append(
                {
                    key: data[f"{prefix}-{index}-{key}"]
                    for key in keys
                    if f"{prefix}-{index}-{key}" in data
                }
            )
        for key in list(compacted):
            if key.startswith(f"{prefix}-"):
                del compacted[key]
        compacted[f"{prefix}-TOTAL_FORMS"] = str(len(rows))
        compacted[f"{prefix}-INITIAL_FORMS"] = "0"
        compacted[f"{prefix}-MIN_NUM_FORMS"] = "0"
        compacted[f"{prefix}-MAX_NUM_FORMS"] = str(maximum)
        for index, row in enumerate(rows):
            for key, value in row.items():
                compacted[f"{prefix}-{index}-{key}"] = value
    return compacted
