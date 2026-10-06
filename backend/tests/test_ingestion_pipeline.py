"""Tests for the ingestion cache (D10) and pipeline orchestration (D9, D11)."""

from typing import List

from backend.api.models import Chunk, Document
from backend.ingestion.ingest_cache import IngestCache
from backend.ingestion.pipeline import ingest_source


# --- IngestCache (Decision 10) ---------------------------------------------

def test_cache_detects_unchanged_and_changed(tmp_path):
    cache = IngestCache(path=tmp_path / "c.json")
    assert cache.is_current("doc1", "hello") is False  # never seen
    cache.record("doc1", "hello")
    assert cache.is_current("doc1", "hello") is True   # unchanged
    assert cache.is_current("doc1", "hello world") is False  # changed


def test_cache_persists_round_trip(tmp_path):
    path = tmp_path / "c.json"
    cache = IngestCache(path=path)
    cache.record("doc1", "text")
    cache.save()
    reloaded = IngestCache.load(path)
    assert reloaded.is_current("doc1", "text") is True
    assert len(reloaded) == 1


def test_cache_tolerates_corrupt_file(tmp_path):
    path = tmp_path / "c.json"
    path.write_text("{not json", encoding="utf-8")
    cache = IngestCache.load(path)  # must not raise
    assert len(cache) == 0


# --- Pipeline (Decisions 9 & 11) -------------------------------------------

class FakeVectorStore:
    def __init__(self):
        self.upserted: List[str] = []
        self.deleted: List[str] = []

    def upsert_chunks(self, chunks):
        self.upserted.extend(c.doc_id for c in chunks)
        return len(chunks)

    def delete_by_doc_id(self, doc_id):
        self.deleted.append(doc_id)


class FakeAdapter:
    def __init__(self, docs):
        self._docs = docs

    def documents(self):
        return iter(self._docs)


def _doc(doc_id: str, text: str) -> Document:
    # No recognized document_type -> fallback chunker, which yields >=1 chunk
    # for any non-empty text (keeps the pipeline test independent of the
    # statute-specific chunking heuristics).
    return Document(
        text=text,
        metadata={"title": "T", "jurisdiction_id": "ca-federal",
                  "categories": ["criminal"]},
        source_path=doc_id,
    )


def test_pipeline_ingests_new_documents(tmp_path):
    vs = FakeVectorStore()
    cache = IngestCache(path=tmp_path / "c.json")
    adapter = FakeAdapter([_doc("acts/A.xml", "text a"), _doc("acts/B.xml", "text b")])

    stats = ingest_source(adapter, vs, cache, source_id="ca-justice-laws")

    assert stats.documents_seen == 2
    assert stats.documents_ingested == 2
    assert stats.documents_skipped == 0
    assert stats.chunks_upserted >= 2
    # Latest-only: each doc's old chunks are deleted before upsert (Decision 9).
    assert vs.deleted == ["acts/A.xml", "acts/B.xml"]


def test_pipeline_skips_unchanged_on_rerun(tmp_path):
    cache = IngestCache(path=tmp_path / "c.json")
    docs = [_doc("acts/A.xml", "text a")]

    first = ingest_source(FakeAdapter(docs), FakeVectorStore(), cache, source_id="s")
    assert first.documents_ingested == 1

    vs2 = FakeVectorStore()
    second = ingest_source(FakeAdapter(docs), vs2, cache, source_id="s")
    assert second.documents_skipped == 1
    assert second.documents_ingested == 0
    assert vs2.upserted == []  # nothing re-embedded
    assert vs2.deleted == []


def test_pipeline_reingests_changed_document(tmp_path):
    cache = IngestCache(path=tmp_path / "c.json")
    ingest_source(FakeAdapter([_doc("acts/A.xml", "old")]), FakeVectorStore(), cache, source_id="s")

    vs2 = FakeVectorStore()
    stats = ingest_source(FakeAdapter([_doc("acts/A.xml", "new text")]), vs2, cache, source_id="s")
    assert stats.documents_ingested == 1
    assert vs2.deleted == ["acts/A.xml"]  # replaced
    assert vs2.upserted  # re-embedded


def test_pipeline_continues_past_a_failing_document(tmp_path):
    class ExplodingStore(FakeVectorStore):
        def upsert_chunks(self, chunks):
            if any(c.doc_id == "acts/BAD.xml" for c in chunks):
                raise RuntimeError("boom")
            return super().upsert_chunks(chunks)

    vs = ExplodingStore()
    cache = IngestCache(path=tmp_path / "c.json")
    adapter = FakeAdapter([_doc("acts/BAD.xml", "x"), _doc("acts/GOOD.xml", "y")])

    stats = ingest_source(adapter, vs, cache, source_id="s")
    assert stats.documents_ingested == 1
    assert len(stats.errors) == 1
    assert "acts/GOOD.xml" in vs.upserted
