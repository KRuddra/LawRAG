"""BC Laws adapter — British Columbia statutes via the CiviX API (Decision 1 MVP).

The CiviX API has two shapes:

* a **browse listing** at ``/civix/content/complete/statreg/<id>/`` returning
  XML ``<root>`` of ``<dir>`` / ``<document>`` entries (``CIVIX_DOCUMENT_*``
  fields); the tree nests statreg -> letter -> act -> content document.
* a **content document** at ``/civix/document/id/complete/statreg/<id>`` returning
  the act as **XHTML**.

The pure parsers (:func:`parse_browse_listing`, :func:`parse_document_html`) are
tested with fixtures; :meth:`BCLawsAdapter.documents` performs the live
traversal. No auth; requests are throttled politely (Decision 12).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Optional

import requests
from bs4 import BeautifulSoup
from lxml import etree

from backend.api.models import Document
from backend.categories import classify
from backend.ingestion.adapters.base import AdapterError, SourceAdapter, register_adapter

logger = logging.getLogger(__name__)

CIVIX_CONTENT_BASE = "https://www.bclaws.gov.bc.ca/civix/content/complete/statreg"
CIVIX_DOCUMENT_BASE = "https://www.bclaws.gov.bc.ca/civix/document/id/complete/statreg"
REQUEST_DELAY_SECONDS = 0.5  # polite throttle


@dataclass(frozen=True)
class CivixEntry:
    """One entry in a CiviX browse listing."""

    id: str
    title: str
    kind: str  # "dir" or "document"


def parse_browse_listing(xml: bytes | str) -> List[CivixEntry]:
    """Parse a CiviX ``<root>`` listing into dir/document entries."""
    if isinstance(xml, str):
        xml = xml.encode("utf-8")
    parser = etree.XMLParser(recover=True)
    root = etree.fromstring(xml, parser=parser)
    if root is None:
        raise AdapterError("Malformed CiviX browse listing")

    entries: List[CivixEntry] = []
    for node in root:
        if node.tag not in ("dir", "document"):
            continue
        doc_id = node.findtext("CIVIX_DOCUMENT_ID")
        title = node.findtext("CIVIX_DOCUMENT_TITLE") or ""
        if doc_id:
            entries.append(CivixEntry(id=doc_id.strip(), title=title.strip(), kind=node.tag))
    return entries


def parse_document_html(
    html: str,
    base_metadata: Optional[Dict[str, Any]] = None,
    source_uri: str = "",
) -> Optional[Document]:
    """Parse a CiviX act (XHTML) into a tagged Document."""
    soup = BeautifulSoup(html, "html.parser")

    # Drop non-content nodes.
    for tag in soup(["script", "style", "head", "META", "meta", "link"]):
        tag.decompose()

    title = None
    if soup.title and soup.title.get_text(strip=True):
        title = soup.title.get_text(strip=True)
    if not title:
        h = soup.find(["h1", "h2"])
        title = h.get_text(strip=True) if h else "Untitled Act"

    body = soup.body or soup
    text = " ".join(body.get_text(separator=" ").split()).strip()
    if not text:
        logger.warning("BC doc %s produced no text; skipping", source_uri or title)
        return None

    metadata: Dict[str, Any] = dict(base_metadata or {})
    metadata.update(
        {
            "title": title,
            "document_type": "statute",
            "statute_numbers": [],
            "dates": [],
            "categories": [c.value for c in classify(text=text, title=title)],
            "in_force": True,
        }
    )
    return Document(text=text, metadata=metadata, source_path=source_uri)


@register_adapter
class BCLawsAdapter(SourceAdapter):
    """Traverses the CiviX statreg tree and parses each act's XHTML content."""

    name = "bc_laws"

    def __init__(self, entry, session: Optional[requests.Session] = None, max_acts: Optional[int] = None):
        super().__init__(entry)
        self._session = session or requests.Session()
        self.max_acts = max_acts  # cap for smoke runs; None = all

    def _get(self, url: str) -> str:
        time.sleep(REQUEST_DELAY_SECONDS)
        resp = self._session.get(url, timeout=30)
        if resp.status_code != 200:
            raise AdapterError(f"CiviX request failed ({resp.status_code}): {url}")
        return resp.text

    def _browse(self, path_id: str = "") -> List[CivixEntry]:
        url = f"{CIVIX_CONTENT_BASE}/{path_id}/".replace("statreg//", "statreg/")
        return parse_browse_listing(self._get(url))

    def documents(self) -> Iterator[Document]:
        base = self.base_metadata
        emitted = 0
        # statreg -> letter dirs -> act dirs -> content documents
        for letter in self._browse():
            if letter.kind != "dir":
                continue
            for act in self._browse(letter.id):
                if act.kind != "dir":
                    continue
                for item in self._browse(act.id):
                    if item.kind != "document":
                        continue
                    source_uri = f"{CIVIX_DOCUMENT_BASE}/{item.id}"
                    try:
                        doc = parse_document_html(
                            self._get(source_uri), base_metadata=base, source_uri=source_uri
                        )
                    except AdapterError as exc:
                        logger.error("Failed BC doc %s: %s", item.id, exc)
                        continue
                    if doc is not None:
                        emitted += 1
                        yield doc
                        if self.max_acts and emitted >= self.max_acts:
                            return
