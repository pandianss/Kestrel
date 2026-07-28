"""Data models and seams for corporate relationships, segment reporting, and industries.

Enforces point-in-time constraints (publish_date >= period_end) and valid values.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Protocol, runtime_checkable


class RelationType(Enum):
    PARENT = "parent"
    SUBSIDIARY = "subsidiary"
    ASSOCIATE = "associate"
    JOINT_VENTURE = "jv"
    PROMOTER_GROUP = "promoter"


@dataclass(frozen=True)
class CorporateRelation:
    """A directed, point-in-time relation in a corporate tree."""
    source_symbol: str
    target_name_or_symbol: str
    relation_type: RelationType
    holding_pct: float            # e.g., 0.51 for 51% stake
    publish_date: date            # when it was publicly filed/disclosed
    source: str = ""              # provenance: where this was disclosed

    def __post_init__(self) -> None:
        if not (0.0 <= self.holding_pct <= 1.0):
            raise ValueError(f"holding_pct must be in [0.0, 1.0], got {self.holding_pct}")


@dataclass(frozen=True)
class ProductSegment:
    """Discloses the percentage of revenue derived from a segment."""
    symbol: str
    segment_name: str
    revenue_pct: float            # e.g., 0.15 for 15% revenue share
    period_end: date
    publish_date: date            # when this was publicly filed/disclosed
    source: str = ""              # provenance: the filing/URL this came from

    def __post_init__(self) -> None:
        if not (0.0 <= self.revenue_pct <= 1.0):
            raise ValueError(f"revenue_pct must be in [0.0, 1.0], got {self.revenue_pct}")
        if self.publish_date < self.period_end:
            raise ValueError(
                f"{self.symbol}: publish_date {self.publish_date} precedes "
                f"period_end {self.period_end} — that is look-ahead, not data."
            )


@dataclass(frozen=True)
class IndustryMapping:
    """Point-in-time classification of a company's sector."""
    symbol: str
    primary_industry: str         # e.g., "Financial Services"
    sub_sector: str               # e.g., "Private Sector Banks" ("" if not verifiable)
    related_industries: list[str] # e.g., ["IT Services"] ([] if not verifiable)
    effective_from: date          # the date this mapping took effect
    source: str = ""              # provenance: where the classification came from


@runtime_checkable
class RelationsSource(Protocol):
    def relations_asof(self, symbol: str, d: date) -> list[CorporateRelation]:
        """All corporate relationships of `symbol` public on or before `d`."""
        ...

    def segments_asof(self, symbol: str, d: date) -> list[ProductSegment]:
        """All segment disclosures of `symbol` public on or before `d`."""
        ...

    def industry_asof(self, symbol: str, d: date) -> IndustryMapping | None:
        """Standardized sector classification of `symbol` effective on or before `d`."""
        ...
