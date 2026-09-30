"""Tests for the govinfo (USLM) and BC Laws (CiviX/XHTML) adapters."""

import pytest

from backend.ingestion.adapters import get_adapter
from backend.ingestion.adapters.base import AdapterError
from backend.ingestion.adapters.govinfo import GovInfoAdapter, parse_uslm_xml
from backend.ingestion.adapters.bc_laws import (
    BCLawsAdapter,
    CivixEntry,
    parse_browse_listing,
    parse_document_html,
)
from backend.ingestion.source_registry import load_registry

US_META = {
    "jurisdiction_id": "us-federal", "country": "US", "region": None,
    "level": "federal", "jurisdiction": "US", "source_id": "us-govinfo-uscode",
}
BC_META = {
    "jurisdiction_id": "ca-bc", "country": "CA", "region": "BC",
    "level": "provincial", "jurisdiction": "CA", "source_id": "ca-bc-laws",
}

# Faithful to real USLM (namespace http://schemas.gpo.gov/xml/uslm).
USLM_DOC = """<?xml version="1.0" encoding="UTF-8"?>
<uscDoc xmlns="http://schemas.gpo.gov/xml/uslm" xmlns:dc="http://purl.org/dc/elements/1.1/">
  <meta><dc:title>Title 18 - Crimes and Criminal Procedure</dc:title></meta>
  <main>
    <title><num value="18">Title 18</num><heading>Crimes and Criminal Procedure</heading>
      <section><num value="1111">§ 1111.</num><heading>Murder</heading>
        <content><p>Murder is the unlawful killing of a human being with malice aforethought. Whoever commits murder is guilty of an offense.</p></content>
      </section>
    </title>
  </main>
</uscDoc>"""

# Real CiviX browse listing shape.
CIVIX_LISTING = """<?xml version="1.0"?>
<root>
  <dir><CIVIX_DOCUMENT_TITLE>-- M --</CIVIX_DOCUMENT_TITLE><CIVIX_DOCUMENT_ID>111</CIVIX_DOCUMENT_ID><CIVIX_DOCUMENT_TYPE>dir</CIVIX_DOCUMENT_TYPE></dir>
  <document><CIVIX_DOCUMENT_TITLE>Motor Vehicle Act</CIVIX_DOCUMENT_TITLE><CIVIX_DOCUMENT_ID>96318_01</CIVIX_DOCUMENT_ID><CIVIX_DOCUMENT_TYPE>document</CIVIX_DOCUMENT_TYPE></document>
</root>"""

# CiviX act content is XHTML.
CIVIX_HTML = """<!DOCTYPE html><html><head><title>Motor Vehicle Act</title>
<style>.x{}</style><script>var a=1;</script></head>
<body><h2>Motor Vehicle Act</h2>
<p>A person must not drive a motor vehicle on a highway without a licence. Driving while impaired is an offence.</p>
</body></html>"""


# --- govinfo / USLM ---------------------------------------------------------

def test_parse_uslm_extracts_title_and_text():
    doc = parse_uslm_xml(USLM_DOC, base_metadata=US_META, source_uri="usc18.xml")
    assert doc is not None
    assert "Crimes and Criminal Procedure" in doc.metadata["title"]
    assert "malice aforethought" in doc.text.lower()
    assert doc.metadata["jurisdiction_id"] == "us-federal"
    assert doc.metadata["document_type"] == "statute"


def test_parse_uslm_classifies_criminal():
    doc = parse_uslm_xml(USLM_DOC, base_metadata=US_META)
    assert "criminal" in doc.metadata["categories"]


def test_parse_uslm_malformed_raises():
    with pytest.raises(AdapterError):
        parse_uslm_xml(b"\x00\x01 not xml at all <<<", base_metadata=US_META)


def test_govinfo_adapter_reads_directory(tmp_path):
    (tmp_path / "usc18.xml").write_text(USLM_DOC, encoding="utf-8")
    entry = next(e for e in load_registry() if e.id == "us-govinfo-uscode")
    adapter = GovInfoAdapter(entry, source_dir=tmp_path)
    docs = list(adapter.documents())
    assert len(docs) == 1
    assert docs[0].metadata["jurisdiction_id"] == "us-federal"


# --- BC Laws / CiviX --------------------------------------------------------

def test_parse_browse_listing_splits_dirs_and_documents():
    entries = parse_browse_listing(CIVIX_LISTING)
    kinds = {e.id: e.kind for e in entries}
    assert kinds["111"] == "dir"
    assert kinds["96318_01"] == "document"
    assert any(e.title == "Motor Vehicle Act" for e in entries)


def test_parse_document_html_extracts_text_and_drops_scripts():
    doc = parse_document_html(CIVIX_HTML, base_metadata=BC_META, source_uri="u")
    assert doc is not None
    assert doc.metadata["title"] == "Motor Vehicle Act"
    assert "var a=1" not in doc.text  # script stripped
    assert "motor vehicle" in doc.text.lower()
    assert doc.metadata["jurisdiction_id"] == "ca-bc"
    assert doc.metadata["region"] == "BC"


def test_parse_document_html_classifies_traffic():
    doc = parse_document_html(CIVIX_HTML, base_metadata=BC_META)
    assert "traffic" in doc.metadata["categories"] or "criminal" in doc.metadata["categories"]


def test_get_adapter_resolves_both():
    entries = {e.id: e for e in load_registry()}
    assert isinstance(get_adapter(entries["us-govinfo-uscode"]), GovInfoAdapter)
    assert isinstance(get_adapter(entries["ca-bc-laws"]), BCLawsAdapter)
