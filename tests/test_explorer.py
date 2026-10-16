from django.test import SimpleTestCase

from django_qbe2.catalog import describe_report
from django_qbe2.explorer import build_explorer
from django_qbe2.registry import Report
from tests.models import Customer, Order, Pet, Profile, Tag


class CatalogReport(Report):
    def __init__(self, model, fields):
        self.model = model
        self.fields = fields

    def get_queryset(self, request):
        return self.model._default_manager.all()


class ExplorerTests(SimpleTestCase):
    def setUp(self):
        self.reports = {
            "tests.order": CatalogReport(
                Order,
                (
                    "number",
                    "total",
                    "customer__name",
                    "customer__pets__name",
                    "customer__profile__label",
                ),
            ),
            "tests.customer": CatalogReport(
                Customer, ("name", "order__number", "profile__label")
            ),
            "tests.pet": CatalogReport(Pet, ("name", "tags__label")),
            "tests.profile": CatalogReport(Profile, ("label",)),
            "tests.tag": CatalogReport(Tag, ("label", "pets__name")),
        }
        self.catalog = {
            report_id: describe_report(report, self.reports)
            for report_id, report in self.reports.items()
        }

    def test_root_and_related_fields_are_grouped_by_owner(self):
        data = build_explorer(self.catalog["tests.order"], self.catalog)

        self.assertEqual(
            [node.id for node in data.nodes],
            ["tests.order", "tests.customer", "tests.pet", "tests.profile"],
        )
        self.assertEqual(len(data.edges), 3)
        self.assertEqual(
            len(
                {(edge.source_id, edge.accessor, edge.target_id) for edge in data.edges}
            ),
            len(data.edges),
        )
        self.assertEqual(
            [(field.path, field.owner_id) for field in data.fields],
            [
                ("number", "tests.order"),
                ("total", "tests.order"),
                ("customer__name", "tests.customer"),
                ("customer__pets__name", "tests.pet"),
                ("customer__profile__label", "tests.profile"),
            ],
        )

    def test_edges_are_deduplicated_and_describe_direction_and_cardinality(self):
        data = build_explorer(self.catalog["tests.customer"], self.catalog)
        edge = next(edge for edge in data.edges if edge.accessor == "order")

        self.assertTrue(edge.reverse)
        self.assertTrue(edge.multi_valued)
        self.assertEqual(
            (edge.source_id, edge.target_id), ("tests.customer", "tests.order")
        )
        self.assertEqual(len(data.edges), 2)
        profile_edge = next(edge for edge in data.edges if edge.accessor == "profile")
        self.assertTrue(profile_edge.reverse)
        self.assertFalse(profile_edge.multi_valued)

    def test_two_hop_field_has_connected_edges(self):
        data = build_explorer(self.catalog["tests.order"], self.catalog)

        self.assertEqual(
            [(edge.source_id, edge.target_id) for edge in data.edges],
            [
                ("tests.order", "tests.customer"),
                ("tests.customer", "tests.pet"),
                ("tests.customer", "tests.profile"),
            ],
        )

    def test_direct_and_reverse_many_to_many_edges_are_multi_valued(self):
        direct = build_explorer(self.catalog["tests.pet"], self.catalog)
        reverse = build_explorer(self.catalog["tests.tag"], self.catalog)

        self.assertTrue(direct.edges[0].multi_valued)
        self.assertFalse(direct.edges[0].reverse)
        self.assertTrue(reverse.edges[0].multi_valued)
        self.assertTrue(reverse.edges[0].reverse)

    def test_path_and_duplicate_labels_remain_distinguishable(self):
        report = CatalogReport(Order, ("number", "customer__name"))
        report.field_labels = {"number": "Name", "customer__name": "Name"}
        catalog = {
            "tests.order": describe_report(report, self.reports),
            "tests.customer": self.catalog["tests.customer"],
        }
        data = build_explorer(catalog["tests.order"], catalog)

        self.assertEqual([field.label for field in data.fields], ["Name", "Name"])
        self.assertEqual(
            [field.path for field in data.fields], ["number", "customer__name"]
        )

    def test_omits_related_nodes_edges_and_fields_missing_from_authorized_catalog(self):
        catalog = {"tests.order": self.catalog["tests.order"]}
        data = build_explorer(catalog["tests.order"], catalog)

        self.assertEqual([node.id for node in data.nodes], ["tests.order"])
        self.assertEqual(data.edges, ())
        self.assertEqual([field.path for field in data.fields], ["number", "total"])

    def test_field_eligibility_excludes_multivalued_ordering_and_summaries(self):
        data = build_explorer(self.catalog["tests.order"], self.catalog)
        scalar, multivalued = data.fields[1], data.fields[3]

        self.assertTrue(scalar.orderable)
        self.assertTrue(scalar.groupable)
        self.assertTrue(scalar.metricable)
        self.assertFalse(multivalued.orderable)
        self.assertFalse(multivalued.groupable)
        self.assertFalse(multivalued.metricable)

    def test_text_fields_are_not_numeric_summary_metrics(self):
        data = build_explorer(self.catalog["tests.order"], self.catalog)

        self.assertFalse(data.fields[0].metricable)
        self.assertTrue(data.fields[1].metricable)
