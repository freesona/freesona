"""Structured Knowledge Base records and deterministic ingestion services."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import asdict, dataclass
from typing import Any

import aiosqlite

from utils.chroma import add_knowledge

logger = logging.getLogger("FreesonaBot")

VALID_ENTRY_TYPES = frozenset(
    {"dialogue", "narration", "event", "relationship", "description"}
)
VALID_SOURCE_TYPES = frozenset(
    {"anime", "novel", "manga", "game", "guidebook", "interview", "website", "other"}
)
VALID_CANON_LEVELS = frozenset(
    {"canon", "semi-canon", "non-canon", "headcanon", "alternate"}
)
REQUIRED_FIELDS = frozenset(
    {"persona", "source", "source_type", "entry_type", "topics", "content"}
)
ENTRY_FIELDS = frozenset(
    {
        "persona",
        "source",
        "source_type",
        "entry_type",
        "topics",
        "content",
        "canon_level",
        "revision",
    }
)
@dataclass(frozen=True)
class KnowledgeEntry:
    """Validated, normalized Knowledge Base record."""
    id: str
    persona: str
    source: str
    source_type: str
    entry_type: str
    topics: tuple[str, ...]
    content: str
    canon_level: str = "canon"
    revision: int = 1
    metadata: dict[str, Any] | None = None
def canonicalize_entry(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize whitespace, case-sensitive identifiers, and ordered metadata."""
    normalized = {key: value for key, value in data.items() if key != "id"}
    for field in ("persona", "source", "content"):
        normalized[field] = " ".join(str(normalized.get(field, "")).split())
    for field in ("source_type", "entry_type"):
        normalized[field] = str(normalized.get(field, "")).strip().lower()
    normalized["canon_level"] = (
        str(normalized.get("canon_level", "canon")).strip().lower()
    )
    topics = normalized.get("topics", ())
    if isinstance(topics, str):
        topics = topics.split(",")
    normalized["topics"] = tuple(
        sorted({str(topic).strip().lower() for topic in topics if str(topic).strip()})
    )
    normalized["revision"] = int(normalized.get("revision", 1))
    return normalized
def validate_entry(data: dict[str, Any]) -> dict[str, Any]:
    """Validate and canonicalize an entry, raising ``ValueError`` on invalid input."""
    normalized = canonicalize_entry(data)
    missing = REQUIRED_FIELDS - normalized.keys()
    if missing or any(
        not normalized.get(field) for field in (REQUIRED_FIELDS - missing)
    ):
        raise ValueError(f"Missing required Knowledge Base fields: {sorted(missing)}")
    if normalized["source_type"] not in VALID_SOURCE_TYPES:
        raise ValueError("Unsupported source_type")
    if normalized["entry_type"] not in VALID_ENTRY_TYPES:
        raise ValueError("Unsupported entry_type")
    if normalized["canon_level"] not in VALID_CANON_LEVELS:
        raise ValueError("Unsupported canon_level")
    if normalized["revision"] < 1:
        raise ValueError("revision must be positive")
    metadata = {
        key: value for key, value in normalized.items() if key not in ENTRY_FIELDS
    }
    if not all(
        isinstance(value, (str, int, float, bool, list, tuple))
        for value in metadata.values()
    ):
        raise ValueError("metadata values must be strings, numbers, booleans, or lists")
    return normalized
def stable_entry_id(data: dict[str, Any]) -> str:
    """Return a stable identifier derived from canonical entry identity/content."""
    normalized = validate_entry(data)
    identity = json.dumps(
        normalized, sort_keys=True, default=list, separators=(",", ":")
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()
class KnowledgeBaseService:
    """Persist structured records and optionally synchronize them to Chroma."""
    def __init__(self, database_path: str, *, indexer=add_knowledge) -> None:
        """Create a service backed by ``database_path`` and an injectable indexer."""
        self.database_path = database_path
        self.indexer = indexer
    async def initialize(self) -> None:
        """Create the structured-record table."""
        async with aiosqlite.connect(self.database_path) as db:
            await db.execute(
                """CREATE TABLE IF NOT EXISTS knowledge_entries (
                    id TEXT PRIMARY KEY, persona TEXT NOT NULL, revision INTEGER NOT NULL,
                    payload TEXT NOT NULL, indexed_id TEXT, created_at REAL NOT NULL DEFAULT (unixepoch()),
                    UNIQUE(persona, id, revision)
                )"""
            )
            await db.commit()
    async def ingest(self, data: dict[str, Any]) -> KnowledgeEntry:
        """Validate, persist, and index one deterministic record."""
        normalized = validate_entry(data)
        entry_id = stable_entry_id(normalized)
        payload = json.dumps(
            normalized, sort_keys=True, default=list, separators=(",", ":")
        )
        entry_values = {key: normalized[key] for key in ENTRY_FIELDS}
        metadata = {
            key: value for key, value in normalized.items() if key not in ENTRY_FIELDS
        }
        entry = KnowledgeEntry(id=entry_id, metadata=metadata or None, **entry_values)
        async with aiosqlite.connect(self.database_path) as db:
            cursor = await db.execute(
                "INSERT OR IGNORE INTO knowledge_entries (id, persona, revision, payload) VALUES (?, ?, ?, ?)",
                (entry_id, entry.persona, entry.revision, payload),
            )
            await db.commit()
            inserted = cursor.rowcount == 1
        if not inserted:
            return entry
        document = f"[{entry.entry_type}] {entry.content}"
        metadata = {
            key: value
            for key, value in asdict(entry).items()
            if key not in {"id", "content", "metadata"}
        }
        metadata["topics"] = list(entry.topics)
        metadata.update(entry.metadata or {})
        metadata["structured_id"] = entry_id
        try:
            indexed_id = await asyncio.to_thread(
                self.indexer, document, source=entry.source, metadata=metadata
            )
        except (OSError, RuntimeError, ValueError):
            indexed_id = ""
        if indexed_id:
            async with aiosqlite.connect(self.database_path) as db:
                await db.execute(
                    "UPDATE knowledge_entries SET indexed_id = ? WHERE id = ?",
                    (indexed_id, entry_id),
                )
                await db.commit()
        return entry

    async def retry_pending_indexing(self) -> int:
        """Retry Chroma indexing for records persisted without an index."""
        async with aiosqlite.connect(self.database_path) as db:
            cursor = await db.execute(
                "SELECT id, payload FROM knowledge_entries WHERE indexed_id IS NULL "
                "ORDER BY created_at DESC, rowid DESC"
            )
            rows = await cursor.fetchall()
        indexed = 0
        for entry_id, payload in rows:
            normalized = validate_entry(json.loads(payload))
            entry_values = {key: normalized[key] for key in ENTRY_FIELDS}
            entry = KnowledgeEntry(
                id=entry_id,
                metadata={
                    key: value
                    for key, value in normalized.items()
                    if key not in ENTRY_FIELDS
                }
                or None,
                **entry_values,
            )
            metadata = {
                key: value
                for key, value in asdict(entry).items()
                if key not in {"id", "content", "metadata"}
            }
            metadata["topics"] = list(entry.topics)
            metadata.update(entry.metadata or {})
            metadata["structured_id"] = entry_id
            try:
                indexed_id = await asyncio.to_thread(
                    self.indexer,
                    f"[{entry.entry_type}] {entry.content}",
                    source=entry.source,
                    metadata=metadata,
                )
            except (OSError, RuntimeError, ValueError):
                indexed_id = ""
            if indexed_id:
                async with aiosqlite.connect(self.database_path) as db:
                    await db.execute(
                        "UPDATE knowledge_entries SET indexed_id = ? WHERE id = ?",
                        (indexed_id, entry_id),
                    )
                    await db.commit()
                indexed += 1
        return indexed

    async def indexed_id(self, entry_id: str) -> str | None:
        """Return the durable Chroma ID for a structured record, if indexed."""
        async with aiosqlite.connect(self.database_path) as db:
            cursor = await db.execute(
                "SELECT indexed_id FROM knowledge_entries WHERE id = ?", (entry_id,)
            )
            row = await cursor.fetchone()
        return row[0] if row else None
    async def list_entries(self, persona: str | None = None) -> list[KnowledgeEntry]:
        """Return persisted entries, optionally limited to one persona."""
        async with aiosqlite.connect(self.database_path) as db:
            query = "SELECT payload FROM knowledge_entries ORDER BY created_at DESC, rowid DESC"
            args: tuple[str, ...] = ()
            if persona:
                query = "SELECT payload FROM knowledge_entries WHERE persona = ? ORDER BY created_at DESC, rowid DESC"
                args = (persona,)
            cursor = await db.execute(query, args)
            rows = await cursor.fetchall()
        entries = []
        for row in rows:
            normalized = validate_entry(json.loads(row[0]))
            entry_values = {key: normalized[key] for key in ENTRY_FIELDS}
            metadata = {
                key: value
                for key, value in normalized.items()
                if key not in ENTRY_FIELDS
            }
            entries.append(
                KnowledgeEntry(
                    id=stable_entry_id(normalized),
                    metadata=metadata or None,
                    **entry_values,
                )
            )
        return entries
    async def delete_entry(self, entry_id: str) -> bool:
        """Delete a structured record and its linked Chroma index entry."""
        async with aiosqlite.connect(self.database_path) as db:
            cursor = await db.execute(
                "SELECT indexed_id FROM knowledge_entries WHERE id = ?", (entry_id,)
            )
            row = await cursor.fetchone()
            if row is None:
                return False
        indexed_id = row[0]
        async with aiosqlite.connect(self.database_path) as db:
            await db.execute("DELETE FROM knowledge_entries WHERE id = ?", (entry_id,))
            await db.commit()
        if indexed_id:
            try:
                from utils.chroma import delete_knowledge

                deleted = await asyncio.to_thread(delete_knowledge, indexed_id)
            except Exception:
                logger.exception("Failed to delete Chroma index entry %s", indexed_id)
            else:
                if not deleted:
                    logger.error("Failed to delete Chroma index entry %s", indexed_id)
        return True
