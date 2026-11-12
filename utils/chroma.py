#!/usr/bin/env python3

# utils/chroma.py: ChromaDB utility functions for managing and

# querying a ChromaDB collection. Implements the Persona-Agnostic

# Knowledge Base (RAG) architecture.

import io
import json
import logging
import os
import uuid
import zipfile
from typing import Any, Protocol, cast
from xml.etree import ElementTree

# Exported symbols for static analysis tools like Pylance. Including

# ``list_knowledge`` ensures that ``from utils.chroma import list_knowledge``

# resolves correctly.

__all__ = [
    "RETRIEVAL_CANDIDATE_MULTIPLIER",
    "VALID_CANON_LEVELS",
    "VALID_ENTRY_TYPES",
    "VALID_SOURCE_TYPES",
    "add_knowledge",
    "delete_knowledge",
    "extract_epub_book_info",
    "extract_text_from_bytes",
    "get_knowledge_by_persona",
    "list_knowledge",
    "query_knowledge",
    "rank_knowledge_for_persona",
]


from dotenv import load_dotenv

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

    def get(
        self, limit: int | None = None, **kwargs: Any
    ) -> dict[str, Any]: ...

    def query(self, **kwargs: Any) -> dict[str, Any]: ...


# Required metadata fields per the Persona Knowledge Base schema

REQUIRED_METADATA_FIELDS = frozenset(
    ("persona", "source", "source_type", "entry_type", "topics")
)

# Optional metadata fields – these are not required for every entry but may be

# provided when available.

OPTIONAL_METADATA_FIELDS = frozenset(
    (
        "episode",
        "chapter",
        "scene",
        "timestamp",
        "canon_level",
        "tags",
        "speaker",
        "title",
        "structured_id",
    )
)


# Validation sets for metadata fields – these mirror the definitions used in
# the Discord cog (`cogs/ai/chroma.py`). They are required by
# `_validate_metadata` to ensure that user‑provided metadata conforms to
# expected values.

VALID_ENTRY_TYPES = {
    "dialogue",
    "narration",
    "event",
    "relationship",
    "description",
}


VALID_SOURCE_TYPES = {
    "anime",
    "novel",
    "manga",
    "game",
    "guidebook",
    "interview",
    "website",
    "other",
}


VALID_CANON_LEVELS = {
    "canon",
    "semi-canon",
    "non-canon",
    "headcanon",
    "alternate",
}


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


def extract_epub_book_info(data: bytes, filename: str = "") -> dict[str, str]:
    """Extract book title and author from EPUB container or filename."""
    info = {"title": "", "author": "", "source": ""}
    if data:
        try:
            with zipfile.ZipFile(io.BytesIO(data), mode="r") as archive:
                container_data = archive.read("META-INF/container.xml")
                container = ElementTree.fromstring(container_data)
                rootfile = next(
                    (
                        elem
                        for elem in container.iter()
                        if elem.tag.endswith("rootfile")
                    ),
                    None,
                )
                if rootfile is not None:
                    opf_path = rootfile.attrib.get("full-path")
                    if opf_path:
                        opf_data = archive.read(opf_path)
                        opf = ElementTree.fromstring(opf_data)
                        for elem in opf.iter():
                            tag = elem.tag.split("}")[-1].lower()
                            text = "".join(elem.itertext()).strip()
                            if not text:
                                continue
                            if tag == "title" and not info["title"]:
                                info["title"] = text
                            elif tag == "creator" and not info["author"]:
                                info["author"] = text
        except (OSError, zipfile.BadZipFile, ElementTree.ParseError):
            pass

    # Fall back to cleaned filename if title was not found in OPF
    if not info["title"] and filename:
        raw_name = filename
        base_name = raw_name.rsplit(".", 1)[0] if "." in raw_name else raw_name
        cleaned = base_name.replace("_", " ").strip()
        info["title"] = cleaned

    info["source"] = info["title"] or "novel"
    return info


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
            # Explicitly open the EPUB archive in read mode to satisfy Pylance
            # and

            # avoid runtime errors on some platforms.

            with zipfile.ZipFile(io.BytesIO(data), mode="r") as archive:
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

                    heading = None
                    for tag_name in ("h1", "h2", "h3"):
                        for elem in chapter_root.iter():
                            if elem.tag.endswith(tag_name):
                                h_text = "".join(elem.itertext()).strip()
                                if (
                                    h_text
                                    and h_text.lower() != "unknown"
                                    and len(h_text) < 100
                                ):
                                    heading = h_text
                                    break
                        if heading:
                            break

                    # Preserve paragraph boundaries: block-level elements
                    # become separate lines so downstream chunking can
                    # split on real paragraph breaks instead of treating
                    # an entire chapter as one unbroken line.

                    block_tags = {
                        "p",
                        "div",
                        "h1",
                        "h2",
                        "h3",
                        "h4",
                        "h5",
                        "h6",
                        "blockquote",
                        "li",
                    }

                    blocks: list[str] = []

                    for child in list(body):

                        child_tag = (
                            child.tag.split("}")[-1].lower()
                            if isinstance(child.tag, str)
                            else ""
                        )

                        if child_tag not in block_tags:

                            continue

                        block_text = " ".join(
                            part.strip()
                            for part in child.itertext()
                            if part and part.strip()
                        )

                        if block_text:

                            blocks.append(block_text)

                    if blocks:

                        text = "\n\n".join(blocks)

                    else:

                        text = " ".join(
                            part.strip()
                            for part in body.itertext()
                            if part and part.strip()
                        )

                    if text:
                        if heading:
                            text_parts.append(f"## {heading}\n\n{text}")
                        else:
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
        return (
            False,
            f"Missing required metadata fields: {', '.join(sorted(missing))}",
        )

    # Validate topics is a list

    topics = metadata.get("topics")

    if not isinstance(topics, (list, tuple)) or len(topics) == 0:
        return False, "Field 'topics' must be a non-empty list."

    # Validate entry_type

    entry_type = metadata.get("entry_type")

    if entry_type not in VALID_ENTRY_TYPES:
        return (
            False,
            f"Field 'entry_type' must be one of: {
                ', '.join(sorted(VALID_ENTRY_TYPES))
            }",
        )

    # Validate source_type

    source_type = metadata.get("source_type")

    if source_type not in VALID_SOURCE_TYPES:
        return (
            False,
            f"Field 'source_type' must be one of: {
                ', '.join(sorted(VALID_SOURCE_TYPES))
            }",
        )

    # Validate canon_level if provided

    canon_level = metadata.get("canon_level")

    if canon_level is not None and canon_level not in VALID_CANON_LEVELS:
        return (
            False,
            f"Field 'canon_level' must be one of: {
                ', '.join(sorted(VALID_CANON_LEVELS))
            }",
        )

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


def _split_long_text(text: str, max_length: int) -> list[str]:
    """Splits oversized text into pieces at sentence boundaries.

    Guarantee: every returned piece is non-empty, stripped, and at most
    ``max_length`` characters long.  Used to keep a single oversized
    narration "line" (e.g., a flattened chapter paragraph) from
    producing a chunk that exceeds the embedding model's practical
    token budget.
    """

    pieces: list[str] = []

    start = 0

    length = len(text)

    sentence_markers = (". ", "! ", "? ", "。”", "！”", "？”", "...")

    while start < length:

        end = min(start + max_length, length)

        if end < length:

            window = text[start:end]

            cut = -1

            cut_width = 1

            for marker in sentence_markers:

                index = window.rfind(marker)

                if index > cut:

                    cut = index

                    # Keep the punctuation; drop any trailing space.

                    cut_width = max(1, len(marker) - 1)

            if cut >= max_length // 2:

                end = start + cut + cut_width

        piece = text[start:end].strip()

        if piece:

            pieces.append(piece)

        start = end

        while start < length and text[start].isspace():

            start += 1

    return pieces


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

        current_chapter: str | None = None

        def emit_chunk(attribution: str | None) -> None:
            """Finalize the in-progress chunk with its speaker/chapter."""

            nonlocal current_chunk

            if not current_chunk.strip():
                return

            chunks.append(
                {
                    "document": current_chunk.strip(),
                    "speaker": attribution,
                    "chapter": current_chapter,
                    "estimated_tokens": len(current_chunk) // 4,
                }
            )

            current_chunk = ""

        # noinspection GrazieInspection

        for entry in speaker_data:
            speaker = entry["speaker"]

            dialogue = entry["dialogue"]

            # Markdown headings (emitted by the EPUB extractor) open a
            # new chapter so subsequent chunks carry chapter metadata.

            if speaker == "Narrator" and dialogue.startswith("#"):
                heading_text = dialogue.lstrip("#").strip()

                if heading_text:
                    emit_chunk(current_speaker)

                    current_speaker = None

                    current_chapter = heading_text

                    current_chunk = heading_text

                    continue

            # If speaker changes and we have content, finalize current chunk

            if (
                current_speaker is not None
                and speaker != current_speaker
                and current_chunk
            ):
                emit_chunk(current_speaker)

            current_speaker = speaker

            # Split oversized entries (e.g., flattened narration lines)
            # so a single entry cannot exceed the chunk budget.

            if len(dialogue) > max_chunk_size:
                # Reserve room for the "Speaker: " prefix and newline in
                # each emitted line so chunks never exceed the budget.

                line_overhead = len(speaker) + 3

                pieces = _split_long_text(
                    dialogue, max(1, max_chunk_size - line_overhead)
                )

            else:
                pieces = [dialogue]

            for piece in pieces:
                line = f"{speaker}: {piece}\n"

                # Check if chunk would get too large before appending

                if (
                    current_chunk
                    and len(current_chunk) + len(line) > max_chunk_size
                ):
                    emit_chunk(current_speaker)

                current_chunk += line

        # Add final chunk

        emit_chunk(current_speaker)

        return chunks

    # Fallback: simple paragraph-based chunking for narration
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    chunks = []
    current_chunk = ""
    current_chapter: str | None = None

    for raw_para in paragraphs:
        # Split oversized paragraphs so a single flattened block cannot
        # exceed the chunk budget.
        if len(raw_para) > max_chunk_size:
            para_parts = _split_long_text(raw_para, max_chunk_size)
        else:
            para_parts = [raw_para]

        for para in para_parts:
            # Detect markdown chapter headings
            if para.startswith("#"):
                heading_text = para.lstrip("#").strip()
                if heading_text:
                    if current_chunk.strip():
                        chunks.append(
                            {
                                "document": current_chunk.strip(),
                                "speaker": None,
                                "chapter": current_chapter,
                                "estimated_tokens": len(current_chunk) // 4,
                            }
                        )
                        current_chunk = ""
                    current_chapter = heading_text
                    current_chunk = para
                    continue

            if (
                len(current_chunk) + len(para) + 2 > max_chunk_size
                and current_chunk
            ):
                if len(current_chunk) >= min_chunk_size:
                    chunks.append(
                        {
                            "document": current_chunk,
                            "speaker": None,
                            "chapter": current_chapter,
                            "estimated_tokens": len(current_chunk) // 4,
                        }
                    )
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
                "chapter": current_chapter,
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

        if chunk.get("chapter"):
            metadata["chapter"] = chunk["chapter"]

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
    """Add a knowledge entry to the ChromaDB collection.



    The caller must provide ``metadata`` containing the required fields:

    ``persona``, ``source``, ``source_type``, ``entry_type`` and ``topics``.

    Optional fields (e.g., ``episode``) are accepted if present.



    Returns the generated document ID on success or an empty string on failure.

    """

    collection = get_collection(collection_name)

    if collection is None:
        return ""

    if not document or not document.strip():
        logger.warning("Attempted to add empty document to knowledge base.")

        return ""

    # Ensure metadata is a dict and contains required keys.

    meta = metadata.copy() if isinstance(metadata, dict) else {}

    # Populate required fields that have defaults or are derived.

    meta.setdefault("source", source)

    if title:
        meta["title"] = title

    valid, reason = _validate_metadata(meta)

    if not valid:
        logger.warning(f"Invalid metadata for knowledge entry: {reason}")

        return ""

    # Normalize metadata values (e.g., list of topics ->
    # comma‑separated string)

    normalized_meta = _normalize_metadata(meta)

    # Generate a unique ID for the document.

    doc_id = str(uuid.uuid4())

    try:
        collection.add(
            ids=[doc_id],
            documents=[document],
            metadatas=[normalized_meta],
        )

    except (ValueError, RuntimeError, OSError) as exc:
        logger.error(f"Chroma add error: {exc}")

        return ""

    return doc_id


class ChromaBackendError(RuntimeError):
    """Raised when Chroma cannot service a search request."""


def delete_knowledge(doc_id: str, collection_name: str | None = None) -> bool:
    """Delete a knowledge entry from the Chroma collection.

    Args:
        doc_id: Identifier of the document to delete.
        collection_name: Optional collection name; defaults to the
        default collection.

    Returns:
        True if deletion succeeded, False otherwise.
    """
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
        raise ChromaBackendError("Chroma backend is unavailable")

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
        raise ChromaBackendError("Chroma search failed") from exc


# How many extra semantic candidates to fetch beyond ``kb_top_k`` before

# persona-first re-ranking, so first-hand (speaker-matched) entries have a

# chance to displace closer-but-second-hand narration.

RETRIEVAL_CANDIDATE_MULTIPLIER = 3


def _entry_speakers(entry: dict[str, Any]) -> set[str]:
    """Collect speaker identities attributed to a knowledge entry.

    Uses the ``speaker`` metadata field first, then falls back to
    scanning ``Name:``-prefixed lines in the document text so chunks
    ingested without speaker metadata still count as first-hand
    knowledge for the characters that speak in them.
    """

    speakers: set[str] = set()

    metadata = entry.get("metadata") or {}

    speaker = str(metadata.get("speaker", "")).strip()

    if speaker:

        speakers.add(speaker.casefold())

    document = entry.get("document", "")

    if isinstance(document, str):

        for line in document.splitlines():

            prefix = line.split(":", 1)[0].strip()

            if (
                prefix
                and len(prefix) <= 40
                and prefix.replace(" ", "").isalpha()
            ):

                speakers.add(prefix.casefold())

    return speakers


def rank_knowledge_for_persona(
    entries: list[dict[str, Any]],
    persona_id: str | None,
) -> list[dict[str, Any]]:
    """Re-rank retrieved entries so first-hand knowledge ranks first.

    Similarity search alone cannot tell whether the persona actually
    witnessed what an entry describes.  Entries where the persona is the
    speaker (her own words and memories) are first-hand knowledge and
    are boosted; narration and other characters' dialogue are second-hand
    or authorial knowledge and keep their original semantic order after
    the boosted tier.  Nothing is dropped or rewritten — only order
    changes.

    Args:

        entries: Entries as returned by ``query_knowledge``.

        persona_id: Persona identifier to match speakers against.

    Returns:

        The re-ranked list (stable within each tier by distance).

    """

    if not entries or not persona_id or not persona_id.strip():

        return entries

    persona_key = persona_id.strip().casefold()

    def sort_key(entry: dict[str, Any]) -> tuple[int, float]:

        distance = entry.get("distance")

        distance_value = float("inf") if distance is None else float(distance)

        tier = 0 if persona_key in _entry_speakers(entry) else 1

        return (tier, distance_value)

    return sorted(entries, key=sort_key)


def list_knowledge(
    collection_name: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Return all knowledge entries in the collection.



    This mirrors :func:`get_knowledge_by_persona` but without any persona

    filtering. It retrieves the full set of documents, their metadata, and the

    associated IDs from the configured Chroma collection.



    Args:

        collection_name: Optional collection name override. If ``None`` the

            default collection name from the environment is used.

        limit: Maximum number of entries to return.



    Returns:

        A list of dictionaries, each containing ``id``, ``document`` and

        ``metadata`` keys. An empty list is returned if the collection
        cannot be

        accessed or an error occurs.

    """

    collection = get_collection(collection_name)

    if collection is None:
        return []

    try:
        result = collection.get(
            limit=limit, include=["documents", "metadatas"]
        )

        ids = result.get("ids", []) or []

        docs = result.get("documents", []) or []

        metadatas = result.get("metadatas", []) or []

        entries: list[dict[str, Any]] = []

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
        logger.error(f"Chroma list_knowledge error: {exc}")

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
            # ChromaDB .get() uses 'limit' in some versions, but the Protocol
            # definition in this file doesn't specify it. For consistency
            # with the collection.get() call on line 782, we use a slice
            # or ensure the Protocol matches.
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
