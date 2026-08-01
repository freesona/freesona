# utils/chroma.py: ChromaDB utility functions for managing and
# querying a ChromaDB collection. Implements the Persona-Agnostic
# Knowledge Base (RAG) architecture.
from dotenv import load_dotenv
import io
import json
import logging
import os
import uuid
import xml.etree.ElementTree as ElementTree
import zipfile
from typing import Any, Protocol, cast

logger = logging.getLogger("FreesonaBot")

try:
    import chromadb
except ImportError:
    chromadb = None


load_dotenv()

_chroma_client: Any = None


class ChromaCollection(Protocol):
    """Minimum ChromaDB collection interface used by this module."""

    def add(self, **kwargs: Any) -> None: ...

    def delete(self, **kwargs: Any) -> None: ...

    def get(self, **kwargs: Any) -> dict[str, Any]: ...

    def query(self, **kwargs: Any) -> dict[str, Any]: ...


# Required metadata fields per the Persona Knowledge Base schema
REQUIRED_METADATA_FIELDS = frozenset(
    ("persona", "source", "source_type", "entry_type", "topics")
)
# Optional metadata fields
OPTIONAL_METADATA_FIELDS = frozenset(
    (
        "episode",
        "chapter",
        "scene",
        "speaker",
        "timestamp",
        "canon_level",
        "tags",
        "schema_version",
        "embedding_model",
    )
)

# Valid values for metadata fields
VALID_SOURCE_TYPES = frozenset(
    (
        "anime",
        "novel",
        "manga",
        "game",
        "guidebook",
        "interview",
        "website",
        "other",
    )
)
VALID_ENTRY_TYPES = frozenset(
    ("dialogue", "narration", "event", "relationship", "description")
)
VALID_CANON_LEVELS = frozenset(
    ("canon", "semi-canon", "non-canon", "headcanon", "alternate")
)


def get_chroma_client() -> Any | None:
    global _chroma_client
    if chromadb is None:
        return None
    if _chroma_client is None:
        persist_directory = os.getenv("CHROMA_PERSIST_DIRECTORY", "./.chroma")
        _chroma_client = chromadb.PersistentClient(path=persist_directory)
    return _chroma_client


def get_collection(
    collection_name: str | None = None,
) -> ChromaCollection | None:
    client = get_chroma_client()
    if client is None:
        return None
    resolved_client = cast(Any, client)
    name = collection_name or os.getenv("CHROMA_COLLECTION", "freesona")
    return cast(
        ChromaCollection, resolved_client.get_or_create_collection(name=name)
    )


def parse_discord_chat_json(raw_bytes: bytes) -> str:
    """Parses exported Discord message JSON arrays into plain text logs."""
    try:
        data = json.loads(raw_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return ""

    if not isinstance(data, list):
        return ""

    formatted_messages = []

    # Sort chronological (oldest to newest)
    for msg in reversed(data):
        if not isinstance(msg, dict):
            continue

        author = (
            msg.get("userName")
            or msg.get("author", {}).get("username")
            or "Unknown"
        )
        content = (msg.get("content") or "").strip()
        timestamp = msg.get("timestamp", "").split("T")[
            0
        ]  # Extracts YYYY-MM-DD

        if content:
            if timestamp:
                formatted_messages.append(f"[{timestamp}] {author}: {content}")
            else:
                formatted_messages.append(f"{author}: {content}")

    return "\n".join(formatted_messages)


def extract_text_from_bytes(filename: str, data: bytes) -> str:
    """Extracts plain text from various file formats (JSON,
    PDF, EPUB, TXT, MD)."""
    lower_name = (filename or "").lower()

    if lower_name.endswith(".json"):
        extracted_json = parse_discord_chat_json(data)
        if extracted_json:
            return extracted_json

    if lower_name.endswith(".pdf"):
        try:
            from pypdf import PdfReader
        except ImportError:
            logger.warning(
                "pypdf is not installed; falling back to raw "
                "bytes decode for PDF input."
            )
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
                container_data = archive.read("META-INF/container.xml")
                container = ElementTree.fromstring(container_data)

                rootfile = None
                for elem in container.iter():
                    if elem.tag.endswith("rootfile"):
                        rootfile = elem
                        break
                if rootfile is None:
                    logger.warning("EPUB container.xml missing rootfile")
                    return ""

                opf_path = rootfile.attrib.get("full-path")
                if not opf_path:
                    logger.warning("EPUB rootfile missing full-path")
                    return ""

                opf_data = archive.read(opf_path)
                opf_root = ElementTree.fromstring(opf_data)

                item_map = {}
                for item in opf_root.iter():
                    if item.tag.endswith("item"):
                        item_id = item.attrib.get("id")
                        href = item.attrib.get("href")
                        if item_id and href:
                            item_map[item_id] = href

                spine_ids = []
                for itemref in opf_root.iter():
                    if itemref.tag.endswith("itemref"):
                        idref = itemref.attrib.get("idref")
                        if idref:
                            spine_ids.append(idref)

                text_parts: list[str] = []
                opf_dir = os.path.dirname(opf_path) if "/" in opf_path else ""

                for item_id in spine_ids:
                    href_value = item_map.get(item_id)
                    if not isinstance(href_value, str) or not href_value:
                        continue
                    href = href_value

                    if opf_dir and not href.startswith(opf_dir):
                        full_href = f"{opf_dir}/{href}" if opf_dir else href
                    else:
                        full_href = href

                    try:
                        chapter_xml = archive.read(full_href)
                    except KeyError:
                        try:
                            chapter_xml = archive.read(href)
                        except KeyError:
                            continue

                    chapter_root = ElementTree.fromstring(chapter_xml)
                    body = None
                    for elem in chapter_root.iter():
                        if elem.tag.endswith("body"):
                            body = elem
                            break
                    if body is None:
                        continue

                    text = " ".join(
                        part.strip()
                        for part in body.itertext()
                        if part and part.strip()
                    )
                    if text:
                        text_parts.append(text)

                result = "\n\n".join(text_parts).strip()
                if not result:
                    logger.warning("EPUB extraction returned empty text")
                return result
        except (OSError, ElementTree.ParseError, UnicodeDecodeError) as exc:
            logger.warning(
                f"Failed to decode EPUB attachment {filename}: {exc}"
            )
            return ""

    return (
        data.decode("utf-8", errors="ignore").strip()
        or data.decode("latin-1", errors="ignore").strip()
    )


def _validate_metadata(metadata: dict[str, Any] | None) -> tuple[bool, str]:
    """Validates that required metadata fields are present and
    correctly formatted."""
    if metadata is None:
        return False, "Metadata is required but was not provided."

    missing = REQUIRED_METADATA_FIELDS.difference(metadata.keys())
    if missing:
        return False, f"Missing required metadata fields: {
            ', '.join(
                sorted(missing))}"

    # Validate topics is a list
    topics = metadata.get("topics")
    if not isinstance(topics, (list, tuple)) or len(topics) == 0:
        return False, "Field 'topics' must be a non-empty list."

    # Validate entry_type
    entry_type = metadata.get("entry_type")
    if entry_type not in VALID_ENTRY_TYPES:
        return False, f"Field 'entry_type' must be one of: {
            ', '.join(
                sorted(VALID_ENTRY_TYPES))}"

    # Validate source_type
    source_type = metadata.get("source_type")
    if source_type not in VALID_SOURCE_TYPES:
        return False, f"Field 'source_type' must be one of: {
            ', '.join(
                sorted(VALID_SOURCE_TYPES))}"

    # Validate canon_level if provided
    canon_level = metadata.get("canon_level")
    if canon_level is not None and canon_level not in VALID_CANON_LEVELS:
        return False, f"Field 'canon_level' must be one of: {
            ', '.join(
                sorted(VALID_CANON_LEVELS))}"

    # Validate persona is non-empty string
    persona = metadata.get("persona")
    if not isinstance(persona, str) or not persona.strip():
        return False, "Field 'persona' must be a non-empty string."

    # Validate source is non-empty string
    source = metadata.get("source")
    if not isinstance(source, str) or not source.strip():
        return False, "Field 'source' must be a non-empty string."

    return True, ""


def _normalize_metadata(metadata: dict[str, Any]) -> dict[str, str]:
    """Normalizes metadata values to strings for ChromaDB storage."""
    normalized = {}
    all_fields = REQUIRED_METADATA_FIELDS | OPTIONAL_METADATA_FIELDS
    for key in all_fields:
        value = metadata.get(key)
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            normalized[key] = ", ".join(str(v) for v in value if v is not None)
        else:
            normalized[key] = str(value)
    return normalized


# =============================================================================
# Ingestion Pipeline Utilities
# =============================================================================


def clean_source_text(text: str | None) -> str:
    """
    Cleans raw source text for ingestion.

    Removes excessive whitespace, normalizes line endings, and strips
    common artifacts from copy-pasted source material.
    """
    if not text:
        return ""

    # Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Remove excessive blank lines (more than 2 consecutive)
    lines = text.split("\n")
    cleaned_lines = []
    blank_count = 0
    for line in lines:
        if line.strip() == "":
            blank_count += 1
            if blank_count <= 2:
                cleaned_lines.append("")
        else:
            blank_count = 0
            cleaned_lines.append(line.rstrip())

    # Join and strip trailing/leading whitespace
    result = "\n".join(cleaned_lines).strip()

    # Ensure no more than 2 consecutive newlines anywhere (defensive)
    while "\n\n\n" in result:
        result = result.replace("\n\n\n", "\n\n")

    return result


def identify_speakers(
    text: str, speaker_patterns: list[str] | None = None
) -> list[dict[str, str]]:
    """
    Identifies speaker attributions in dialogue text.

    Args:
        text: The dialogue text to analyze.
        speaker_patterns: Optional list of speaker name patterns to recognize.

    Returns:
        List of dicts with 'speaker' and 'dialogue' keys.
    """
    if speaker_patterns is None:
        speaker_patterns = [
            r"^([A-Z][a-z]+):\s*(.+)$",  # "Name: dialogue"
            r"^([A-Z][a-z]+\s+[A-Z][a-z]+):\s*(.+)$",  # "First Last: dialogue"
        ]

    import re

    results = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        matched = False
        for pattern in speaker_patterns:
            match = re.match(pattern, line)
            if match:
                results.append(
                    {
                        "speaker": match.group(1).strip(),
                        "dialogue": match.group(2).strip(),
                    }
                )
                matched = True
                break
        if not matched:
            # No speaker identified, treat as narration
            results.append({"speaker": "Narrator", "dialogue": line})
    return results


# noinspection GrazieInspection
def chunk_semantic_units(
    text: str,
    max_chunk_size: int = 1500,
    min_chunk_size: int = 100,
    speaker_data: list[dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """
    Splits text into atomic semantic units for embedding.

    Each chunk represents one complete semantic idea:
    - One exchange/dialogue
    - One conversation segment
    - One event description
    - One monologue
    - One narrated description

    Args:
        text: The source text to chunk.
        max_chunk_size: Maximum characters per chunk.
        min_chunk_size: Minimum characters per chunk
        (smaller chunks are merged).
        speaker_data: Optional pre-identified speaker dialogue data.

    Returns:
        List of chunks with metadata: document, speaker (if dialogue),
        estimated_tokens.
    """
    if speaker_data:
        # Use pre-identified speaker data for dialogue-based chunking
        chunks = []
        current_chunk = ""
        current_speaker = None

        # noinspection GrazieInspection
        for entry in speaker_data:
            speaker = entry["speaker"]
            dialogue = entry["dialogue"]

            # If speaker changes and we have content, finalize current chunk
            if (
                current_speaker is not None
                and speaker != current_speaker
                and current_chunk
            ):
                chunks.append(
                    {
                        "document": current_chunk.strip(),
                        "speaker": current_speaker,
                        "estimated_tokens": len(current_chunk) // 4,
                    }
                )
                current_chunk = ""

            current_speaker = speaker
            current_chunk += f"{speaker}: {dialogue}\n"

            # Check if chunk is getting too large
            if len(current_chunk) >= max_chunk_size:
                chunks.append(
                    {
                        "document": current_chunk.strip(),
                        "speaker": current_speaker,
                        "estimated_tokens": len(current_chunk) // 4,
                    }
                )
                current_chunk = ""
                current_speaker = None

        # Add final chunk
        if current_chunk.strip():
            chunks.append(
                {
                    "document": current_chunk.strip(),
                    "speaker": current_speaker,
                    "estimated_tokens": len(current_chunk) // 4,
                }
            )

        return chunks

    # Fallback: simple paragraph-based chunking for narration
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks = []
    current_chunk = ""

    for para in paragraphs:
        if (
            len(current_chunk) + len(para) + 2 > max_chunk_size
            and current_chunk
        ):
            if len(current_chunk) >= min_chunk_size:
                chunks.append(
                    {
                        "document": current_chunk,
                        "speaker": None,
                        "estimated_tokens": len(current_chunk) // 4,
                    }
                )
            else:
                # Merge small chunk with next
                pass
            current_chunk = para
        else:
            if current_chunk:
                current_chunk += "\n\n" + para
            else:
                current_chunk = para

    if current_chunk.strip():
        chunks.append(
            {
                "document": current_chunk.strip(),
                "speaker": None,
                "estimated_tokens": len(current_chunk) // 4,
            }
        )

    return chunks


def assign_metadata(
    chunks: list[dict[str, Any]],
    base_metadata: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Assigns metadata to each chunk, preserving chunk-specific fields.

    Args:
        chunks: List of chunk dicts from chunk_semantic_units.
        base_metadata: Base metadata to apply to all chunks
        (persona, source, etc.)

    Returns:
        List of dicts with document and complete metadata
        ready for embedding.
    """
    results = []
    for chunk in chunks:
        metadata = base_metadata.copy()
        # Add schema version and embedding model if not present
        if "schema_version" not in metadata:
            metadata["schema_version"] = "1"
        if "embedding_model" not in metadata:
            metadata["embedding_model"] = os.getenv(
                "EMBEDDING_MODEL", "text-embedding-3-large"
            )
        if chunk.get("speaker") and chunk["speaker"] != "Narrator":
            metadata["speaker"] = chunk["speaker"]
            metadata["entry_type"] = "dialogue"
        else:
            metadata["entry_type"] = metadata.get("entry_type", "narration")
        results.append(
            {
                "document": chunk["document"],
                "metadata": metadata,
            }
        )
    return results


def ingest_source(
    raw_text: str,
    base_metadata: dict[str, Any],
    max_chunk_size: int = 1500,
    min_chunk_size: int = 100,
) -> list[dict[str, Any]]:
    """
    Full ingestion pipeline: clean -> identify speakers ->
    chunk -> assign metadata.

    Args:
        raw_text: Raw source text.
        base_metadata: Required metadata (persona, source,
        source_type, entry_type, topics) plus optional fields
        (episode, chapter, scene, timestamp, canon_level, tags).
        max_chunk_size: Maximum characters per chunk.
        min_chunk_size: Minimum characters per chunk.

    Returns:
        List of ingestion-ready entries with document and metadata.
    """
    # Stage 1: Cleaning
    cleaned = clean_source_text(raw_text)

    # Stage 2: Speaker Identification
    speaker_data = identify_speakers(cleaned)

    # Stage 3: Semantic Chunking
    chunks = chunk_semantic_units(
        cleaned,
        max_chunk_size=max_chunk_size,
        min_chunk_size=min_chunk_size,
        speaker_data=speaker_data,
    )

    # Stage 4: Metadata Assignment
    return assign_metadata(chunks, base_metadata)


def add_knowledge(
    document: str,
    *,
    source: str = "manual",
    title: str | None = None,
    collection_name: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    """
    Adds a knowledge entry to the ChromaDB collection.

    Requires metadata with the following fields:
    - persona: Persona identifier (required)
    - source: Original source (required)
    - source_type: Anime, Novel, Manga, Game, Guidebook,
      Interview, Website, Other (required)
    - entry_type: Dialogue, Narration, Event, Relationship,
      Description (required)
    - topics: List of semantic topics (required, non-empty)

    Optional metadata fields:
    - episode: Episode number
    - chapter: Chapter number
    - scene: Scene description
    - speaker: Speaking character
    - timestamp: Source timestamp
    - canon_level: Canon priority
    - tags: Additional indexing tags
    - schema_version: Schema version (auto-populated, default: 1)
    - embedding_model: Embedding model used (auto-populated from config)
    """
    collection = get_collection(collection_name)
    if collection is None:
        return ""

    if not document or not document.strip():
        logger.warning("Attempted to add empty document to knowledge base.")
        return ""

    # Validate metadata
    valid, error_msg = _validate_metadata(metadata)
    if not valid:
        logger.error(f"Invalid metadata for knowledge entry: {error_msg}")
        return ""

    doc_id = f"kb_{uuid.uuid4().hex}"

    # Merge provided metadata with defaults
    entry_metadata = {"source": source or "manual"}
    if title:
        entry_metadata["title"] = str(title).strip()
    if metadata:
        entry_metadata.update(_normalize_metadata(metadata))

    # Add schema version and embedding model if not provided
    if "schema_version" not in entry_metadata:
        entry_metadata["schema_version"] = "1"
    if "embedding_model" not in entry_metadata:
        entry_metadata["embedding_model"] = os.getenv(
            "EMBEDDING_MODEL", "text-embedding-3-large"
        )

    try:
        collection.add(
            documents=[document],
            metadatas=[entry_metadata],
            ids=[doc_id],
        )
        return doc_id
    except Exception:  # chromadb doesn't expose a public base exception
        logger.exception("Chroma add error")
        return ""


def list_knowledge(
    limit: int = 20, collection_name: str | None = None
) -> list[dict[str, Any]]:
    collection = get_collection(collection_name)
    if collection is None:
        return []

    try:
        result = collection.get(
            limit=limit, include=["documents", "metadatas"]
        )
    except TypeError:
        try:
            result = collection.get(include=["documents", "metadatas"])
        except Exception:  # chromadb doesn't expose a public base exception
            logger.exception("Chroma list error")
            return []
    except Exception:  # chromadb doesn't expose a public base exception
        logger.exception("Chroma list error")
        return []

    ids = (result.get("ids", []) or [])[:limit]
    docs = (result.get("documents", []) or [])[:limit]
    metadatas = (result.get("metadatas", []) or [])[:limit]

    entries: list[dict[str, Any]] = []
    for index, doc_id in enumerate(ids):
        entries.append(
            {
                "id": doc_id,
                "document": docs[index] if index < len(docs) else "",
                "metadata": metadatas[index] if index < len(metadatas) else {},
            }
        )
    return entries


def delete_knowledge(doc_id: str, collection_name: str | None = None) -> bool:
    collection = get_collection(collection_name)
    if collection is None:
        return False

    try:
        collection.delete(ids=[doc_id])
        return True
    except (ValueError, RuntimeError, OSError) as exc:
        logger.error(f"Chroma delete error: {exc}")
        return False


def query_knowledge(
    query: str,
    limit: int = 3,
    collection_name: str | None = None,
    persona: str | None = None,
) -> list[dict[str, Any]]:
    """
    Queries the knowledge base with optional persona filtering.

    Args:
        query: The search query text.
        limit: Maximum number of results to return.
        collection_name: Optional collection name override.
        persona: Optional persona identifier to filter results by.

    Returns:
        List of knowledge entries with document, metadata,
        and distance.
    """
    collection = get_collection(collection_name)
    if collection is None:
        return []

    try:
        where_clause = {"persona": persona} if persona else None
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
                        "metadata": metadatas[i] if i < len(metadatas) else {},
                        "distance": (
                            distances[i] if i < len(distances) else None
                        ),
                    }
                )
        return entries
    except (ValueError, RuntimeError, OSError) as exc:
        logger.error(f"Chroma query error: {exc}")
        return []


def get_knowledge_by_persona(
    persona: str,
    limit: int = 50,
    collection_name: str | None = None,
) -> list[dict[str, Any]]:
    """
    Retrieves all knowledge entries for a specific persona.

    Args:
        persona: The persona identifier to filter by.
        limit: Maximum number of entries to return.
        collection_name: Optional collection name override.

    Returns:
        List of knowledge entries for the persona.
    """
    collection = get_collection(collection_name)
    if collection is None:
        return []

    try:
        result = collection.get(
            where={"persona": persona},
            limit=limit,
            include=["documents", "metadatas"],
        )

        ids = result.get("ids", []) or []
        docs = result.get("documents", []) or []
        metadatas = result.get("metadatas", []) or []

        entries = []
        for i, doc_id in enumerate(ids):
            entries.append(
                {
                    "id": doc_id,
                    "document": docs[i] if i < len(docs) else "",
                    "metadata": metadatas[i] if i < len(metadatas) else {},
                }
            )
        return entries
    except (ValueError, RuntimeError, OSError) as exc:
        logger.error(f"Chroma get by persona error: {exc}")
        return []
