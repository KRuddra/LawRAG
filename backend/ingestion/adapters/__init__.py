"""Source adapters: fetch + parse official legal sources into Documents.

Each adapter is pinned to a registry source (Decision 2) and produces
jurisdiction/category-tagged :class:`~backend.api.models.Document` objects for
the existing chunk -> embed -> index pipeline.
"""

from backend.ingestion.adapters.base import (
    AdapterError,
    SourceAdapter,
    get_adapter,
    jurisdiction_fields,
    register_adapter,
)

# Import concrete adapters so they self-register.
from backend.ingestion.adapters import justice_laws  # noqa: F401
from backend.ingestion.adapters import govinfo  # noqa: F401
from backend.ingestion.adapters import bc_laws  # noqa: F401

__all__ = [
    "AdapterError",
    "SourceAdapter",
    "get_adapter",
    "jurisdiction_fields",
    "register_adapter",
]
