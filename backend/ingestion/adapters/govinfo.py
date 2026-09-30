"""govinfo adapter — US federal statutes (US Code) in USLM XML (Decision 1 MVP).

Parses GPO's United States Legislative Markup (USLM, namespace
``http://schemas.gpo.gov/xml/uslm``) into tagged Documents. Parsing is
namespace-agnostic (``{*}`` wildcards) so it tolerates USLM 2.0/2.1 variations.

Bulk download of the USLM title files into ``data/raw`` (Decision 4) is the
ingestion CLI's job; this adapter parses XML already on disk, so it is testable
offline.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Iterator, Optional, Union

from lxml import etree

from backend.api.models import Document
from backend.categories import classify
from backend.ingestion.adapters.base import AdapterError, SourceAdapter, register_adapter

logger = logging.getLogger(__name__)

DC_NS = "http://purl.org/dc/elements/1.1/"


def _clean(el: Optional[etree._Element]) -> str:
    """Whitespace-collapsed text of an element (empty string if None)."""
    if el is None:
        return ""
    return " ".join("".join(el.itertext()).split())


def _extract_title(root: etree._Element) -> str:
    for tag in ("{*}docTitle", "{*}longTitle", "{*}heading"):
        text = _clean(root.find(f".//{tag}"))
        if text:
            return text
    dc_title = _clean(root.find(f".//{{{DC_NS}}}title"))
    return dc_title or "Untitled"


def parse_uslm_xml(
    xml: Union[str, bytes],
    base_metadata: Optional[Dict[str, Any]] = None,
    source_uri: str = "",
) -> Optional[Document]:
    """Parse one USLM document into a tagged Document, or None if it has no text."""
    if isinstance(xml, str):
        xml = xml.encode("utf-8")
    parser = etree.XMLParser(recover=True)
    try:
        root = etree.fromstring(xml, parser=parser)
    except etree.XMLSyntaxError as exc:
        raise AdapterError(f"Malformed USLM XML: {exc}") from exc
    if root is None:
        raise AdapterError("Empty or unparseable USLM XML")

    title = _extract_title(root)

    sections = root.findall(".//{*}section")
    if sections:
        parts = [_clean(s) for s in sections]
        text = "\n\n".join(p for p in parts if p).strip()
    else:
        main = root.find(".//{*}main")
        text = _clean(main if main is not None else root)

    if not text:
        logger.warning("USLM doc %s produced no text; skipping", source_uri or title)
        return None

    # Leading section number, if the first <num> carries a value (e.g. "Title 1").
    first_num = _clean(root.find(".//{*}main//{*}num"))

    metadata: Dict[str, Any] = dict(base_metadata or {})
    metadata.update(
        {
            "title": title,
            "document_type": "statute",
            "statute_numbers": [first_num] if first_num else [],
            "dates": [],
            "categories": [c.value for c in classify(text=text, title=title)],
            "in_force": True,
        }
    )
    return Document(text=f"{title}\n\n{text}", metadata=metadata, source_path=source_uri)


@register_adapter
class GovInfoAdapter(SourceAdapter):
    """Reads US Code USLM XML files from a local directory (Decision 4)."""

    name = "govinfo"

    def __init__(self, entry, source_dir: Optional[Union[str, Path]] = None):
        super().__init__(entry)
        self.source_dir = Path(source_dir) if source_dir else Path("data/raw") / entry.id

    def documents(self) -> Iterator[Document]:
        if not self.source_dir.exists():
            raise AdapterError(
                f"govinfo source dir not found: {self.source_dir}. "
                "Run the ingestion download step first."
            )
        base = self.base_metadata
        for xml_path in sorted(self.source_dir.rglob("*.xml")):
            try:
                doc = parse_uslm_xml(
                    xml_path.read_bytes(),
                    base_metadata=base,
                    source_uri=xml_path.name,
                )
            except AdapterError as exc:
                logger.error("Failed to parse %s: %s", xml_path, exc)
                continue
            if doc is not None:
                yield doc
