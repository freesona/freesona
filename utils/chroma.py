# utils/chroma.py: ChromaDB utility functions for managing and querying a ChromaDB collection.
import io
import logging
import os
import uuid
import zipfile
from typing import Any
from xml.etree import ElementTree as ET

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


def extract_text_from_bytes(filename: str, data: bytes) -> str:
    lower_name = (filename or "").lower()

    if lower_name.endswith(".pdf"):
        try:
            from pypdf import PdfReader
        except ImportError:
            logger.warning("pypdf is not installed; falling back to raw bytes decode for PDF input.")
            return data.decode("utf-8", errors="ignore").strip()

        reader = PdfReader(io.BytesIO(data))
        pages: list[str] = []
        for page in reader.pages:
            extracted = page.extract_text() or ""
            if extracted.strip():
                pages.append(extracted.strip())
        return "\n\n".join(pages).strip()

    if lower_name.endswith(".epub"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                # Normalize namespace handling for container parsing
                container_data = archive.read("META-INF/container.xml")
                # Use universal namespace handling instead of string replacement
                container = ET.fromstring(container_data)
                # Find rootfile with namespace-agnostic approach
                rootfile = None
                for elem in container.iter():
                    if elem.tag.endswith('rootfile'):
                        rootfile = elem
                        break
                if rootfile is None:
                    logger.warning("EPUB container.xml missing rootfile")
                    return ""

                opf_path = rootfile.attrib.get("full-path")
                if not opf_path:
                    logger.warning("EPUB rootfile missing full-path")
                    return ""

                # Normalize namespace handling for OPF parsing
                opf_data = archive.read(opf_path)
                opf_root = ET.fromstring(opf_data)
                
                # Extract manifest items with namespace-agnostic approach
                item_map = {}
                for item in opf_root.iter():
                    if item.tag.endswith('item'):
                        item_id = item.attrib.get("id")
                        href = item.attrib.get("href")
                        if item_id and href:
                            item_map[item_id] = href

                # Extract spine item references with namespace-agnostic approach
                spine_ids = []
                for itemref in opf_root.iter():
                    if itemref.tag.endswith('itemref'):
                        idref = itemref.attrib.get("idref")
                        if idref:
                            spine_ids.append(idref)

                text_parts: list[str] = []
                import os
                # Get the directory of the OPF file to resolve relative paths correctly
                opf_dir = os.path.dirname(opf_path) if '/' in opf_path else ''
                
                for item_id in spine_ids:
                    href = item_map.get(item_id)
                    if not href:
                        continue
                    # Resolve the href relative to the OPF file's directory
                    if opf_dir and not href.startswith(opf_dir):
                        full_href = f"{opf_dir}/{href}" if opf_dir else href
                    else:
                        full_href = href
                    
                    try:
                        chapter_xml = archive.read(full_href)
                    except KeyError:
                        # Try without the directory prefix if the first attempt failed
                        try:
                            chapter_xml = archive.read(href)
                        except KeyError:
                            continue
                    
                    # Normalize namespace handling for chapter parsing
                    chapter_root = ET.fromstring(chapter_xml)
                    # Find body with namespace-agnostic approach
                    body = None
                    for elem in chapter_root.iter():
                        if elem.tag.endswith('body'):
                            body = elem
                            break
                    if body is None:
                        continue
                    
                    text = " ".join(part.strip() for part in body.itertext() if part and part.strip())
                    if text:
                        text_parts.append(text)

                result = "\n\n".join(text_parts).strip()
                if not result:
                    logger.warning("EPUB extraction returned empty text")
                return result
        except Exception as exc:
            logger.warning(f"Failed to decode EPUB attachment {filename}: {exc}")
            return ""

    return data.decode("utf-8", errors="ignore").strip() or data.decode("latin-1", errors="ignore").strip()


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


def list_knowledge(limit: int = 20, collection_name: str | None = None) -> list[dict[str, Any]]:
    collection = get_collection(collection_name)
    if collection is None:
        return []

    try:
        result = collection.get(limit=limit, include=["documents", "metadatas"])
    except TypeError:
        try:
            result = collection.get(include=["documents", "metadatas"])
        except Exception as exc:
            logger.error(f"Chroma list error: {exc}")
            return []
    except Exception as exc:
        logger.error(f"Chroma list error: {exc}")
        return []

    ids = (result.get("ids", []) or [])[:limit]
    docs = (result.get("documents", []) or [])[:limit]
    metadatas = (result.get("metadatas", []) or [])[:limit]

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