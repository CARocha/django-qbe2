import csv
import io
import json
from contextlib import contextmanager

from django import forms
from django.core.exceptions import ValidationError
from django.test import TransactionTestCase
from django.utils import timezone
from django.utils.safestring import mark_safe

from django_qbe2.catalog import get_catalog
from django_qbe2.forms import FilterForm, QueryBuilderForm
from django_qbe2.validation import validate_definition
from tests import test_engine
from tests.models import Customer, Order
from tests.test_validation import order_payload


class ChoiceFieldsTests(TransactionTestCase):
    setUp = test_engine.EngineTests.setUp

    @contextmanager
    def choices(self, model, name, values):
        field = model._meta.get_field(name)
        original = field.choices
        field.choices = values
        try:
            yield
        finally:
            field.choices = original

    def post(self, payload, **extra):
        self.client.force_login(self.alice)
        return self.client.post(
            "/qbe/results/", {"definition": json.dumps(payload), **extra}
        )

    def test_catalog_snapshots_grouped_callable_choices_per_request(self):
        values = {"Group": {0: "Zero", 1: "One"}, 2: "Two"}
        with self.choices(Order, "quantity", lambda: values):
            first = get_catalog(self.request)
            self.assertEqual(
                first["tests.order"].fields["quantity"].choices,
                ((0, "Zero"), (1, "One"), (2, "Two")),
            )
            values["Group"][0] = "Updated zero"
            second = get_catalog(self.request)
            self.assertEqual(
                second["tests.order"].fields["quantity"].choices[0],
                (0, "Updated zero"),
            )
            self.assertEqual(
                first["tests.order"].fields["quantity"].choices[0][1], "Zero"
            )

    def test_related_choices_require_target_permission(self):
        from tests.fixtures import grant_view, make_staff

        restricted = make_staff("restricted")
        grant_view(restricted, Order)
        self.client.force_login(restricted)
        with self.choices(Customer, "name", [("secret", "Hidden choice")]):
            response = self.client.get("/qbe/?report=tests.order")
        self.assertNotContains(response, "Hidden choice")

    def test_system_checks_and_hidden_fields_do_not_evaluate_callable_choices(self):
        from django_qbe2.checks import check_reports
        from tests.fixtures import grant_view, make_staff

        def unavailable_choices():
            raise AssertionError("A hidden field's choices were evaluated.")

        restricted = make_staff("restricted")
        grant_view(restricted, Order)
        self.request.user = restricted
        with self.choices(Customer, "name", unavailable_choices):
            self.assertEqual(check_reports(), [])
            self.assertNotIn(
                "customer__name", get_catalog(self.request)["tests.order"].fields
            )

    def test_server_widgets_select_equality_but_keep_search_fragments_as_text(self):
        with self.choices(Order, "number", [("A100", "First"), ("A200", "Second")]):
            fields = get_catalog(self.request)["tests.order"].fields
            for operator, widget in (
                ("exact", forms.Select),
                ("iexact", forms.Select),
                ("contains", forms.TextInput),
            ):
                with self.subTest(operator=operator):
                    row = FilterForm(
                        {"field": "number", "operator": operator, "value": "A100"},
                        fields=fields,
                    )
                    self.assertIsInstance(row.fields["value"].widget, widget)
                    if widget is forms.Select:
                        self.assertIn(
                            ("A100", "First"), list(row.fields["value"].widget.choices)
                        )

    def test_numeric_and_boolean_choices_preserve_zero_and_false(self):
        with (
            self.choices(Order, "quantity", [(0, "Zero"), (1, "One")]),
            self.choices(Order, "active", [(True, "Enabled"), (False, "Disabled")]),
        ):
            catalog = get_catalog(self.request)
            for field, raw, value in (("quantity", "0", 0), ("active", "false", False)):
                with self.subTest(field=field):
                    data = {
                        "report": "tests.order",
                        "columns": [field],
                        "page_size": "50",
                        "filters-TOTAL_FORMS": "1",
                        "filters-INITIAL_FORMS": "0",
                        "filters-0-field": field,
                        "filters-0-operator": "exact",
                        "filters-0-value": raw,
                        "ordering-TOTAL_FORMS": "0",
                        "ordering-INITIAL_FORMS": "0",
                    }
                    form = QueryBuilderForm(data, catalog=catalog)
                    self.assertIsInstance(
                        form.filters.forms[0].fields["value"].widget, forms.Select
                    )
                    self.assertTrue(form.is_valid(), form.errors)
                    self.assertEqual(form.definition.filters[0].value, value)
                    self.assertIs(type(form.definition.filters[0].value), type(value))

    def test_equality_rejects_tampered_values_but_search_and_ranges_remain_valid(self):
        with (
            self.choices(Order, "number", [("A100", "First")]),
            self.choices(Order, "quantity", [(0, "Zero"), (2, "Two")]),
        ):
            catalog = get_catalog(self.request)
            for field, operator, value in (
                ("number", "exact", "invalid"),
                ("number", "iexact", "invalid"),
                ("quantity", "exact", "1"),
            ):
                with (
                    self.subTest(field=field, operator=operator),
                    self.assertRaises(ValidationError),
                ):
                    validate_definition(
                        order_payload(
                            filters=[
                                {"field": field, "operator": operator, "value": value}
                            ]
                        ),
                        catalog,
                    )
            for field, operator, value in (
                ("number", "contains", "A"),
                ("number", "iexact", "a100"),
                ("quantity", "gte", "1"),
            ):
                with self.subTest(field=field, operator=operator):
                    validate_definition(
                        order_payload(
                            filters=[
                                {"field": field, "operator": operator, "value": value}
                            ]
                        ),
                        catalog,
                    )

    def test_labels_are_html_only_and_queries_keep_stored_values(self):
        with self.choices(
            Order, "number", [("A100", "First order"), ("A200", "Second order")]
        ):
            payload = order_payload(
                columns=["number"],
                filters=[{"field": "number", "operator": "exact", "value": "A100"}],
            )
            response = self.post(payload)
            self.assertContains(response, "First order")
            self.assertEqual(json.loads(response.context["definition_json"]), payload)
            export = self.client.post(
                "/qbe/export/", {"definition": json.dumps(payload)}
            )
            rows = list(
                csv.reader(io.StringIO(b"".join(export.streaming_content).decode()))
            )
            export.close()
            self.assertEqual(rows[1:], [["A100"]])

    def test_edit_preserves_case_insensitive_and_numeric_aliases(self):
        with (
            self.choices(Order, "number", [("A100", "First")]),
            self.choices(Order, "quantity", [(0, "Zero")]),
        ):
            for field, operator, raw, displayed in (
                ("number", "iexact", "a100", "A100"),
                ("quantity", "exact", "+0", "0"),
            ):
                with self.subTest(field=field):
                    payload = order_payload(
                        filters=[{"field": field, "operator": operator, "value": raw}]
                    )
                    response = self.post(payload, action="edit")
                    self.assertEqual(response.status_code, 200)
                    self.assertContains(
                        response, f'<option value="{displayed}" selected>'
                    )
                    self.assertEqual(response.context["form"].payload, payload)

    def test_datetime_choices_follow_the_active_timezone(self):
        import datetime

        from django_qbe2.engine import build_queryset

        local = datetime.datetime(2026, 10, 13, 12)
        with (
            timezone.override("America/Managua"),
            self.choices(Order, "created_at", [(local, "Noon")]),
        ):
            Order.objects.filter(pk=self.orders[0].pk).update(
                created_at=timezone.make_aware(local)
            )
            catalog = get_catalog(self.request)
            definition = validate_definition(
                order_payload(
                    filters=[
                        {
                            "field": "created_at",
                            "operator": "exact",
                            "value": "2026-10-13T12:00:00",
                        }
                    ]
                ),
                catalog,
            )
            self.assertEqual(
                list(
                    build_queryset(definition, catalog, self.request).values_list(
                        "pk", flat=True
                    )
                ),
                [self.orders[0].pk],
            )
            response = self.post(
                order_payload(
                    filters=[
                        {
                            "field": "created_at",
                            "operator": "exact",
                            "value": "2026-10-13T12:00:00",
                        }
                    ]
                ),
                action="edit",
            )
            self.assertContains(
                response, '<option value="2026-10-13T12:00:00-06:00" selected>'
            )

    def test_related_labels_preserve_row_authorization(self):
        with self.choices(
            Customer,
            "name",
            [
                ("Alice Customer", "Allowed customer"),
                ("Bob Customer", "Other customer"),
            ],
        ):
            response = self.post(order_payload(columns=["customer__name"]))
        self.assertContains(response, "Allowed customer")
        self.assertNotContains(response, "Other customer")

    def test_unknown_stored_values_fall_back_to_their_original_text(self):
        with self.choices(Order, "number", [("A100", "Known order")]):
            response = self.post(order_payload(columns=["number"]))
        self.assertContains(response, "Known order")
        self.assertContains(response, "A200")

    def test_choice_labels_are_plain_text_even_if_marked_safe(self):
        label = mark_safe("<script>alert(1)</script>")
        with self.choices(Order, "number", [("A100", label)]):
            response = self.post(order_payload(columns=["number"]))
            self.assertContains(response, "&lt;script&gt;alert(1)&lt;/script&gt;")
            self.assertNotContains(response, "<script>alert(1)</script>")
            edited = self.post(
                order_payload(
                    filters=[{"field": "number", "operator": "exact", "value": "A100"}]
                ),
                action="edit",
            )
            self.assertContains(edited, "&lt;script&gt;alert(1)&lt;/script&gt;")

    def test_blank_choice_and_null_operator_remain_distinct(self):
        with self.choices(Order, "due_date", [(None, "Not set")]):
            catalog = get_catalog(self.request)
            definition = validate_definition(
                order_payload(
                    filters=[{"field": "due_date", "operator": "isnull", "value": True}]
                ),
                catalog,
            )
            self.assertIs(definition.filters[0].value, True)
        with self.choices(Order, "note", [("", "No note"), ("gift", "Gift")]):
            response = self.post(
                order_payload(
                    columns=["note"],
                    filters=[{"field": "note", "operator": "exact", "value": ""}],
                )
            )
            self.assertContains(response, "No note")
            edited = self.post(
                order_payload(
                    filters=[{"field": "note", "operator": "exact", "value": ""}]
                ),
                action="edit",
            )
            self.assertContains(edited, '<option value="" selected>No note</option>')

    def test_null_only_and_empty_declarations_reject_nonmember_equality(self):
        for choices in ([(None, "Not set")], lambda: []):
            with (
                self.subTest(choices=choices),
                self.choices(Order, "due_date", choices),
            ):
                catalog = get_catalog(self.request)
                with self.assertRaises(ValidationError):
                    validate_definition(
                        order_payload(
                            filters=[
                                {
                                    "field": "due_date",
                                    "operator": "exact",
                                    "value": "2026-10-13",
                                }
                            ]
                        ),
                        catalog,
                    )
                definition = validate_definition(
                    order_payload(
                        filters=[
                            {"field": "due_date", "operator": "isnull", "value": True}
                        ]
                    ),
                    catalog,
                )
                self.assertIs(definition.filters[0].value, True)
                form = FilterForm(
                    {"field": "due_date", "operator": "exact", "value": ""},
                    fields=catalog["tests.order"].fields,
                )
                self.assertIsInstance(form.fields["value"].widget, forms.Select)

    def test_empty_results_explain_conditions_and_row_policy_without_leaking_counts(
        self,
    ):
        response = self.post(
            order_payload(
                filters=[{"field": "number", "operator": "exact", "value": "missing"}]
            )
        )
        self.assertContains(
            response, "Your report's access policy also limits which rows you can see."
        )
        self.assertContains(response, "Edit the report to adjust its conditions.")
        self.assertNotContains(response, "B100")
