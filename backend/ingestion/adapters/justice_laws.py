"""Justice Laws adapter — Canadian federal Acts (Decision 1 MVP source).

Parses the Department of Justice consolidated-Acts XML (the
``justicecanada/laws-lois-xml`` bulk format) into tagged Documents.

Schema (validated against real samples):

    <Statute in-force="yes" xml:lang="en" lims:current-date="..."
             xmlns:lims="http://justice.gc.ca/lims">
      <Identification>
        <LongTitle>An Act respecting ...</LongTitle>
        <ShortTitle status="official">Foo Act</ShortTitle>
        <Chapter><ConsolidatedNumber official="yes">F-12</ConsolidatedNumber></Chapter>
      </Identification>
      <Body>
        <Section><MarginalNote>..</MarginalNote><Label>1</Label><Text>..</Text></Section>
        ...
      </Body>
      <Repealed>..</Repealed>   <!-- present only for repealed Acts -->
    </Statute>

Only in-force Acts are emitted (Decision 9: latest-only, current law). The bulk
download of the ~300 MB XML tree into ``data/raw`` (Decision 4: in-repo storage)
is handled by the ingestion CLI, not here; this adapter parses XML files that
already exist on disk so it is fully testable offline.
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

LIMS_NS = "http://justice.gc.ca/lims"
JUSTICE_LAWS_ACT_BASE = "https://laws-lois.justice.gc.ca/eng/acts/"


def _first_text(root: etree._Element, xpath: str) -> Optional[str]:
    """Return the concatenated text of the first element matching xpath."""
    found = root.find(xpath)
    if found is None:
        return None
    text = "".join(found.itertext()).strip()
    return text or None


def _is_in_force(root: etree._Element) -> bool:
    """An Act is in force when in-force="yes" and it carries no <Repealed>."""
    if root.get("in-force", "").lower() == "no":
        return False
    if root.find(".//Repealed") is not None:
        return False
    return True


def _section_text(section: etree._Element) -> str:
    """Render one <Section> as readable text (label, marginal note, body)."""
    label = _first_text(section, "Label") or ""
    note = _first_text(section, "MarginalNote") or ""
    texts = ["".join(t.itertext()).strip() for t in section.findall(".//Text")]
    body = " ".join(t for t in texts if t).strip()
    header_parts = [p for p in (f"Section {label}" if label else "", note) if p]
    header = " — ".join(header_parts)
    return f"{header}\n{body}".strip() if header else body


def parse_statute_xml(
    xml: Union[str, bytes],
    base_metadata: Optional[Dict[str, Any]] = None,
    source_uri: str = "",
) -> Optional[Document]:
    """Parse one Justice Laws Act XML document into a tagged Document.

    Returns ``None`` for Acts that are not in force (repealed / not-yet-in-force)
    so only current law is ingested. Raises :class:`AdapterError` on malformed
    XML.
    """
    if isinstance(xml, str):
        xml = xml.encode("utf-8")
    parser = etree.XMLParser(recover=True, remove_blank_text=False)
    try:
        root = etree.fromstring(xml, parser=parser)
    except etree.XMLSyntaxError as exc:
        raise AdapterError(f"Malformed Justice Laws XML: {exc}") from exc
    if root is None or root.tag != "Statute":
        raise AdapterError(f"Expected <Statute> root, got {getattr(root, 'tag', None)!r}")

    if not _is_in_force(root):
        logger.info("Skipping non-in-force Act: %s", source_uri or "<unknown>")
        return None

    title = (
        _first_text(root, ".//ShortTitle")
        or _first_text(root, ".//LongTitle")
        or "Untitled Act"
    )
    consolidated_number = _first_text(root, ".//ConsolidatedNumber")
    current_date = root.get(f"{{{LIMS_NS}}}current-date")

    body = root.find("Body")
    sections = body.findall(".//Section") if body is not None else []
    if sections:
        text = "\n\n".join(_section_text(s) for s in sections).strip()
    else:
        text = "".join(body.itertext()).strip() if body is not None else ""

    if not text:
        logger.warning("Act %s produced no body text; skipping", title)
        return None

    metadata: Dict[str, Any] = dict(base_metadata or {})
    metadata.update(
        {
            "title": title,
            "document_type": "statute",
            "statute_numbers": [consolidated_number] if consolidated_number else [],
            "dates": [current_date] if current_date else [],
            "categories": [c.value for c in classify(text=text, title=title)],
            "in_force": True,
        }
    )

    return Document(text=f"{title}\n\n{text}", metadata=metadata, source_path=source_uri)


@register_adapter
class JusticeLawsAdapter(SourceAdapter):
    """Reads Justice Laws Act XML files from a local directory (Decision 4)."""

    name = "justice_laws"

    def __init__(self, entry, source_dir: Optional[Union[str, Path]] = None):
        super().__init__(entry)
        # Default download location under the in-repo raw data tree.
        self.source_dir = Path(source_dir) if source_dir else Path("data/raw") / entry.id

    def documents(self) -> Iterator[Document]:
        if not self.source_dir.exists():
            raise AdapterError(
                f"Justice Laws source dir not found: {self.source_dir}. "
                "Run the ingestion download step first."
            )
        base = self.base_metadata
        for xml_path in sorted(self.source_dir.rglob("*.xml")):
            try:
                doc = parse_statute_xml(
                    xml_path.read_bytes(),
                    base_metadata=base,
                    source_uri=f"{JUSTICE_LAWS_ACT_BASE}{xml_path.stem}/",
                )
            except AdapterError as exc:
                logger.error("Failed to parse %s: %s", xml_path, exc)
                continue
            if doc is not None:
                yield doc
