from copy import deepcopy

from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.test import TestCase, override_settings

from django_qbe2.validation import validate_definition
from tests import test_validation
from tests.test_validation import order_payload


def leaf(field="number", value="A100", operator="exact"):
    return {"field": field, "operator": operator, "value": value}


def group(*children, connector="and", negated=False):
    return {"connector": connector, "negated": negated, "children": list(children)}


def grouped_payload(where=None):
    payload = order_payload()
    payload.pop("filters")
    return {**payload, "version": 2, "where": group(leaf()) if where is None else where}


class ConditionValidationTests(TestCase):
    setUp = test_validation.ValidationTests.setUp

    def test_accepts_mixed_tree_and_discovers_all_leaves(self):
        definition = validate_definition(
            grouped_payload(
                group(
                    group(leaf(), leaf(value="A200"), connector="or"),
                    group(leaf(value="A300"), negated=True),
                )
            ),
            self.catalog,
        )
        self.assertEqual(definition.version, 2)
        self.assertEqual(len(definition.filters), 3)
        self.assertEqual(definition.where.children[0].connector, "or")
        self.assertTrue(definition.where.children[1].negated)

    def test_empty_root_only(self):
        self.assertEqual(
            validate_definition(grouped_payload(group()), self.catalog).filters, ()
        )
        for where in (group(connector="or"), group(negated=True), group(group())):
            with self.subTest(where=where), self.assertRaises(ValidationError):
                validate_definition(grouped_payload(where), self.catalog)

    def test_rejects_invalid_nodes_and_every_unauthorized_branch(self):
        malformed = [
            group(leaf(), leaf(field="owner"), connector="or"),
            group(leaf(), connector="xor"),
            group(leaf(), negated=1),
            {**group(leaf()), "extra": True},
            group({**leaf(), "sql": "DELETE"}),
            {**group(leaf()), "children": "bad"},
            group([]),
            leaf(),
        ]
        for where in malformed:
            with self.subTest(where=where), self.assertRaises(ValidationError):
                validate_definition(grouped_payload(where), self.catalog)
        for version in (True, 3, "2"):
            with self.subTest(version=version), self.assertRaises(ValidationError):
                validate_definition(
                    {**grouped_payload(), "version": version}, self.catalog
                )

    def test_global_budgets_and_exact_boundaries(self):
        validate_definition(
            grouped_payload(group(*[leaf() for _ in range(20)])), self.catalog
        )
        validate_definition(
            grouped_payload(group(*[group(leaf()) for _ in range(9)])), self.catalog
        )
        validate_definition(grouped_payload(group(group(group(leaf())))), self.catalog)
        for where in (
            group(*[leaf() for _ in range(21)]),
            group(*[group(leaf()) for _ in range(10)]),
            group(group(group(group(leaf())))),
        ):
            with self.subTest(where=where), self.assertRaises(ValidationError):
                validate_definition(grouped_payload(where), self.catalog)
        with override_settings(QBE2_MAX_FILTERS=2):
            with self.assertRaises(ValidationError):
                validate_definition(
                    grouped_payload(group(group(leaf(), leaf()), leaf())), self.catalog
                )

    def test_bad_group_settings_and_deep_input_fail_safely(self):
        for setting in ("QBE2_MAX_GROUPS", "QBE2_MAX_GROUP_DEPTH"):
            for value in (0, -1, True):
                with (
                    override_settings(**{setting: value}),
                    self.assertRaises(ImproperlyConfigured),
                ):
                    validate_definition(grouped_payload(), self.catalog)
        where = group(leaf())
        for _ in range(1500):
            where = group(where)
        with self.assertRaises(ValidationError):
            validate_definition(grouped_payload(where), self.catalog)

    def test_v1_is_unchanged_and_payload_is_not_modified(self):
        payload = grouped_payload()
        original = deepcopy(payload)
        validate_definition(payload, self.catalog)
        self.assertEqual(payload, original)
        old = validate_definition(order_payload(), self.catalog)
        self.assertEqual(old.version, 1)
        self.assertIsNone(old.where)
