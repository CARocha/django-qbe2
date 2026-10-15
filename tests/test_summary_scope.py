from unittest import skipUnless

from django.db import connection
from django.db.models import Count
from django.test import RequestFactory, TestCase

from django_qbe2.catalog import get_catalog
from django_qbe2.validation import validate_definition
from tests.fixtures import grant_view, make_orders, make_staff
from tests.models import Customer, Order
from tests.test_summary_validation import summary_payload
from tests.test_validation import order_payload


class SummaryScopeTests(TestCase):
    def setUp(self):
        self.alice = make_staff("scope-alice")
        self.bob = make_staff("scope-bob")
        grant_view(self.alice, Order, Customer)
        self.orders = make_orders(self.alice)
        self.bob_orders = make_orders(self.bob)
        self.request = RequestFactory().get("/")
        self.request.user = self.alice
        self.catalog = get_catalog(self.request)

    def definition(self, **changes):
        return validate_definition(summary_payload(**changes), self.catalog)

    def test_shared_scope_matches_row_filters_without_result_ordering(self):
        from django_qbe2.engine import build_queryset, build_scoped_queryset

        where = {
            "connector": "and",
            "negated": False,
            "children": [{"field": "total", "operator": "gte", "value": "150.00"}],
        }
        summary = self.definition(where=where)
        row = validate_definition(
            order_payload(
                filters=[{"field": "total", "operator": "gte", "value": "150.00"}]
            ),
            self.catalog,
        )

        scoped = build_scoped_queryset(summary, self.catalog, self.request)

        self.assertEqual(scoped.query.order_by, ())
        self.assertEqual(
            list(scoped.values_list("pk", flat=True)),
            list(
                build_queryset(row, self.catalog, self.request).values_list(
                    "pk", flat=True
                )
            ),
        )

    def test_related_guard_is_outside_or_and_not_predicates(self):
        from django_qbe2.engine import build_scoped_queryset

        foreign = Customer.objects.get(owner=self.bob)
        Order.objects.filter(pk=self.orders[0].pk).update(customer=foreign)
        where = {
            "connector": "or",
            "negated": True,
            "children": [
                {"field": "number", "operator": "exact", "value": "never"},
                {
                    "field": "customer__name",
                    "operator": "contains",
                    "value": "never",
                },
            ],
        }
        definition = self.definition(where=where, group_by=["customer__name"])

        queryset = build_scoped_queryset(definition, self.catalog, self.request)

        self.assertEqual(
            list(queryset.values_list("pk", flat=True)), [self.orders[1].pk]
        )

    def test_related_metric_path_also_requires_target_scope(self):
        from django_qbe2.definitions import MetricSpec, SummaryDefinition
        from django_qbe2.engine import build_scoped_queryset

        foreign = Customer.objects.get(owner=self.bob)
        Order.objects.filter(pk=self.orders[0].pk).update(customer=foreign)
        base = self.definition()
        definition = SummaryDefinition(
            3,
            base.report,
            base.where,
            (),
            (MetricSpec("m1", "sum", "customer__name"),),
            (),
        )

        queryset = build_scoped_queryset(definition, self.catalog, self.request)

        self.assertEqual(
            list(queryset.values_list("pk", flat=True)), [self.orders[1].pk]
        )

    def test_canonical_source_deduplicates_policy_joins(self):
        from django_qbe2.engine import build_summary_source

        report = self.catalog["tests.order"].report
        original = report.get_queryset
        try:
            report.get_queryset = lambda request: Order.objects.filter(
                owner=request.user,
                customer__coded_orders__isnull=False,
            )
            queryset = build_summary_source(
                self.definition(), self.catalog, self.request
            )
            self.assertEqual(
                list(queryset.values_list("pk", flat=True)),
                [order.pk for order in self.orders],
            )
        finally:
            report.get_queryset = original

    def test_canonical_source_preserves_annotated_and_distinct_scope(self):
        from django_qbe2.engine import build_summary_source

        report = self.catalog["tests.order"].report
        original = report.get_queryset
        try:
            report.get_queryset = lambda request: (
                Order.objects.filter(owner=request.user)
                .annotate(related_orders=Count("customer__coded_orders"))
                .filter(related_orders__gte=2)
                .order_by("pk")
                .distinct()
            )
            queryset = build_summary_source(
                self.definition(), self.catalog, self.request
            )
            self.assertEqual(
                list(queryset.values_list("pk", flat=True)),
                [order.pk for order in self.orders],
            )
        finally:
            report.get_queryset = original


class MultiValuedSummaryScopeTests(TestCase):
    def test_multi_valued_filter_counts_each_root_once(self):
        from django.test import RequestFactory

        from django_qbe2.catalog import get_catalog
        from django_qbe2.engine import build_summary_source
        from django_qbe2.execution import execute_summary
        from tests.fixtures import grant_view, make_orders, make_staff
        from tests.models import Customer, Order, Pet, Tag
        from tests.test_summary_validation import summary_payload

        user = make_staff("multi-summary")
        grant_view(user, Customer, Order, Pet, Tag)
        orders = make_orders(user)
        customer = Customer.objects.get(owner=user)
        Pet.objects.create(customer=customer, name="Milo")
        Pet.objects.create(customer=customer, name="Milo")
        request = RequestFactory().get("/")
        request.user = user
        catalog = get_catalog(request)
        payload = summary_payload(
            where={
                "connector": "and",
                "negated": False,
                "children": [
                    {
                        "field": "customer__pets__name",
                        "operator": "exact",
                        "value": "Milo",
                    }
                ],
            }
        )
        definition = validate_definition(payload, catalog)

        result = execute_summary(
            build_summary_source(definition, catalog, request), definition, catalog
        )

        self.assertEqual(result.source_count, len(orders))
        self.assertEqual(result.rows[0]["metric:m1"], len(orders))

        pet_report = catalog["tests.pet"].report
        original = pet_report.get_queryset
        try:
            pet_report.get_queryset = lambda request: Pet.objects.none()
            restricted_source = build_summary_source(definition, catalog, request)
            restricted_result = execute_summary(restricted_source, definition, catalog)
        finally:
            pet_report.get_queryset = original

        self.assertEqual(restricted_result.source_count, 0)
        self.assertEqual(restricted_result.rows[0]["metric:m1"], 0)

    def test_multi_valued_paths_cannot_group_summary_rows(self):
        from django.core.exceptions import ValidationError
        from django.test import RequestFactory

        from django_qbe2.catalog import get_catalog
        from tests.fixtures import grant_view, make_orders, make_staff
        from tests.models import Customer, Order, Pet, Tag
        from tests.test_summary_validation import summary_payload

        user = make_staff("multi-summary-group")
        grant_view(user, Customer, Order, Pet, Tag)
        make_orders(user)
        customer = Customer.objects.get(owner=user)
        Pet.objects.create(customer=customer, name="Milo")
        request = RequestFactory().get("/")
        request.user = user
        catalog = get_catalog(request)
        with self.assertRaises(ValidationError):
            validate_definition(
                summary_payload(group_by=["customer__pets__name"]), catalog
            )

    @skipUnless(connection.vendor == "postgresql", "PostgreSQL DISTINCT ON contract")
    def test_canonical_source_preserves_distinct_on_policy(self):
        from django_qbe2.engine import build_summary_source

        report = self.catalog["tests.order"].report
        original = report.get_queryset
        try:
            report.get_queryset = lambda request: (
                Order.objects.filter(owner=request.user)
                .order_by("owner_id", "pk")
                .distinct("owner_id")
            )
            queryset = build_summary_source(
                self.definition(), self.catalog, self.request
            )
            self.assertEqual(
                list(queryset.values_list("pk", flat=True)), [self.orders[0].pk]
            )
        finally:
            report.get_queryset = original
