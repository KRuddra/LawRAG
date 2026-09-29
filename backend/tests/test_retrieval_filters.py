"""Tests for jurisdiction/category retrieval filtering (Decisions 7 & 8).

Covers the pure helpers only (no OpenAI key or indexed data required):
- build_where_clause: filters dict -> ChromaDB where clause
- enforce_jurisdiction_scope: hard post-filter closing the BM25 leak path
- Chunk model carries the new multi-jurisdiction fields
"""

from backend.api.models import Chunk
from backend.retrieval.vector_store import ScoredChunk, build_where_clause
from backend.retrieval.hybrid_search import enforce_jurisdiction_scope


def _chunk(chunk_id: str, jurisdiction_id: str) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        doc_id="d",
        doc_type="statute",
        text="t",
        hierarchy_path="h",
        jurisdiction="CA",
        title="Title",
        source_uri="uri",
        jurisdiction_id=jurisdiction_id,
    )


# --- build_where_clause -----------------------------------------------------

def test_where_clause_none_and_empty():
    assert build_where_clause(None) is None
    assert build_where_clause({}) is None
    assert build_where_clause({"jurisdiction_id": None}) is None


def test_where_clause_single_scalar_used_directly():
    assert build_where_clause({"category": "criminal"}) == {"category": "criminal"}


def test_where_clause_list_becomes_in_membership():
    clause = build_where_clause({"jurisdiction_id": ["ca-bc", "ca-federal"]})
    assert clause == {"jurisdiction_id": {"$in": ["ca-bc", "ca-federal"]}}


def test_where_clause_multiple_conditions_use_and():
    clause = build_where_clause(
        {"jurisdiction_id": ["ca-bc", "ca-federal"], "category": "criminal"}
    )
    assert "$and" in clause
    assert {"jurisdiction_id": {"$in": ["ca-bc", "ca-federal"]}} in clause["$and"]
    assert {"category": "criminal"} in clause["$and"]


def test_where_clause_drops_empty_list():
    assert build_where_clause({"jurisdiction_id": []}) is None


# --- enforce_jurisdiction_scope --------------------------------------------

def test_enforce_scope_drops_out_of_scope_chunks():
    results = [
        ScoredChunk(_chunk("a", "ca-bc"), 0.9),
        ScoredChunk(_chunk("b", "us-federal"), 0.8),   # leaked via BM25
        ScoredChunk(_chunk("c", "ca-federal"), 0.7),
    ]
    kept = enforce_jurisdiction_scope(results, ["ca-bc", "ca-federal"])
    assert {r.chunk.chunk_id for r in kept} == {"a", "c"}


def test_enforce_scope_passthrough_when_no_allowed_ids():
    results = [ScoredChunk(_chunk("a", "us-federal"), 0.9)]
    assert enforce_jurisdiction_scope(results, None) == results
    assert enforce_jurisdiction_scope(results, []) == results


def test_enforce_scope_drops_chunks_missing_jurisdiction_id():
    # Strict isolation: a chunk with no jurisdiction_id is not "in scope".
    results = [ScoredChunk(_chunk("a", None), 0.9)]
    assert enforce_jurisdiction_scope(results, ["ca-bc"]) == []


# --- Chunk model ------------------------------------------------------------

def test_chunk_accepts_multi_jurisdiction_fields():
    chunk = Chunk(
        chunk_id="x", doc_id="d", doc_type="statute", text="t",
        hierarchy_path="h", jurisdiction="CA", title="T", source_uri="u",
        jurisdiction_id="ca-federal", country="CA", level="federal",
        category="criminal", categories=["criminal", "traffic"],
        source_id="ca-justice-laws",
    )
    assert chunk.jurisdiction_id == "ca-federal"
    assert chunk.category == "criminal"
    assert chunk.categories == ["criminal", "traffic"]
    assert chunk.source_id == "ca-justice-laws"


def test_chunk_backward_compatible_without_new_fields():
    chunk = _chunk("x", "ca-bc")
    # Old construction path (no new fields) still works with sensible defaults.
    legacy = Chunk(
        chunk_id="x", doc_id="d", doc_type="statute", text="t",
        hierarchy_path="h", jurisdiction="WI", title="T", source_uri="u",
    )
    assert legacy.jurisdiction_id is None
    assert legacy.categories == []
