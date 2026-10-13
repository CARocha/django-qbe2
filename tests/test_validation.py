from copy import deepcopy
from dataclasses import replace
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from tests.fixtures import grant_view, make_orders, make_staff
from tests.models import Customer, Order


def order_payload(**changes):
    payload = {
        "version": 1,
        "report": "tests.order",
        "columns": ["number", "total"],
        "filters": [],
        "ordering": [],
    }
    payload.update(changes)
    return payload


class ValidationTests(TestCase):
    def setUp(self):
        from django_qbe2.catalog import get_catalog

        user = make_staff("alice")
        grant_view(user, Order, Customer)
        self.request = RequestFactory().get("/")
        self.request.user = user
        self.catalog = get_catalog(self.request)

    def test_exact_values(self):
        from django_qbe2.validation import validate_definition

        payload = order_payload(
            filters=[
                {"field": "total", "operator": "gte", "value": "100.01"},
                {"field": "active", "operator": "exact", "value": False},
                {"field": "quantity", "operator": "exact", "value": 0},
                {"field": "note", "operator": "exact", "value": ""},
            ]
        )
        with self.assertNumQueries(0):
            definition = validate_definition(payload, self.catalog)
        self.assertEqual(definition.filters[0].value, Decimal("100.01"))
        self.assertIs(definition.filters[1].value, False)
        self.assertEqual(definition.filters[2].value, 0)
        self.assertEqual(definition.filters[3].value, "")

    def test_text_search_fragments_do_not_require_a_complete_email_or_url(self):
        from django_qbe2.engine import build_queryset
        from django_qbe2.validation import validate_definition

        orders = make_orders(self.request.user)
        fields = self.catalog["tests.order"].fields
        for field, stored, fragment in (
            (models.EmailField(max_length=100), "alice@example.com", "@example.com"),
            (models.URLField(max_length=100), "https://example.com", "example.com"),
        ):
            fields["number"] = replace(fields["number"], django_field=field)
            Order.objects.filter(pk=orders[0].pk).update(number=stored)
            for operator in ("contains", "icontains", "startswith", "istartswith"):
                value = stored[:5] if "startswith" in operator else fragment
                with self.subTest(field=type(field).__name__, operator=operator):
                    definition = validate_definition(
                        order_payload(
                            filters=[
                                {
                                    "field": "number",
                                    "operator": operator,
                                    "value": value,
                                }
                            ]
                        ),
                        self.catalog,
                    )
                    queryset = build_queryset(definition, self.catalog, self.request)
                    self.assertEqual(
                        list(queryset.values_list("pk", flat=True)), [orders[0].pk]
                    )
            for operator, value in (
                ("contains", "x" * 101),
                ("contains", 123),
                ("exact", fragment),
            ):
                with (
                    self.subTest(operator=operator, value=value),
                    self.assertRaises(ValidationError),
                ):
                    validate_definition(
                        order_payload(
                            filters=[
                                {
                                    "field": "number",
                                    "operator": operator,
                                    "value": value,
                                }
                            ]
                        ),
                        self.catalog,
                    )

    def test_invalid_definitions_are_rejected(self):
        from django_qbe2.validation import validate_definition

        cases = [
            order_payload(version=True),
            order_payload(version=2),
            order_payload(unknown=True),
            order_payload(columns=[]),
            order_payload(columns=["number", "number"]),
            order_payload(columns=["owner__password"]),
            order_payload(ordering=[{"field": "total", "direction": "sideways"}]),
        ]
        for field, operator, value in (
            ("due_date", "isnull", "false"),
            ("total", "exact", 0.1),
            ("total", "exact", "NaN"),
            ("total", "exact", "Infinity"),
            ("quantity", "exact", 2**100),
            ("quantity", "exact", True),
            ("number", "regex", ".*"),
            ("active", "exact", "false"),
            ("reference", "exact", "bad-uuid"),
            ("due_date", "exact", "bad-date"),
        ):
            cases.append(
                order_payload(
                    filters=[
                        {
                            "field": field,
                            "operator": operator,
                            "value": value,
                        }
                    ]
                )
            )
        for payload in cases:
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                validate_definition(payload, self.catalog)

    def test_configurable_limits(self):
        from django_qbe2.validation import validate_definition

        with override_settings(
            QBE2_MAX_COLUMNS=1, QBE2_MAX_FILTERS=1, QBE2_MAX_ORDERING=1
        ):
            for changes in (
                {"columns": ["number", "total"]},
                {
                    "columns": ["number"],
                    "filters": [
                        {"field": "total", "operator": "gte", "value": "1"},
                        {"field": "total", "operator": "lte", "value": "2"},
                    ],
                },
                {
                    "columns": ["number"],
                    "ordering": [
                        {"field": "number", "direction": "asc"},
                        {"field": "total", "direction": "asc"},
                    ],
                },
            ):
                with self.subTest(changes=changes), self.assertRaises(ValidationError):
                    validate_definition(order_payload(**changes), self.catalog)

    def test_datetime_uses_active_timezone(self):
        from django_qbe2.validation import validate_definition

        payload = order_payload(
            filters=[
                {
                    "field": "created_at",
                    "operator": "gte",
                    "value": "2026-10-12T12:00:00",
                }
            ]
        )
        original = deepcopy(payload)
        with timezone.override("America/Managua"):
            value = validate_definition(payload, self.catalog).filters[0].value
        self.assertEqual(value.utcoffset().total_seconds(), -21600)
        self.assertEqual(payload, original)
