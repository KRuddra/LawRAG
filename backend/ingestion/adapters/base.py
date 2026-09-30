"""Adapter framework: base class, registry, and jurisdiction helpers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Iterator, Type

from backend.api.models import Document
from backend.ingestion.source_registry import SourceEntry
from backend.jurisdictions import get_jurisdiction


class AdapterError(RuntimeError):
    """Raised when an adapter cannot fetch or parse a source."""


def jurisdiction_fields(entry: SourceEntry) -> Dict[str, Any]:
    """Derive the metadata every document from this source should carry.

    Resolves the registry entry's jurisdiction into the structured fields the
    chunker copies onto each chunk (Decision 7) plus the source id for
    provenance.
    """
    j = get_jurisdiction(entry.jurisdiction_id)
    return {
        "jurisdiction_id": j.id,
        "country": j.country.value,
        "region": j.region,
        "level": j.level.value,
        "jurisdiction": j.country.value,  # legacy scalar label
        "source_id": entry.id,
    }


class SourceAdapter(ABC):
    """Base class for a source adapter.

    Concrete adapters set a unique ``name`` (matching the ``adapter`` field in
    the registry) and implement :meth:`documents`.
    """

    name: str = "base"

    def __init__(self, entry: SourceEntry):
        self.entry = entry

    @property
    def base_metadata(self) -> Dict[str, Any]:
        return jurisdiction_fields(self.entry)

    @abstractmethod
    def documents(self) -> Iterator[Document]:
        """Yield normalized, jurisdiction/category-tagged Documents."""
        raise NotImplementedError


_ADAPTERS: Dict[str, Type[SourceAdapter]] = {}


def register_adapter(cls: Type[SourceAdapter]) -> Type[SourceAdapter]:
    """Class decorator that registers an adapter under its ``name``."""
    _ADAPTERS[cls.name] = cls
    return cls


def get_adapter(entry: SourceEntry) -> SourceAdapter:
    """Instantiate the adapter named by a registry entry."""
    try:
        cls = _ADAPTERS[entry.adapter]
    except KeyError as exc:
        raise AdapterError(
            f"No adapter registered for {entry.adapter!r}. "
            f"Known adapters: {sorted(_ADAPTERS)}"
        ) from exc
    return cls(entry)
