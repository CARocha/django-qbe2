"""Build an authorized, presentation-only projection of registered report fields."""

from dataclasses import dataclass

from django_qbe2.catalog import ReportSpec


@dataclass(frozen=True)
class ExplorerNode:
    id: str
    label: str
    is_root: bool = False


@dataclass(frozen=True)
class ExplorerEdge:
    id: str
    source_id: str
    target_id: str
    accessor: str
    label: str
    reverse: bool
    multi_valued: bool


@dataclass(frozen=True)
class ExplorerField:
    path: str
    label: str
    owner_id: str
    owner_label: str
    multi_valued: bool
    orderable: bool
    groupable: bool


@dataclass(frozen=True)
class ExplorerData:
    root_id: str
    nodes: tuple[ExplorerNode, ...]
    edges: tuple[ExplorerEdge, ...]
    fields: tuple[ExplorerField, ...]


def build_explorer(report: ReportSpec, catalog: dict[str, ReportSpec]) -> ExplorerData:
    """Project only fields whose complete relation path is in the authorized catalog."""
    root_model = report.report.model
    nodes = {
        report.id: ExplorerNode(report.id, str(root_model._meta.verbose_name), True)
    }
    edges = {}
    fields = []

    for field in report.fields.values():
        if any(step.target_report_id not in catalog for step in field.relations):
            continue

        source_id = report.id
        for step in field.relations:
            target_id = step.target_report_id
            if target_id not in nodes:
                nodes[target_id] = ExplorerNode(
                    target_id, str(step.target_model._meta.verbose_name)
                )
            edge_id = "__".join((source_id, step.accessor, target_id))
            edges.setdefault(
                edge_id,
                ExplorerEdge(
                    id=edge_id,
                    source_id=source_id,
                    target_id=target_id,
                    accessor=step.accessor,
                    label=str(step.relation_field.verbose_name),
                    reverse=step.reverse,
                    multi_valued=step.multi_valued,
                ),
            )
            source_id = target_id

        owner = field.relations[-1].target_model if field.relations else root_model
        fields.append(
            ExplorerField(
                path=field.path,
                label=field.label,
                owner_id=owner._meta.label_lower,
                owner_label=str(owner._meta.verbose_name),
                multi_valued=field.multi_valued,
                orderable=not field.multi_valued,
                groupable=not field.multi_valued,
            )
        )

    return ExplorerData(
        root_id=report.id,
        nodes=tuple(nodes.values()),
        edges=tuple(edges.values()),
        fields=tuple(fields),
    )
