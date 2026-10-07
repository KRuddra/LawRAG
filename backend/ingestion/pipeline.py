"""Decoupled ingestion pipeline (Decision 11).

Orchestrates: adapter.documents() -> chunk -> (latest-only replace) -> embed +
upsert, skipping unchanged documents via the content-hash cache (Decision 10).

The vector store and cache are injected so the orchestration is fully testable
without an OpenAI key or a live ChromaDB.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Protocol

from backend.api.models import Chunk, Document
from backend.ingestion.chunking import chunk_document
from backend.ingestion.ingest_cache import IngestCache

logger = logging.getLogger(__name__)


class _Adapter(Protocol):
    def documents(self) -> "list[Document]": ...


class _VectorStore(Protocol):
    def upsert_chunks(self, chunks: List[Chunk]) -> int: ...
    def delete_by_doc_id(self, doc_id: str) -> None: ...


@dataclass
class IngestStats:
    """Outcome of ingesting one source."""

    source_id: str
    documents_seen: int = 0
    documents_ingested: int = 0
    documents_skipped: int = 0  # unchanged since last run (cache hit)
    chunks_upserted: int = 0
    errors: List[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "documents_seen": self.documents_seen,
            "documents_ingested": self.documents_ingested,
            "documents_skipped": self.documents_skipped,
            "chunks_upserted": self.chunks_upserted,
            "errors": self.errors,
        }


def ingest_source(
    adapter: _Adapter,
    vector_store: _VectorStore,
    cache: IngestCache,
    source_id: str,
    replace: bool = True,
    limit: Optional[int] = None,
) -> IngestStats:
    """Ingest every document an adapter yields.

    - Unchanged documents (same content hash as last run) are skipped entirely
      so they are never re-embedded (Decision 10).
    - Changed/new documents replace their previous chunks before upsert so only
      the current version is stored (Decision 9).
    - ``limit`` caps how many documents are processed (for cheap smoke runs).
    """
    stats = IngestStats(source_id=source_id)

    for doc in adapter.documents():
        if limit is not None and stats.documents_seen >= limit:
            break
        stats.documents_seen += 1
        doc_id = doc.source_path

        if doc_id and cache.is_current(doc_id, doc.text):
            stats.documents_skipped += 1
            continue

        try:
            chunks = chunk_document(doc)
            if replace and doc_id:
                vector_store.delete_by_doc_id(doc_id)
            if chunks:
                vector_store.upsert_chunks(chunks)
            cache.record(doc_id, doc.text)
            stats.documents_ingested += 1
            stats.chunks_upserted += len(chunks)
        except Exception as exc:  # keep going; one bad doc shouldn't abort the source
            logger.exception("Failed to ingest %s", doc_id)
            stats.errors.append(f"{doc_id}: {exc}")

    cache.save()
    logger.info("Ingested %s: %s", source_id, stats.as_dict())
    return stats
