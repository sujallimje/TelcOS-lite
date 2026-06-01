#!/usr/bin/env python3
"""
TelcOS Lite – Document Loader Script
=====================================
Bootstrap script to ingest one or more source documents (txt, md, pdf) into
the ChromaDB knowledge base used by the cognitive reasoning layer.

Usage
-----
    # Ingest a single file:
    python scripts/load_documents.py --path docs/runbooks.md

    # Ingest all supported files under a directory (recursive):
    python scripts/load_documents.py --dir docs/

    # Custom persist directory and collection:
    python scripts/load_documents.py \\
        --dir docs/ \\
        --persist-dir /var/telcos/chroma \\
        --collection telcos_prod

    # Dry-run (list files that would be ingested, no writes):
    python scripts/load_documents.py --dir docs/ --dry-run

Exit codes
----------
    0 – success
    1 – partial failure (some files skipped)
    2 – fatal error (no chunks stored)
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path when executed directly
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.cognitive.vectorstore import (  # noqa: E402
    CognitiveVectorStore,
    SUPPORTED_EXTENSIONS as _SUPPORTED_EXTENSIONS,
    _DEFAULT_COLLECTION,
    _DEFAULT_PERSIST_DIR,
)


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _configure_logging(verbose: bool) -> None:
    """Configure structured console logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format=(
            '{"time": "%(asctime)s", "level": "%(levelname)s", '
            '"logger": "%(name)s", "message": "%(message)s"}'
        ),
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )


logger: logging.Logger = logging.getLogger("load_documents")


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def _collect_files(
    paths: list[Path],
    directories: list[Path],
    recursive: bool,
) -> list[Path]:
    """
    Build an ordered, deduplicated list of supported files to ingest.

    Args:
        paths: Explicitly specified file paths.
        directories: Root directories to scan.
        recursive: Whether to scan directories recursively.

    Returns:
        Deduplicated list of ``Path`` objects for supported document types.
    """
    seen: set[Path] = set()
    collected: list[Path] = []

    def _add(p: Path) -> None:
        resolved = p.resolve()
        if resolved in seen:
            return
        if not resolved.exists():
            logger.warning("Path does not exist – skipping", extra={"path": str(p)})
            return
        seen.add(resolved)
        collected.append(resolved)

    for fp in paths:
        fp = Path(fp)
        if fp.suffix.lower() not in _SUPPORTED_EXTENSIONS:
            logger.warning(
                "Unsupported file type – skipping",
                extra={"path": str(fp), "extension": fp.suffix},
            )
            continue
        _add(fp)

    for directory in directories:
        directory = Path(directory)
        if not directory.is_dir():
            logger.error(
                "Not a directory – skipping",
                extra={"path": str(directory)},
            )
            continue
        glob_fn = directory.rglob if recursive else directory.glob
        for ext in _SUPPORTED_EXTENSIONS:
            for candidate in sorted(glob_fn(f"*{ext}")):
                _add(candidate)

    return collected


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    """Return the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="load_documents",
        description="Ingest documents into the TelcOS Lite ChromaDB knowledge base.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    source = parser.add_argument_group("Source")
    source.add_argument(
        "--path",
        dest="paths",
        metavar="FILE",
        action="append",
        default=[],
        help="Path to a single document file (.txt, .md, .pdf). Repeatable.",
    )
    source.add_argument(
        "--dir",
        dest="directories",
        metavar="DIR",
        action="append",
        default=[],
        help=(
            "Directory to scan for supported documents. Repeatable. "
            "Combine with --no-recursive to disable subdirectory traversal."
        ),
    )
    source.add_argument(
        "--no-recursive",
        dest="recursive",
        action="store_false",
        default=True,
        help="Disable recursive directory scanning (default: recursive).",
    )

    store = parser.add_argument_group("Vector Store")
    store.add_argument(
        "--persist-dir",
        default=_DEFAULT_PERSIST_DIR,
        metavar="PATH",
        help=f"ChromaDB persistence directory (default: {_DEFAULT_PERSIST_DIR}).",
    )
    store.add_argument(
        "--collection",
        default=_DEFAULT_COLLECTION,
        metavar="NAME",
        help=f"ChromaDB collection name (default: {_DEFAULT_COLLECTION}).",
    )
    store.add_argument(
        "--embedding-model",
        default="sentence-transformers/all-MiniLM-L6-v2",
        metavar="MODEL",
        help="HuggingFace embedding model name or local path.",
    )
    store.add_argument(
        "--chunk-size",
        type=int,
        default=512,
        metavar="N",
        help="Maximum characters per text chunk (default: 512).",
    )
    store.add_argument(
        "--chunk-overlap",
        type=int,
        default=64,
        metavar="N",
        help="Overlap between consecutive chunks in characters (default: 64).",
    )

    misc = parser.add_argument_group("Misc")
    misc.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="List files that would be ingested without writing to ChromaDB.",
    )
    misc.add_argument(
        "--reset",
        action="store_true",
        default=False,
        help=(
            "Drop and recreate the ChromaDB collection before ingestion. "
            "CAUTION: destructive – all existing vectors are deleted."
        ),
    )
    misc.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        default=False,
        help="Enable DEBUG-level logging.",
    )

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    """
    Main entry point for the document loader.

    Args:
        argv: CLI arguments (defaults to ``sys.argv[1:]``).

    Returns:
        Exit code: 0 = success, 1 = partial failure, 2 = fatal error.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    _configure_logging(args.verbose)

    # ------------------------------------------------------------------ #
    # 1. Collect files
    # ------------------------------------------------------------------ #
    paths: list[Path] = [Path(p) for p in args.paths]
    directories: list[Path] = [Path(d) for d in args.directories]

    if not paths and not directories:
        logger.error(
            "No sources provided. Use --path FILE or --dir DIR.",
        )
        parser.print_help()
        return 2

    files: list[Path] = _collect_files(
        paths=paths,
        directories=directories,
        recursive=args.recursive,
    )

    if not files:
        logger.error("No supported documents found. Nothing to ingest.")
        return 2

    logger.info(
        "Documents discovered",
        extra={"count": len(files), "files": [str(f) for f in files]},
    )

    # ------------------------------------------------------------------ #
    # 2. Dry-run mode
    # ------------------------------------------------------------------ #
    if args.dry_run:
        print("\n[DRY RUN] Files that would be ingested:")
        for f in files:
            print(f"  {f}")
        print(f"\nTotal: {len(files)} file(s)")
        return 0

    # ------------------------------------------------------------------ #
    # 3. Initialise vector store
    # ------------------------------------------------------------------ #
    try:
        store = CognitiveVectorStore(
            persist_directory=args.persist_dir,
            collection_name=args.collection,
            embedding_model=args.embedding_model,
            chunk_size=args.chunk_size,
            chunk_overlap=args.chunk_overlap,
        )
    except Exception as exc:
        logger.exception(
            "Failed to initialise CognitiveVectorStore",
            extra={"error": str(exc)},
        )
        return 2

    # ------------------------------------------------------------------ #
    # 4. Optional reset
    # ------------------------------------------------------------------ #
    if args.reset:
        logger.warning(
            "Resetting collection as requested",
            extra={"collection": args.collection},
        )
        try:
            store.reset_collection()
        except Exception as exc:
            logger.exception(
                "Collection reset failed",
                extra={"error": str(exc)},
            )
            return 2

    # ------------------------------------------------------------------ #
    # 5. Ingest
    # ------------------------------------------------------------------ #
    try:
        total_chunks: int = store.ingest_documents(files)
    except Exception as exc:
        logger.exception(
            "Fatal error during ingestion",
            extra={"error": str(exc)},
        )
        return 2

    final_count: int = store.collection_count()

    if total_chunks == 0:
        logger.error(
            "Ingestion produced zero chunks. Check document content.",
            extra={"collection_size": final_count},
        )
        return 2

    logger.info(
        "Ingestion finished successfully",
        extra={
            "chunks_added": total_chunks,
            "collection_total": final_count,
            "collection": args.collection,
            "persist_dir": args.persist_dir,
        },
    )

    print(
        f"\n✓ Ingested {total_chunks} chunk(s) from {len(files)} file(s) "
        f"into collection '{args.collection}' "
        f"(total vectors in store: {final_count})."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())