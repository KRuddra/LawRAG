"""
Category-of-law taxonomy and classification (Decision 8).

A single controlled, cross-jurisdiction vocabulary so users can filter by
category consistently whether the law comes from the US or Canada. Pure
standard library.

Classification is multi-label and hybrid by design:

* :func:`classify` is the deterministic, rules/keyword first pass used at
  ingestion. It is cheap, explainable, and auditable.
* An LLM-assisted second pass (for ambiguous documents) plugs in later behind
  the same return contract; it is intentionally not wired here so the pipeline
  has no API-key dependency for basic categorisation.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional, Sequence, Set


class LawCategory(str, Enum):
    """Controlled vocabulary of law categories.

    Deliberately broad and jurisdiction-neutral; source-native categories are
    mapped into these values at ingestion.
    """

    CRIMINAL = "criminal"
    TRAFFIC = "traffic"            # motor vehicle / highway
    FAMILY = "family"
    PROPERTY = "property"
    EMPLOYMENT = "employment"     # labour / employment
    TAX = "tax"
    ADMINISTRATIVE = "administrative"
    CONSTITUTIONAL = "constitutional"
    COMMERCIAL = "commercial"     # business / corporate / consumer
    IMMIGRATION = "immigration"
    HEALTH = "health"
    ENVIRONMENTAL = "environmental"
    CIVIL_PROCEDURE = "civil_procedure"
    OTHER = "other"


# Keyword signals per category. Ordered roughly by specificity; matching is
# case-insensitive and word-ish (substring on a normalised lower-case string).
# Kept small and readable — this is a first pass, not a full ontology.
_CATEGORY_KEYWORDS: Dict[LawCategory, Sequence[str]] = {
    LawCategory.CRIMINAL: (
        "criminal", "offence", "offense", "felony", "misdemeanor",
        "homicide", "assault", "theft", "sentencing", "prosecution",
    ),
    LawCategory.TRAFFIC: (
        "motor vehicle", "traffic", "highway", "driver", "driving",
        "speeding", "licence plate", "license plate", "impaired driving", "dui",
    ),
    LawCategory.FAMILY: (
        "family law", "divorce", "custody", "child support", "adoption",
        "guardianship", "marriage", "spousal",
    ),
    LawCategory.PROPERTY: (
        "real property", "landlord", "tenant", "lease", "conveyance",
        "easement", "zoning", "land title", "mortgage",
    ),
    LawCategory.EMPLOYMENT: (
        "employment", "labour", "labor", "workplace", "wages",
        "occupational health", "collective bargaining", "wrongful dismissal",
    ),
    LawCategory.TAX: (
        "income tax", "taxation", "excise", "gst", "hst", "sales tax", "tariff",
    ),
    LawCategory.IMMIGRATION: (
        "immigration", "refugee", "citizenship", "permanent resident", "visa",
        "deportation", "removal order",
    ),
    LawCategory.HEALTH: (
        "public health", "health care", "healthcare", "mental health",
        "controlled substance", "medical",
    ),
    LawCategory.ENVIRONMENTAL: (
        "environmental", "emissions", "pollution", "wildlife", "fisheries",
        "endangered species", "waste management",
    ),
    LawCategory.COMMERCIAL: (
        "corporation", "corporate", "securities", "consumer protection",
        "bankruptcy", "insolvency", "competition", "contract",
    ),
    LawCategory.CONSTITUTIONAL: (
        "constitution", "charter of rights", "bill of rights",
        "fundamental freedoms", "due process",
    ),
    LawCategory.CIVIL_PROCEDURE: (
        "rules of court", "civil procedure", "pleadings", "discovery",
        "limitation period",
    ),
    LawCategory.ADMINISTRATIVE: (
        "administrative", "regulation", "licensing", "tribunal", "agency",
        "permit",
    ),
}


def all_categories() -> List[LawCategory]:
    """Return the full controlled vocabulary."""
    return list(LawCategory)


def classify(
    text: str,
    title: Optional[str] = None,
    hints: Optional[Sequence[str]] = None,
    max_categories: int = 3,
) -> List[LawCategory]:
    """Assign one or more categories to a document (rules/keyword pass).

    Args:
        text: The document (or leading excerpt) to classify.
        title: Optional title, weighted more heavily than body text.
        hints: Optional source-native category strings (e.g. a statute chapter
            name) matched against the same keyword table.
        max_categories: Cap on labels returned, most-signal first.

    Returns:
        A multi-label list of :class:`LawCategory`. Never empty — falls back to
        ``[LawCategory.OTHER]`` when nothing matches.
    """
    title_blob = _normalise(title or "")
    body_blob = _normalise(text or "")
    hint_blob = _normalise(" ".join(hints or ()))

    scores: Dict[LawCategory, int] = {}
    for category, keywords in _CATEGORY_KEYWORDS.items():
        score = 0
        for keyword in keywords:
            kw = keyword.lower()
            # Title and hints are strong signals; body is a weaker signal.
            if kw in title_blob:
                score += 3
            if kw in hint_blob:
                score += 3
            if kw in body_blob:
                score += 1
        if score > 0:
            scores[category] = score

    if not scores:
        return [LawCategory.OTHER]

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return [category for category, _ in ranked[:max_categories]]


def normalise_category(value: str) -> Optional[LawCategory]:
    """Map an arbitrary string to a :class:`LawCategory`, or ``None``."""
    candidate = value.strip().lower()
    for category in LawCategory:
        if candidate == category.value:
            return category
    return None


def _normalise(value: str) -> str:
    """Lower-case and collapse whitespace for stable substring matching."""
    return " ".join(value.lower().split())
