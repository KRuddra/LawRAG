"""Tests for the source registry (Decision 2 human gate + Decision 3 status)."""

import json

import pytest

from backend.ingestion.source_registry import (
    DiscoveredBy,
    RegistryError,
    SourceStatus,
    ingestible_sources,
    load_registry,
)
from backend.jurisdictions import applicable_ids


def test_default_registry_loads_and_validates():
    entries = load_registry()
    ids = {e.id for e in entries}
    assert {"us-govinfo-uscode", "ca-justice-laws", "ca-bc-laws"} <= ids


def test_only_approved_active_sources_are_ingestible():
    ingestible = ingestible_sources()
    ids = {e.id for e in ingestible}
    # The three MVP sources are approved + active.
    assert {"us-govinfo-uscode", "ca-justice-laws", "ca-bc-laws"} == ids
    # The AI-discovered, unapproved candidate must be excluded.
    assert "us-courtlistener-caselaw-proposed" not in ids


def test_proposed_candidate_is_ai_discovered_and_not_ingestible():
    entries = {e.id: e for e in load_registry()}
    candidate = entries["us-courtlistener-caselaw-proposed"]
    assert candidate.discovered_by is DiscoveredBy.AI
    assert candidate.approved is False
    assert candidate.status is SourceStatus.PROPOSED
    assert candidate.is_ingestible is False


def test_ingestible_filter_by_jurisdiction_scope():
    # A BC query scope should reach BC + Canada federal sources, not US.
    scope = applicable_ids("ca-bc")  # ["ca-bc", "ca-federal"]
    result = {e.id for e in ingestible_sources(jurisdiction_ids=scope)}
    assert result == {"ca-bc-laws", "ca-justice-laws"}
    assert "us-govinfo-uscode" not in result


def test_ingestible_filter_by_category():
    # All MVP sources use "*", so any category resolves to all three.
    result = {e.id for e in ingestible_sources(category="criminal")}
    assert result == {"us-govinfo-uscode", "ca-justice-laws", "ca-bc-laws"}


def test_covers_category_wildcard_and_specific():
    entries = {e.id: e for e in load_registry()}
    assert entries["ca-bc-laws"].covers_category("family") is True  # "*"


def test_malformed_registry_missing_field_raises(tmp_path):
    bad = tmp_path / "sources.json"
    bad.write_text(json.dumps([{"id": "x", "name": "X"}]), encoding="utf-8")
    with pytest.raises(RegistryError):
        load_registry(bad)


def test_unknown_jurisdiction_in_registry_raises(tmp_path):
    bad = tmp_path / "sources.json"
    bad.write_text(
        json.dumps([{
            "id": "x", "name": "X", "jurisdiction_id": "ca-on",
            "adapter": "a", "url": "u", "doc_format": "xml",
            "licence": "l", "approved": True,
        }]),
        encoding="utf-8",
    )
    with pytest.raises(RegistryError):
        load_registry(bad)


def test_duplicate_ids_raise(tmp_path):
    entry = {
        "id": "dupe", "name": "X", "jurisdiction_id": "us-federal",
        "adapter": "a", "url": "u", "doc_format": "xml",
        "licence": "l", "approved": True,
    }
    bad = tmp_path / "sources.json"
    bad.write_text(json.dumps([entry, entry]), encoding="utf-8")
    with pytest.raises(RegistryError):
        load_registry(bad)
