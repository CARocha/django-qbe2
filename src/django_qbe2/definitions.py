from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

type Scalar = str | int | Decimal | bool | date | datetime | UUID | None


@dataclass(frozen=True)
class FilterSpec:
    field: str
    operator: str
    value: Scalar


@dataclass(frozen=True)
class ConditionGroup:
    connector: Literal["and", "or"]
    negated: bool
    children: tuple[FilterSpec | ConditionGroup, ...]


@dataclass(frozen=True)
class OrderingSpec:
    field: str
    direction: Literal["asc", "desc"]


@dataclass(frozen=True)
class QueryDefinition:
    version: Literal[1, 2]
    report: str
    columns: tuple[str, ...]
    filters: tuple[FilterSpec, ...]
    ordering: tuple[OrderingSpec, ...]
    where: ConditionGroup | None = None
