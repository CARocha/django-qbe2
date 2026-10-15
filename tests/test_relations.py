from django_qbe2.catalog import get_catalog
from django_qbe2.engine import build_queryset
from django_qbe2.validation import validate_definition
from tests.models import Customer, Order
from tests.test_engine import EngineTests
from tests.test_validation import order_payload


class RelationTests(EngineTests):
    def test_inaccessible_customer_excludes_order(self):
        foreign = Customer.objects.get(owner=self.bob)
        Order.objects.filter(pk=self.orders[0].pk).update(customer=foreign)
        Order.objects.filter(pk=self.orders[1].pk).update(customer=None)
        for changes in (
            {"columns": ["number", "customer__name"]},
            {"ordering": [{"field": "customer__name", "direction": "asc"}]},
            {
                "filters": [
                    {"field": "customer__name", "operator": "contains", "value": "Bob"}
                ]
            },
        ):
            with self.subTest(changes=changes):
                queryset = self.query(**changes)
                numbers = list(queryset.values_list("number", flat=True))
                self.assertNotIn("A100", numbers)
                if "filters" not in changes:
                    self.assertEqual(numbers, ["A200"])

    def test_to_field_uses_target_key(self):
        foreign = Customer.objects.get(owner=self.bob)
        Order.objects.filter(pk=self.orders[0].pk).update(customer_by_code=foreign)
        queryset = self.query(columns=["customer_by_code__code"])
        self.assertEqual(
            list(queryset.values_list("customer_by_code__code", flat=True)), ["ALICE"]
        )

    def test_one_to_one_does_not_duplicate_rows(self):
        from django_qbe2.catalog import get_catalog
        from tests.fixtures import grant_view
        from tests.models import Profile

        customer = Customer.objects.get(owner=self.alice)
        Profile.objects.create(customer=customer, label="Primary")
        grant_view(self.alice, Profile)
        for name in ("_perm_cache", "_user_perm_cache"):
            self.alice.__dict__.pop(name, None)
        catalog = get_catalog(self.request)
        definition = validate_definition(
            order_payload(report="tests.profile", columns=["label", "customer__name"]),
            catalog,
        )
        queryset = build_queryset(definition, catalog, self.request)
        self.assertEqual(list(queryset.values_list("label", flat=True)), ["Primary"])

    def test_each_single_related_hop_requires_its_row_scope(self):
        from tests.fixtures import grant_view
        from tests.models import Profile

        customer = Customer.objects.get(owner=self.alice)
        Profile.objects.create(customer=customer, label="Primary")
        grant_view(self.alice, Profile)
        for name in ("_perm_cache", "_user_perm_cache"):
            self.alice.__dict__.pop(name, None)
        self.catalog = get_catalog(self.request)
        profile_report = self.catalog["tests.profile"].report
        original = profile_report.get_queryset
        try:
            profile_report.get_queryset = lambda request: Profile.objects.none()
            queryset = self.query(columns=["number", "customer__profile__label"])
        finally:
            profile_report.get_queryset = original

        self.assertEqual(list(queryset), [])


class MultiValuedRelationTests(EngineTests):
    def setUp(self):
        super().setUp()
        from tests.fixtures import grant_view
        from tests.models import Pet, Tag

        grant_view(self.alice, Pet, Tag)
        for name in ("_perm_cache", "_user_perm_cache"):
            self.alice.__dict__.pop(name, None)
        self.catalog = get_catalog(self.request)
        self.customer = Customer.objects.get(owner=self.alice)
        self.milo = Pet.objects.create(customer=self.customer, name="Milo")
        self.luna = Pet.objects.create(customer=self.customer, name="Luna")

    def test_and_leaves_can_match_different_related_objects(self):
        queryset = self.query(
            filters=[
                {
                    "field": "customer__pets__name",
                    "operator": "exact",
                    "value": "Milo",
                },
                {
                    "field": "customer__pets__name",
                    "operator": "exact",
                    "value": "Luna",
                },
            ]
        )

        self.assertEqual(
            list(queryset.values_list("number", flat=True)), ["A100", "A200"]
        )

    def test_or_and_not_use_root_level_existential_predicates(self):
        from tests.test_condition_validation import group, grouped_payload, leaf

        for where, expected in (
            (
                group(
                    leaf("customer__pets__name", "Milo"),
                    leaf("customer__pets__name", "Luna"),
                    connector="or",
                ),
                ["A100", "A200"],
            ),
            (group(leaf("customer__pets__name", "Milo"), negated=True), []),
        ):
            definition = validate_definition(grouped_payload(where), self.catalog)
            with self.subTest(where=where):
                queryset = build_queryset(definition, self.catalog, self.request)
                self.assertEqual(
                    list(queryset.values_list("number", flat=True)), expected
                )

    def test_hidden_intermediate_rows_do_not_match_nested_filters(self):
        customer_report = self.catalog["tests.customer"].report
        original = customer_report.get_queryset
        try:
            customer_report.get_queryset = lambda request: Customer.objects.none()
            queryset = self.query(
                filters=[
                    {
                        "field": "customer__pets__name",
                        "operator": "exact",
                        "value": "Milo",
                    }
                ]
            )
        finally:
            customer_report.get_queryset = original

        self.assertEqual(list(queryset), [])

    def test_hidden_terminal_rows_do_not_match_nested_filters(self):
        pet_report = self.catalog["tests.pet"].report
        original = pet_report.get_queryset
        try:
            pet_report.get_queryset = lambda request: self.milo.__class__.objects.none()
            queryset = self.query(
                filters=[
                    {
                        "field": "customer__pets__name",
                        "operator": "exact",
                        "value": "Milo",
                    }
                ]
            )
        finally:
            pet_report.get_queryset = original

        self.assertEqual(list(queryset), [])

    def test_many_to_many_filter_matches_each_root_once(self):
        from tests.models import Pet, Tag

        Pet.objects.filter(pk=self.milo.pk).update(name="Milo")
        Pet.objects.filter(pk=self.luna.pk).update(name="Luna")
        first = Tag.objects.create(label="friendly")
        second = Tag.objects.create(label="furry")
        self.milo.tags.add(first, second)
        definition = validate_definition(
            order_payload(
                report="tests.pet",
                columns=["name"],
                filters=[
                    {"field": "tags__label", "operator": "contains", "value": "y"}
                ],
            ),
            self.catalog,
        )

        queryset = build_queryset(definition, self.catalog, self.request)

        self.assertEqual(list(queryset.values_list("name", flat=True)), ["Milo"])

    def test_reverse_many_to_many_filter_matches_each_root_once(self):
        from tests.models import Tag

        first = Tag.objects.create(label="friendly")
        second = Tag.objects.create(label="furry")
        self.milo.tags.add(first, second)
        definition = validate_definition(
            order_payload(
                report="tests.tag",
                columns=["label"],
                filters=[{"field": "pets__name", "operator": "exact", "value": "Milo"}],
            ),
            self.catalog,
        )

        queryset = build_queryset(definition, self.catalog, self.request)

        self.assertEqual(
            list(queryset.values_list("label", flat=True)), ["friendly", "furry"]
        )

    def test_multi_valued_paths_cannot_order_rows(self):
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            validate_definition(
                order_payload(
                    ordering=[{"field": "customer__pets__name", "direction": "asc"}]
                ),
                self.catalog,
            )
