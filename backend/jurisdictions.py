"""
Jurisdiction taxonomy for the multi-jurisdiction legal RAG pipeline.

Models the country -> region -> level hierarchy used to scope retrieval
(Decision 7: hard metadata filtering). Pure standard library so the domain
model carries no dependency on pydantic, ChromaDB, or any network client.

MVP scope (Decision 1): US federal, Canada federal, British Columbia.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional


class Country(str, Enum):
    """Supported countries."""

    US = "US"
    CA = "CA"


class Level(str, Enum):
    """Government level a body of law sits at."""

    FEDERAL = "federal"
    STATE = "state"          # US sub-national
    PROVINCIAL = "provincial"  # CA sub-national
    TERRITORIAL = "territorial"  # CA territories
    MUNICIPAL = "municipal"


class UnknownJurisdictionError(KeyError):
    """Raised when a jurisdiction id is not present in the registry."""


@dataclass(frozen=True)
class Jurisdiction:
    """A single jurisdiction that law can belong to.

    ``region`` is ``None`` for federal jurisdictions and a short code
    (e.g. ``"BC"``) for sub-national ones.
    """

    id: str
    country: Country
    level: Level
    name: str
    region: Optional[str] = None

    @property
    def is_federal(self) -> bool:
        return self.level is Level.FEDERAL


# --- MVP registry -----------------------------------------------------------
# Keep this list small and explicit; new jurisdictions are added deliberately
# rather than discovered at runtime.

US_FEDERAL = Jurisdiction(
    id="us-federal", country=Country.US, level=Level.FEDERAL, name="United States (federal)"
)
CA_FEDERAL = Jurisdiction(
    id="ca-federal", country=Country.CA, level=Level.FEDERAL, name="Canada (federal)"
)
CA_BC = Jurisdiction(
    id="ca-bc",
    country=Country.CA,
    level=Level.PROVINCIAL,
    name="British Columbia",
    region="BC",
)

_JURISDICTIONS: Dict[str, Jurisdiction] = {
    j.id: j for j in (US_FEDERAL, CA_FEDERAL, CA_BC)
}


def all_jurisdictions() -> List[Jurisdiction]:
    """Return every registered jurisdiction."""
    return list(_JURISDICTIONS.values())


def get_jurisdiction(jurisdiction_id: str) -> Jurisdiction:
    """Look up a jurisdiction by id, raising if it is unknown."""
    try:
        return _JURISDICTIONS[jurisdiction_id]
    except KeyError as exc:
        raise UnknownJurisdictionError(
            f"Unknown jurisdiction id: {jurisdiction_id!r}. "
            f"Known ids: {sorted(_JURISDICTIONS)}"
        ) from exc


def federal_for(country: Country) -> Optional[Jurisdiction]:
    """Return the federal jurisdiction for a country, if one is registered."""
    for jurisdiction in _JURISDICTIONS.values():
        if jurisdiction.country is country and jurisdiction.is_federal:
            return jurisdiction
    return None


def resolve_applicable(jurisdiction_id: str) -> List[Jurisdiction]:
    """Return every jurisdiction whose law applies to a query scoped here.

    A sub-national query (e.g. British Columbia) is answered from that region
    **plus** its country's federal layer, because federal law co-applies within
    a province or state. A federal query returns only the federal layer.

    The region is always first so callers can label it as the primary scope.
    """
    primary = get_jurisdiction(jurisdiction_id)
    if primary.is_federal:
        return [primary]

    applicable = [primary]
    federal = federal_for(primary.country)
    if federal is not None and federal.id != primary.id:
        applicable.append(federal)
    return applicable


def applicable_ids(jurisdiction_id: str) -> List[str]:
    """Convenience: the ids from :func:`resolve_applicable`, for metadata filters."""
    return [j.id for j in resolve_applicable(jurisdiction_id)]
