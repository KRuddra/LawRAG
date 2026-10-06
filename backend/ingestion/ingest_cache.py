"""Document-level content-hash cache (Decision 10).

Avoids re-embedding unchanged documents across ingestion runs. Keyed by
``doc_id`` (a document's source path/URI) with the SHA-256 of its text. If a
document's hash is unchanged since the last run, the whole document is skipped —
no delete, no re-chunk, no re-embed. Persisted as a small JSON file under the
in-repo data tree (Decision 4). Pure standard library.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

DEFAULT_CACHE_PATH = Path("data") / "ingest_cache.json"


class IngestCache:
    """Maps doc_id -> sha256(text) to detect unchanged documents."""

    def __init__(self, path: Optional[Path] = None, hashes: Optional[Dict[str, str]] = None):
        self.path = Path(path) if path else DEFAULT_CACHE_PATH
        self._hashes: Dict[str, str] = dict(hashes or {})

    @staticmethod
    def _hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def is_current(self, doc_id: str, text: str) -> bool:
        """True if this doc_id was last ingested with identical text."""
        return self._hashes.get(doc_id) == self._hash(text)

    def record(self, doc_id: str, text: str) -> None:
        self._hashes[doc_id] = self._hash(text)

    def forget(self, doc_id: str) -> None:
        self._hashes.pop(doc_id, None)

    def __len__(self) -> int:
        return len(self._hashes)

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "IngestCache":
        path = Path(path) if path else DEFAULT_CACHE_PATH
        if not path.exists():
            return cls(path=path)
        try:
            hashes = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(hashes, dict):
                raise ValueError("cache file is not a JSON object")
            return cls(path=path, hashes=hashes)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Ignoring corrupt ingest cache at %s: %s", path, exc)
            return cls(path=path)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._hashes, indent=2), encoding="utf-8")
