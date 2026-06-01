"""
TelcOS Lite – Cognitive VectorStore Module
==========================================
Provides ChromaDB-backed persistent vector storage with LangChain integration
for semantic retrieval used by the autonomous operations framework.

Responsibilities:
- Document ingestion with chunking (txt, md, pdf)
- Embedding generation via a local abstraction layer
- Similarity search returning top-K ranked chunks
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Final, Sequence

import chromadb
from chromadb import Collection, PersistentClient
from chromadb.config import Settings
from langchain.schema import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import (
    TextLoader,
    UnstructuredMarkdownLoader,
    PyPDFLoader,
)
from langchain_community.embeddings import HuggingFaceEmbeddings

logger: logging.Logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_DEFAULT_COLLECTION: Final[str] = "telcos_knowledge_base"
_DEFAULT_PERSIST_DIR: Final[str] = "data/chroma"
_CHUNK_SIZE: Final[int] = 512
_CHUNK_OVERLAP: Final[int] = 64
_TOP_K: Final[int] = 3
_EMBED_MODEL: Final[str] = "sentence-transformers/all-MiniLM-L6-v2"

# Exported so tooling (e.g. load_documents.py) can reference supported types
SUPPORTED_EXTENSIONS: Final[frozenset[str]] = frozenset({".txt", ".md", ".pdf"})

# ---------------------------------------------------------------------------
# Loader registry
# ---------------------------------------------------------------------------
_LOADER_MAP: dict[str, type] = {
    ".txt": TextLoader,
    ".md": UnstructuredMarkdownLoader,
    ".pdf": PyPDFLoader,
}


# ---------------------------------------------------------------------------
# Local embedding abstraction
# ---------------------------------------------------------------------------
class LocalEmbeddings:
    """
    Thin wrapper around a HuggingFace sentence-transformer model.

    This abstraction isolates the embedding provider so it can be swapped
    (e.g., for an Ollama or custom ONNX model) without touching ingestion
    or search logic.
    """

    def __init__(self, model_name: str = _EMBED_MODEL) -> None:
        """
        Initialise the local embedding model.

        Args:
            model_name: HuggingFace model identifier or local path.

        Raises:
            RuntimeError: If the model cannot be loaded.
        """
        logger.info(
            "Loading local embedding model",
            extra={"model": model_name},
        )
        try:
            self._model: HuggingFaceEmbeddings = HuggingFaceEmbeddings(
                model_name=model_name,
                model_kwargs={"device": "cpu"},
                encode_kwargs={"normalize_embeddings": True},
            )
        except Exception as exc:
            logger.exception(
                "Failed to load embedding model",
                extra={"model": model_name, "error": str(exc)},
            )
            raise RuntimeError(
                f"Embedding model initialisation failed: {exc}"
            ) from exc

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Return embeddings for a batch of texts."""
        return self._model.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        """Return the embedding for a single query string."""
        return self._model.embed_query(text)


# ---------------------------------------------------------------------------
# VectorStore
# ---------------------------------------------------------------------------
class CognitiveVectorStore:
    """
    ChromaDB-backed vector store for TelcOS Lite knowledge retrieval.

    Supports ingestion of .txt, .md, and .pdf documents, splits them into
    overlapping chunks, embeds them locally, and exposes a similarity search
    API used by the cognitive reasoning layer.

    Args:
        persist_directory: Filesystem path for ChromaDB persistence.
        collection_name: Name of the ChromaDB collection.
        embedding_model: HuggingFace model name for local embeddings.
        chunk_size: Maximum token count per text chunk.
        chunk_overlap: Overlap between consecutive chunks (tokens).
    """

    def __init__(
        self,
        persist_directory: str = _DEFAULT_PERSIST_DIR,
        collection_name: str = _DEFAULT_COLLECTION,
        embedding_model: str = _EMBED_MODEL,
        chunk_size: int = _CHUNK_SIZE,
        chunk_overlap: int = _CHUNK_OVERLAP,
    ) -> None:
        self._persist_directory = persist_directory
        self._collection_name = collection_name
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

        Path(persist_directory).mkdir(parents=True, exist_ok=True)

        self._embeddings: LocalEmbeddings = LocalEmbeddings(
            model_name=embedding_model
        )

        self._client: PersistentClient = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(anonymized_telemetry=False),
        )

        self._collection: Collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

        self._splitter: RecursiveCharacterTextSplitter = (
            RecursiveCharacterTextSplitter(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                length_function=len,
                add_start_index=True,
            )
        )

        logger.info(
            "CognitiveVectorStore initialised",
            extra={
                "persist_directory": persist_directory,
                "collection": collection_name,
                "chunk_size": chunk_size,
                "chunk_overlap": chunk_overlap,
            },
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_file(self, path: Path) -> list[Document]:
        """
        Load a single file using the appropriate LangChain loader.

        Args:
            path: Absolute or relative path to the source document.

        Returns:
            List of LangChain ``Document`` objects.

        Raises:
            ValueError: If the file extension is unsupported.
            IOError: If the file cannot be read.
        """
        suffix: str = path.suffix.lower()
        loader_cls = _LOADER_MAP.get(suffix)

        if loader_cls is None:
            raise ValueError(
                f"Unsupported file type '{suffix}' for path '{path}'. "
                f"Supported: {list(_LOADER_MAP)}"
            )

        try:
            loader = loader_cls(str(path))
            docs: list[Document] = loader.load()
            logger.debug(
                "File loaded",
                extra={"path": str(path), "doc_count": len(docs)},
            )
            return docs
        except Exception as exc:
            logger.error(
                "Failed to load file",
                extra={"path": str(path), "error": str(exc)},
            )
            raise IOError(f"Cannot read '{path}': {exc}") from exc

    def _upsert_chunks(self, chunks: list[Document]) -> None:
        """
        Embed and upsert chunks into ChromaDB.

        IDs are derived from source path + start index to guarantee
        idempotent re-ingestion (same document re-loaded will overwrite).

        Args:
            chunks: Split LangChain ``Document`` objects.
        """
        if not chunks:
            logger.warning("No chunks to upsert.")
            return

        texts: list[str] = [c.page_content for c in chunks]
        metadatas: list[dict] = [c.metadata for c in chunks]

        ids: list[str] = [
            f"{m.get('source', 'unknown')}::{m.get('start_index', i)}"
            for i, m in enumerate(metadatas)
        ]

        try:
            vectors: list[list[float]] = self._embeddings.embed_documents(texts)
        except Exception as exc:
            logger.exception(
                "Embedding failed during upsert",
                extra={"chunk_count": len(texts), "error": str(exc)},
            )
            raise

        self._collection.upsert(
            ids=ids,
            embeddings=vectors,
            documents=texts,
            metadatas=metadatas,
        )

        logger.info(
            "Chunks upserted into ChromaDB",
            extra={
                "collection": self._collection_name,
                "upserted": len(ids),
            },
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ingest_documents(self, paths: Sequence[str | Path]) -> int:
        """
        Ingest one or more documents into the vector store.

        Each document is loaded via its type-appropriate LangChain loader,
        split into overlapping chunks, embedded locally, and upserted into
        ChromaDB. Re-ingesting the same file is idempotent.

        Args:
            paths: Iterable of filesystem paths to .txt, .md, or .pdf files.

        Returns:
            Total number of chunks stored across all provided documents.

        Raises:
            ValueError: If an unsupported file type is encountered.
            IOError: If a file cannot be read.
        """
        total_chunks: int = 0

        for raw_path in paths:
            path = Path(raw_path).resolve()

            if not path.exists():
                logger.error(
                    "Document not found – skipping",
                    extra={"path": str(path)},
                )
                continue

            logger.info(
                "Ingesting document",
                extra={"path": str(path)},
            )

            try:
                raw_docs: list[Document] = self._load_file(path)
                chunks: list[Document] = self._splitter.split_documents(raw_docs)

                logger.debug(
                    "Document split into chunks",
                    extra={"path": str(path), "chunks": len(chunks)},
                )

                self._upsert_chunks(chunks)
                total_chunks += len(chunks)

            except (ValueError, IOError) as exc:
                logger.error(
                    "Skipping document due to load/split error",
                    extra={"path": str(path), "error": str(exc)},
                )
                continue

        logger.info(
            "Ingestion complete",
            extra={"total_chunks": total_chunks, "files_processed": len(list(paths))},
        )
        return total_chunks

    def search_context(
        self,
        query: str,
        top_k: int = _TOP_K,
    ) -> list[dict[str, str | float]]:
        """
        Perform cosine similarity search against the knowledge base.

        Args:
            query: Natural-language query string.
            top_k: Number of top-ranked chunks to return (default: 3).

        Returns:
            List of dicts, each containing:
            - ``content`` (str): The chunk text.
            - ``source`` (str): Origin file path from metadata.
            - ``score`` (float): Cosine similarity score (higher = more similar).
            - ``start_index`` (int): Character offset of chunk in source document.

        Raises:
            ValueError: If query is empty.
            RuntimeError: If the ChromaDB query fails.
        """
        if not query or not query.strip():
            raise ValueError("Query string must not be empty.")

        logger.info(
            "Executing similarity search",
            extra={"query_preview": query[:80], "top_k": top_k},
        )

        try:
            query_vector: list[float] = self._embeddings.embed_query(query)

            results = self._collection.query(
                query_embeddings=[query_vector],
                n_results=min(top_k, self._collection.count() or top_k),
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:
            logger.exception(
                "ChromaDB query failed",
                extra={"query_preview": query[:80], "error": str(exc)},
            )
            raise RuntimeError(f"Similarity search failed: {exc}") from exc

        documents: list[str] = results.get("documents", [[]])[0]
        metadatas: list[dict] = results.get("metadatas", [[]])[0]
        distances: list[float] = results.get("distances", [[]])[0]

        # ChromaDB returns L2 or cosine distance; convert distance → similarity
        hits: list[dict[str, str | float]] = []
        for doc, meta, dist in zip(documents, metadatas, distances):
            similarity: float = round(1.0 - dist, 6)
            hits.append(
                {
                    "content": doc,
                    "source": meta.get("source", "unknown"),
                    "score": similarity,
                    "start_index": meta.get("start_index", -1),
                }
            )

        logger.info(
            "Search complete",
            extra={"hits_returned": len(hits)},
        )
        return hits

    def collection_count(self) -> int:
        """Return the number of vectors currently stored in the collection."""
        return self._collection.count()

    def reset_collection(self) -> None:
        """
        Delete and recreate the ChromaDB collection.

        Intended for development / test teardown only. In production,
        prefer targeted upserts.
        """
        logger.warning(
            "Resetting ChromaDB collection",
            extra={"collection": self._collection_name},
        )
        self._client.delete_collection(self._collection_name)
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine"},
        )