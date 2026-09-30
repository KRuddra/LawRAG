"""Tests for source adapters (Phase 2), focused on Justice Laws parsing."""

import pytest

from backend.ingestion.adapters import get_adapter
from backend.ingestion.adapters.base import AdapterError, jurisdiction_fields
from backend.ingestion.adapters.justice_laws import JusticeLawsAdapter, parse_statute_xml
from backend.ingestion.source_registry import load_registry

# Faithful to the real justicecanada/laws-lois-xml schema.
IN_FORCE_ACT = """<?xml version="1.0" encoding="utf-8"?>
<Statute in-force="yes" xml:lang="en" lims:current-date="2025-07-24"
         xmlns:lims="http://justice.gc.ca/lims">
  <Identification>
    <LongTitle>An Act respecting the safety of motor vehicles</LongTitle>
    <ShortTitle status="official">Motor Vehicle Safety Act</ShortTitle>
    <Chapter><ConsolidatedNumber official="yes">M-10</ConsolidatedNumber></Chapter>
  </Identification>
  <Body>
    <Section><MarginalNote>Short title</MarginalNote><Label>1</Label>
      <Text>This Act may be cited as the Motor Vehicle Safety Act.</Text></Section>
    <Section><MarginalNote>Offence</MarginalNote><Label>2</Label>
      <Text>Every person who operates a motor vehicle in contravention of this Act commits an offence.</Text></Section>
  </Body>
</Statute>"""

REPEALED_ACT = """<?xml version="1.0" encoding="utf-8"?>
<Statute in-force="yes" xml:lang="en" xmlns:lims="http://justice.gc.ca/lims">
  <Identification>
    <ShortTitle status="official">Old Repealed Act</ShortTitle>
    <Chapter><ConsolidatedNumber official="yes">O-1</ConsolidatedNumber></Chapter>
  </Identification>
  <Repealed>[Repealed, 2012, c. 24, s. 76]</Repealed>
</Statute>"""

CA_FEDERAL_META = {
    "jurisdiction_id": "ca-federal", "country": "CA", "region": None,
    "level": "federal", "jurisdiction": "CA", "source_id": "ca-justice-laws",
}


def test_parse_in_force_act_extracts_core_fields():
    doc = parse_statute_xml(IN_FORCE_ACT, base_metadata=CA_FEDERAL_META,
                            source_uri="https://laws-lois.justice.gc.ca/eng/acts/M-10/")
    assert doc is not None
    assert doc.metadata["title"] == "Motor Vehicle Safety Act"
    assert doc.metadata["document_type"] == "statute"
    assert doc.metadata["statute_numbers"] == ["M-10"]
    assert doc.metadata["dates"] == ["2025-07-24"]
    assert "motor vehicle" in doc.text.lower()
    assert "commits an offence" in doc.text.lower()


def test_parse_tags_jurisdiction_and_category():
    doc = parse_statute_xml(IN_FORCE_ACT, base_metadata=CA_FEDERAL_META)
    assert doc.metadata["jurisdiction_id"] == "ca-federal"
    assert doc.metadata["level"] == "federal"
    assert doc.metadata["source_id"] == "ca-justice-laws"
    # Body mentions "motor vehicle" and "offence" -> traffic and/or criminal.
    cats = doc.metadata["categories"]
    assert "traffic" in cats or "criminal" in cats


def test_repealed_act_is_skipped():
    assert parse_statute_xml(REPEALED_ACT, base_metadata=CA_FEDERAL_META) is None


def test_not_in_force_attribute_is_skipped():
    xml = IN_FORCE_ACT.replace('in-force="yes"', 'in-force="no"')
    assert parse_statute_xml(xml, base_metadata=CA_FEDERAL_META) is None


def test_wrong_root_raises_adapter_error():
    with pytest.raises(AdapterError):
        parse_statute_xml("<NotAStatute/>", base_metadata=CA_FEDERAL_META)


def test_adapter_reads_directory_of_acts(tmp_path):
    (tmp_path / "M-10.xml").write_text(IN_FORCE_ACT, encoding="utf-8")
    (tmp_path / "O-1.xml").write_text(REPEALED_ACT, encoding="utf-8")

    entry = next(e for e in load_registry() if e.id == "ca-justice-laws")
    adapter = JusticeLawsAdapter(entry, source_dir=tmp_path)
    docs = list(adapter.documents())

    # Only the in-force Act is emitted; the repealed one is skipped.
    assert len(docs) == 1
    assert docs[0].metadata["title"] == "Motor Vehicle Safety Act"
    assert docs[0].metadata["jurisdiction_id"] == "ca-federal"


def test_get_adapter_resolves_justice_laws():
    entry = next(e for e in load_registry() if e.id == "ca-justice-laws")
    adapter = get_adapter(entry)
    assert isinstance(adapter, JusticeLawsAdapter)
    assert jurisdiction_fields(entry)["level"] == "federal"


def test_missing_source_dir_raises():
    entry = next(e for e in load_registry() if e.id == "ca-justice-laws")
    adapter = JusticeLawsAdapter(entry, source_dir="/nonexistent/path/xyz")
    with pytest.raises(AdapterError):
        list(adapter.documents())
