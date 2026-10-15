"""Bounded condition trees, independent of database execution."""

from collections.abc import Callable, Iterator

from django.core.exceptions import ValidationError

from django_qbe2.definitions import ConditionGroup, FilterSpec
from django_qbe2.limits import Limits


def validate_group(
    raw: object, *, limits: Limits, validate_leaf: Callable[[object], FilterSpec]
) -> ConditionGroup:
    groups = leaves = 0

    def visit(node: object, depth: int) -> ConditionGroup:
        nonlocal groups, leaves
        groups += 1
        if depth > limits.max_group_depth or groups > limits.max_groups:
            raise ValidationError(
                {"filters": "The condition group limit was exceeded."}
            )
        if not isinstance(node, dict) or set(node) != {
            "connector",
            "negated",
            "children",
        }:
            raise ValidationError({"filters": "Use a complete condition group."})
        connector, negated, children = (
            node["connector"],
            node["negated"],
            node["children"],
        )
        if connector not in ("and", "or") or type(negated) is not bool:
            raise ValidationError(
                {"filters": "Choose AND or OR and a boolean negation."}
            )
        if (
            not isinstance(children, list)
            or len(children) > limits.max_filters + limits.max_groups
        ):
            raise ValidationError({"filters": "Use a bounded list of conditions."})
        if not children and (depth != 1 or connector != "and" or negated):
            raise ValidationError(
                {"filters": "Only the unnegated AND root may be empty."}
            )
        parsed = []
        for child in children:
            if isinstance(child, dict) and "children" in child:
                parsed.append(visit(child, depth + 1))
            else:
                leaves += 1
                if leaves > limits.max_filters:
                    raise ValidationError(
                        {"filters": f"Use at most {limits.max_filters} filters."}
                    )
                parsed.append(validate_leaf(child))
        return ConditionGroup(connector, negated, tuple(parsed))

    return visit(raw, 1)


def iter_filters(group: ConditionGroup) -> Iterator[FilterSpec]:
    for child in group.children:
        if isinstance(child, FilterSpec):
            yield child
        else:
            yield from iter_filters(child)
