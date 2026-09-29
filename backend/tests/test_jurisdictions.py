"""Tests for the jurisdiction taxonomy (Decision 7 federal-overlap resolver)."""

import pytest

from backend.jurisdictions import (
    CA_BC,
    CA_FEDERAL,
    US_FEDERAL,
    Country,
    Level,
    UnknownJurisdictionError,
    all_jurisdictions,
    applicable_ids,
    federal_for,
    get_jurisdiction,
    resolve_applicable,
)


def test_mvp_registry_has_exactly_the_three_scoped_jurisdictions():
    ids = {j.id for j in all_jurisdictions()}
    assert ids == {"us-federal", "ca-federal", "ca-bc"}


def test_get_jurisdiction_returns_expected_shape():
    bc = get_jurisdiction("ca-bc")
    assert bc.country is Country.CA
    assert bc.level is Level.PROVINCIAL
    assert bc.region == "BC"
    assert bc.is_federal is False


def test_get_unknown_jurisdiction_raises():
    with pytest.raises(UnknownJurisdictionError):
        get_jurisdiction("ca-on")


def test_federal_for_country():
    assert federal_for(Country.US) is US_FEDERAL
    assert federal_for(Country.CA) is CA_FEDERAL


def test_federal_query_resolves_to_only_itself():
    assert resolve_applicable("us-federal") == [US_FEDERAL]
    assert resolve_applicable("ca-federal") == [CA_FEDERAL]


def test_provincial_query_includes_co_applicable_federal_layer():
    # BC query must return BC first (primary) then Canada federal.
    resolved = resolve_applicable("ca-bc")
    assert resolved == [CA_BC, CA_FEDERAL]


def test_applicable_ids_are_usable_as_metadata_filter():
    assert applicable_ids("ca-bc") == ["ca-bc", "ca-federal"]
    assert applicable_ids("us-federal") == ["us-federal"]


def test_bc_query_never_leaks_us_law():
    # Isolation guarantee: US federal must not appear in a Canadian scope.
    assert US_FEDERAL not in resolve_applicable("ca-bc")
