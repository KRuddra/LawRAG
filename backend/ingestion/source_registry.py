"""
Source registry (Decision 2 + Decision 3).

A lightweight, file-backed registry of the official sources we ingest from.
It is deliberately simple: a JSON file of entries, each pinned to a
jurisdiction and an adapter, gated by a human ``approved`` flag. AI-discovered
candidates may be added with ``approved: false`` / ``status: proposed`` and are
never ingested until a human flips the flag.

``status`` also carries Decision 3's failure handling: a source that repeatedly
fails to fetch is marked ``degraded`` (kept, flagged for review) rather than
silently dropped.

Pure standard library.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from backend.jurisdictions import get_jurisdiction

# Default registry file, co-located with this module.
DEFAULT_REGISTRY_PATH = Path(__file__).parent / "sources.json"


class SourceStatus(str, Enum):
    """Lifecycle state of a source (Decision 3)."""

    ACTIVE = "active"        # healthy, ingest normally
    DEGRADED = "degraded"    # repeated fetch failures; keep last-good, flag for review
    PROPOSED = "proposed"    # candidate awaiting human approval
    REMOVED = "removed"      # retired by a human; kept for audit, never ingested


class DiscoveredBy(str, Enum):
    HUMAN = "human"
    AI = "ai"


class RegistryError(ValueError):
    """Raised when the registry file is malformed."""


@dataclass(frozen=True)
class SourceEntry:
    """One official source we can ingest from."""

    id: str
    name: str
    jurisdiction_id: str
    adapter: str
    url: str
    doc_format: str          # e.g. "uslm-xml", "xml", "json"
    licence: str             # e.g. "public-domain", "ogl-canada", "ogl-bc"
    approved: bool           # the human gate; nothing ingests without this
    status: SourceStatus = SourceStatus.ACTIVE
    categories: Sequence[str] = field(default_factory=lambda: ["*"])
    discovered_by: DiscoveredBy = DiscoveredBy.HUMAN
    notes: str = ""

    @property
    def is_ingestible(self) -> bool:
        """True only if a human approved it and it is currently active."""
        return self.approved and self.status is SourceStatus.ACTIVE

    def covers_category(self, category: str) -> bool:
        """Whether this source serves a given category ("*" means all)."""
        return "*" in self.categories or category in self.categories


_REQUIRED_FIELDS = (
    "id", "name", "jurisdiction_id", "adapter", "url", "doc_format",
    "licence", "approved",
)


def _entry_from_dict(raw: Dict) -> SourceEntry:
    missing = [key for key in _REQUIRED_FIELDS if key not in raw]
    if missing:
        raise RegistryError(f"Source entry {raw.get('id', '?')!r} missing fields: {missing}")

    # Validate the jurisdiction link eagerly so a typo fails loudly at load time.
    try:
        get_jurisdiction(raw["jurisdiction_id"])
    except KeyError as exc:
        raise RegistryError(
            f"Source entry {raw['id']!r} references unknown jurisdiction "
            f"{raw['jurisdiction_id']!r}."
        ) from exc

    try:
        status = SourceStatus(raw.get("status", SourceStatus.ACTIVE.value))
        discovered_by = DiscoveredBy(raw.get("discovered_by", DiscoveredBy.HUMAN.value))
    except ValueError as exc:
        raise RegistryError(f"Source entry {raw['id']!r} has an invalid enum value: {exc}") from exc

    return SourceEntry(
        id=raw["id"],
        name=raw["name"],
        jurisdiction_id=raw["jurisdiction_id"],
        adapter=raw["adapter"],
        url=raw["url"],
        doc_format=raw["doc_format"],
        licence=raw["licence"],
        approved=bool(raw["approved"]),
        status=status,
        categories=tuple(raw.get("categories", ["*"])),
        discovered_by=discovered_by,
        notes=raw.get("notes", ""),
    )


def load_registry(path: Optional[Path] = None) -> List[SourceEntry]:
    """Load and validate the source registry from disk."""
    path = path or DEFAULT_REGISTRY_PATH
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RegistryError(f"Registry file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RegistryError(f"Registry file is not valid JSON: {exc}") from exc

    if not isinstance(raw, list):
        raise RegistryError("Registry file must contain a JSON array of source entries.")

    entries = [_entry_from_dict(item) for item in raw]

    ids = [entry.id for entry in entries]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        raise RegistryError(f"Duplicate source ids in registry: {sorted(duplicates)}")

    return entries


def ingestible_sources(
    entries: Optional[Sequence[SourceEntry]] = None,
    jurisdiction_ids: Optional[Sequence[str]] = None,
    category: Optional[str] = None,
) -> List[SourceEntry]:
    """Return approved + active sources, optionally scoped by jurisdiction/category."""
    entries = list(entries) if entries is not None else load_registry()
    result = [entry for entry in entries if entry.is_ingestible]

    if jurisdiction_ids is not None:
        wanted = set(jurisdiction_ids)
        result = [entry for entry in result if entry.jurisdiction_id in wanted]

    if category is not None:
        result = [entry for entry in result if entry.covers_category(category)]

    return result
