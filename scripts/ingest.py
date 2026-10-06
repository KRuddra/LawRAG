#!/usr/bin/env python3
"""Ingestion CLI (Decision 11) — decoupled from the serving API.

Subcommands:
  list              Show approved + active sources (no API key needed).
  download <id>     Fetch a source's bulk data into data/raw/<id> (Decision 4).
  ingest [--source <id>]
                    Parse -> chunk -> embed(cache) -> upsert. Requires
                    OPENAI_API_KEY (embeddings).

Examples:
  python scripts/ingest.py list
  python scripts/ingest.py download ca-justice-laws
  python scripts/ingest.py ingest --source ca-justice-laws
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path

# Make the repo importable when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.ingestion.source_registry import ingestible_sources, load_registry  # noqa: E402
from backend.ingestion.adapters import get_adapter  # noqa: E402
from backend.ingestion.ingest_cache import IngestCache  # noqa: E402
from backend.ingestion.pipeline import ingest_source  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ingest")

RAW_DIR = Path("data/raw")
JUSTICE_LAWS_REPO = "https://github.com/justicecanada/laws-lois-xml"


def cmd_list(_: argparse.Namespace) -> int:
    entries = load_registry()
    ingestible = {e.id for e in ingestible_sources(entries)}
    print(f"{'ID':<28} {'JURISDICTION':<12} {'ADAPTER':<14} {'STATUS':<10} INGESTIBLE")
    for e in entries:
        mark = "yes" if e.id in ingestible else "no"
        print(f"{e.id:<28} {e.jurisdiction_id:<12} {e.adapter:<14} {e.status.value:<10} {mark}")
    return 0


def cmd_download(args: argparse.Namespace) -> int:
    entry = next((e for e in load_registry() if e.id == args.source), None)
    if entry is None:
        logger.error("Unknown source id: %s", args.source)
        return 1

    dest = RAW_DIR / entry.id
    if entry.adapter == "justice_laws":
        dest.mkdir(parents=True, exist_ok=True)
        # Sparse clone only the English Acts to keep the download small.
        logger.info("Sparse-cloning %s (eng/acts) into %s ...", JUSTICE_LAWS_REPO, dest)
        subprocess.run(
            ["git", "clone", "--depth", "1", "--filter=blob:none", "--sparse",
             JUSTICE_LAWS_REPO, str(dest)],
            check=True,
        )
        subprocess.run(["git", "-C", str(dest), "sparse-checkout", "set", "eng/acts"], check=True)
        logger.info("Done. Acts in %s/eng/acts", dest)
        return 0
    if entry.adapter == "bc_laws":
        logger.info("bc_laws uses the live CiviX API; no download step — run `ingest` directly.")
        return 0
    if entry.adapter == "govinfo":
        logger.info(
            "govinfo USLM: download the US Code USLM XML release into %s "
            "(bulk: https://www.govinfo.gov/bulkdata/USCODE), then run `ingest`.", dest,
        )
        return 0
    logger.error("No download routine for adapter %r", entry.adapter)
    return 1


def cmd_ingest(args: argparse.Namespace) -> int:
    # Imported lazily so `list`/`download` work without an OpenAI key.
    from backend.retrieval.vector_store import get_vector_store

    entries = ingestible_sources()
    if args.source:
        entries = [e for e in entries if e.id == args.source]
        if not entries:
            logger.error("Source %r is not an ingestible (approved + active) source.", args.source)
            return 1

    vector_store = get_vector_store()
    cache = IngestCache.load()

    overall_ok = True
    for entry in entries:
        logger.info("Ingesting source: %s", entry.id)
        adapter = get_adapter(entry)
        stats = ingest_source(adapter, vector_store, cache, source_id=entry.id)
        print(stats.as_dict())
        if stats.errors:
            overall_ok = False
    return 0 if overall_ok else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Legal RAG ingestion pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="list sources and whether they are ingestible").set_defaults(func=cmd_list)

    p_dl = sub.add_parser("download", help="download a source's bulk data into data/raw/<id>")
    p_dl.add_argument("source", help="source id (e.g. ca-justice-laws)")
    p_dl.set_defaults(func=cmd_download)

    p_ing = sub.add_parser("ingest", help="parse, chunk, embed, and index sources")
    p_ing.add_argument("--source", help="only ingest this source id (default: all ingestible)")
    p_ing.set_defaults(func=cmd_ingest)

    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
