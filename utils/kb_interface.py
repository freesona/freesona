#!/usr/bin/env python3
# utils/kb_interface.py: Knowledge base interface and ChromaDB adapter.
# Keeps ChromaDB types out of the generation layer.


from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class KnowledgeBase(Protocol):
    """Interface for querying persona knowledge.

    Implementations may be backed by ChromaDB, SQLite, or a fake for tests.
    """

    def query(
        self,
        query: str,
        *,
        limit: int = 3,
        persona: str | None = None,
    ) -> list[dict[str, Any]]:
        """Query the knowledge base.

        Args:
            query: The search query text.
            limit: Maximum number of results to return.
            persona: Optional persona identifier to filter results.

        Returns:
            List of knowledge entries with document, metadata, and distance.
        """
        ...


class ChromaKnowledgeBase:
    """ChromaDB-backed knowledge base implementation."""

    def __init__(self, collection_name: str | None = None) -> None:
        self._collection_name = collection_name

    def query(
        self,
        query: str,
        *,
        limit: int = 3,
        persona: str | None = None,
    ) -> list[dict[str, Any]]:
        from utils.chroma import get_collection, ChromaBackendError

        collection = get_collection(self._collection_name)
        if collection is None:
            raise ChromaBackendError("Chroma backend is unavailable")

        where_clause = {"persona": persona} if persona else None

        try:
            result = collection.query(
                query_texts=[query],
                n_results=limit,
                where=where_clause,
                include=["documents", "metadatas", "distances"],
            )

            docs = result.get("documents", [[]])[0] or []
            metadatas = result.get("metadatas", [[]])[0] or []
            distances = result.get("distances", [[]])[0] or []

            entries = []
            for i, doc in enumerate(docs):
                if isinstance(doc, str) and doc.strip():
                    entries.append(
                        {
                            "document": doc,
                            "metadata": (
                                metadatas[i] if i < len(metadatas) else {}
                            ),
                            "distance": (
                                distances[i] if i < len(distances) else None
                            ),
                        }
                    )
            return entries

        except (ValueError, RuntimeError, OSError) as exc:
            raise ChromaBackendError("Chroma search failed") from exc


class FakeKnowledgeBase:
    """In-memory fake knowledge base for testing."""

    def __init__(self, entries: list[dict[str, Any]] | None = None) -> None:
        self._entries = entries or []

    def query(
        self,
        query: str,
        *,
        limit: int = 3,
        persona: str | None = None,
    ) -> list[dict[str, Any]]:
        results = []
        for entry in self._entries:
            if persona is not None and entry.get("persona") != persona:
                continue
            results.append(entry)
        return results[:limit]
