# utils/chroma.py: ChromaDB utility functions for managing and querying a ChromaDB collection.
import logging
import os
import uuid
from typing import Any

logger = logging.getLogger("FreesonaBot")

try:
    import chromadb
except ImportError:
    chromadb = None

from dotenv import load_dotenv

load_dotenv()

_chroma_client: Any = None


def get_chroma_client() -> Any | None:
    global _chroma_client
    if chromadb is None:
        return None
    if _chroma_client is None:
        persist_directory = os.getenv("CHROMA_PERSIST_DIRECTORY", "./.chroma")
        _chroma_client = chromadb.PersistentClient(path=persist_directory)
    return _chroma_client


def get_collection(collection_name: str | None = None) -> Any | None:
    client = get_chroma_client()
    if client is None:
        return None
    name = collection_name or os.getenv("CHROMA_COLLECTION", "freesona")
    return client.get_or_create_collection(name=name)


def add_knowledge(
    document: str,
    *,
    source: str = "manual",
    title: str | None = None,
    collection_name: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    collection = get_collection(collection_name)
    if collection is None:
        return ""

    doc_id = f"kb_{uuid.uuid4().hex}"
    entry_metadata = {"source": source or "manual"}
    if title:
        entry_metadata["title"] = str(title).strip()
    if metadata:
        entry_metadata.update({k: str(v) for k, v in metadata.items() if v is not None})

    try:
        collection.add(
            documents=[document],
            metadatas=[entry_metadata],
            ids=[doc_id],
        )
        return doc_id
    except Exception as exc:
        logger.error(f"Chroma add error: {exc}")
        return ""


def list_knowledge(collection_name: str | None = None) -> list[dict[str, Any]]:
    collection = get_collection(collection_name)
    if collection is None:
        return []

    try:
        result = collection.get(include=["documents", "metadatas"])
    except Exception as exc:
        logger.error(f"Chroma list error: {exc}")
        return []

    ids = result.get("ids", []) or []
    docs = result.get("documents", []) or []
    metadatas = result.get("metadatas", []) or []

    entries: list[dict[str, Any]] = []
    for index, doc_id in enumerate(ids):
        entries.append({
            "id": doc_id,
            "document": docs[index] if index < len(docs) else "",
            "metadata": metadatas[index] if index < len(metadatas) else {},
        })
    return entries


def delete_knowledge(doc_id: str, collection_name: str | None = None) -> bool:
    collection = get_collection(collection_name)
    if collection is None:
        return False

    try:
        collection.delete(ids=[doc_id])
        return True
    except Exception as exc:
        logger.error(f"Chroma delete error: {exc}")
        return False


def query_knowledge(query: str, limit: int = 3, collection_name: str | None = None) -> list[str]:
    collection = get_collection(collection_name)
    if collection is None:
        return []
    try:
        result = collection.query(query_texts=[query], n_results=limit)
        docs = result.get("documents", []) or []
        flattened = [item for sublist in docs for item in sublist]
        return [doc for doc in flattened if isinstance(doc, str) and doc.strip()]
    except Exception as exc:
        logger.error(f"Chroma query error: {exc}")
        return []