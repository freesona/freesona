# utils/character_memory.py: Character Memory subsystem.
#
# Stores persistent shared history between the persona and the user:
# - promises
# - shared experiences
# - recurring jokes
# - unfinished activities
# - relationship progression
# - persistent decisions
#
# Scope: per (guild_id, user_id, persona_id) triple (NOT per channel)
# Mutability: MUTABLE — memories added/updated/deleted via extraction pipeline
# Boundaries: MUST NOT store canonical facts (PKB), user facts (User Memory),
# or conversation history (ConversationManager). MUST consume ConversationManager
# as source for extraction.

from __future__ import annotations

import os
import json
import uuid
import asyncio
import logging
import aiosqlite
from datetime import datetime, timezone
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any

from utils.config import load_config

logger = logging.getLogger("FreesonaBot")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
def _get_character_memory_file_path() -> str:
    """Get the character memory database file path (reads env each call for testability)."""
    return os.getenv("CHARACTER_MEMORY_FILE_PATH", "./character_memory.db")


def _get_max_memories_per_scope() -> int:
    return int(load_config().get("character_memory_max_memories", 50))


def _get_min_importance() -> float:
    return float(load_config().get("character_memory_min_importance", 0.3))


def _get_extraction_interval_seconds() -> int:
    return int(load_config().get("character_memory_extraction_interval", 300))


def _get_extraction_batch_size() -> int:
    return int(load_config().get("character_memory_extraction_batch_size", 10))


# Module-level constants for backward compatibility (evaluated at import time)
CHARACTER_MEMORY_FILE_PATH = _get_character_memory_file_path()
MAX_MEMORIES_PER_SCOPE = _get_max_memories_per_scope()
MIN_IMPORTANCE = _get_min_importance()
EXTRACTION_INTERVAL_SECONDS = _get_extraction_interval_seconds()
EXTRACTION_BATCH_SIZE = _get_extraction_batch_size()


class MemoryType(Enum):
    """Types of character memories."""
    PROMISE = "promise"
    SHARED_EXPERIENCE = "shared_experience"
    RECURRING_JOKE = "recurring_joke"
    UNFINISHED_ACTIVITY = "unfinished_activity"
    RELATIONSHIP_PROGRESSION = "relationship_progression"
    PERSISTENT_DECISION = "persistent_decision"


@dataclass
class CharacterMemory:
    """A single character memory entry."""
    memory_id: str
    guild_id: int
    user_id: int
    persona_id: str
    memory_type: MemoryType
    content: str
    importance: float
    timestamp: str
    source_message_ids: List[int] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "guild_id": self.guild_id,
            "user_id": self.user_id,
            "persona_id": self.persona_id,
            "memory_type": self.memory_type.value,
            "content": self.content,
            "importance": self.importance,
            "timestamp": self.timestamp,
            "source_message_ids": self.source_message_ids,
            "metadata": self.metadata,
        }

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> CharacterMemory:
        return cls(
            memory_id=row["memory_id"],
            guild_id=int(row["guild_id"]),
            user_id=int(row["user_id"]),
            persona_id=row["persona_id"],
            memory_type=MemoryType(row["memory_type"]),
            content=row["content"],
            importance=row["importance"],
            timestamp=row["timestamp"],
            source_message_ids=json.loads(row["source_message_ids"] or "[]"),
            metadata=json.loads(row["metadata"] or "{}"),
        )


# ---------------------------------------------------------------------------
# Database Initialization
# ---------------------------------------------------------------------------

async def init_db():
    """Initialize the character memory database."""
    async with aiosqlite.connect(_get_character_memory_file_path()) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS character_memories (
                memory_id       TEXT PRIMARY KEY,
                guild_id        TEXT NOT NULL,
                user_id         TEXT NOT NULL,
                persona_id      TEXT NOT NULL,
                memory_type     TEXT NOT NULL,
                content         TEXT NOT NULL,
                importance      REAL NOT NULL,
                timestamp       TEXT NOT NULL,
                source_message_ids TEXT DEFAULT '[]',
                metadata        TEXT DEFAULT '{}'
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_char_mem_scope
            ON character_memories (guild_id, user_id, persona_id)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_char_mem_importance
            ON character_memories (guild_id, user_id, persona_id, importance DESC)
        """)
        await db.commit()


# ---------------------------------------------------------------------------
# Storage Operations
# ---------------------------------------------------------------------------

async def store_memory(memory: CharacterMemory) -> None:
    """Store a new character memory."""
    async with aiosqlite.connect(_get_character_memory_file_path()) as db:
        await db.execute("""
            INSERT INTO character_memories (
                memory_id, guild_id, user_id, persona_id,
                memory_type, content, importance, timestamp,
                source_message_ids, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            memory.memory_id,
            str(memory.guild_id),
            str(memory.user_id),
            memory.persona_id,
            memory.memory_type.value,
            memory.content,
            memory.importance,
            memory.timestamp,
            json.dumps(memory.source_message_ids),
            json.dumps(memory.metadata),
        ))
        await db.commit()


async def update_memory(memory: CharacterMemory) -> None:
    """Update an existing character memory."""
    async with aiosqlite.connect(_get_character_memory_file_path()) as db:
        await db.execute("""
            UPDATE character_memories
            SET content = ?, importance = ?, timestamp = ?,
                source_message_ids = ?, metadata = ?
            WHERE memory_id = ?
        """, (
            memory.content,
            memory.importance,
            memory.timestamp,
            json.dumps(memory.source_message_ids),
            json.dumps(memory.metadata),
            memory.memory_id,
        ))
        await db.commit()


async def delete_memory(memory_id: str) -> None:
    """Delete a character memory by ID."""
    async with aiosqlite.connect(_get_character_memory_file_path()) as db:
        await db.execute(
            "DELETE FROM character_memories WHERE memory_id = ?",
            (memory_id,)
        )
        await db.commit()


async def get_memories(
    guild_id: int,
    user_id: int,
    persona_id: str,
    limit: int = MAX_MEMORIES_PER_SCOPE,
    min_importance: float = MIN_IMPORTANCE,
) -> List[CharacterMemory]:
    """Retrieve character memories for a scope, ordered by importance."""
    async with aiosqlite.connect(_get_character_memory_file_path()) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM character_memories
            WHERE guild_id = ? AND user_id = ? AND persona_id = ?
              AND importance >= ?
            ORDER BY importance DESC, timestamp DESC
            LIMIT ?
        """, (str(guild_id), str(user_id), persona_id, min_importance, limit)) as cursor:
            rows = await cursor.fetchall()
            return [CharacterMemory.from_row(row) for row in rows]


async def get_memory_by_id(memory_id: str) -> Optional[CharacterMemory]:
    """Retrieve a single memory by ID."""
    async with aiosqlite.connect(_get_character_memory_file_path()) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM character_memories WHERE memory_id = ?",
            (memory_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return CharacterMemory.from_row(row) if row else None


async def get_memory_count(guild_id: int, user_id: int, persona_id: str) -> int:
    """Get total memory count for a scope."""
    async with aiosqlite.connect(_get_character_memory_file_path()) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT COUNT(*) as count FROM character_memories
            WHERE guild_id = ? AND user_id = ? AND persona_id = ?
        """, (str(guild_id), str(user_id), persona_id)) as cursor:
            row = await cursor.fetchone()
            return row["count"] if row else 0


async def clear_memories(guild_id: int, user_id: int, persona_id: str) -> int:
    """Clear all memories for a scope. Returns count deleted."""
    async with aiosqlite.connect(_get_character_memory_file_path()) as db:
        cursor = await db.execute("""
            DELETE FROM character_memories
            WHERE guild_id = ? AND user_id = ? AND persona_id = ?
        """, (str(guild_id), str(user_id), persona_id))
        await db.commit()
        return cursor.rowcount


# ---------------------------------------------------------------------------
# Context Assembly for PromptBuilder
# ---------------------------------------------------------------------------

async def build_character_memory_context(
    guild_id: int,
    user_id: int,
    persona_id: str,
    username: str = "",
    limit: int = MAX_MEMORIES_PER_SCOPE,
) -> str:
    """
    Build the character memory context block for PromptBuilder.
    
    Returns formatted string matching the expected output format:
    [Character Memory with {username}]
    - [PROMISE] We promised to play chess next week. (importance: 0.9)
    - [SHARED_EXPERIENCE] We decorated the server for Halloween. (importance: 0.7)
    ...
    """
    if not guild_id or not user_id or not persona_id:
        return ""

    memories = await get_memories(guild_id, user_id, persona_id, limit=limit)

    if not memories:
        display_name = username or f"User {user_id}"
        return (
            f"\n[Character Memory with {display_name}]\n"
            "None. No shared history recorded yet."
        )

    display_name = username or f"User {user_id}"
    lines = [f"\n[Character Memory with {display_name}]"]

    for mem in memories:
        importance_str = f"(importance: {mem.importance:.1f})"
        type_label = mem.memory_type.value.upper()
        lines.append(f"- [{type_label}] {mem.content} {importance_str}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Extraction Pipeline
# ---------------------------------------------------------------------------

EXTRACTION_PROMPT = (
    "You are a character memory extraction assistant. "
    "Given a conversation history between a user and a character, identify "
    "memorable shared moments that define their relationship.\n\n"
    "Extract memories of these types ONLY:\n"
    "- PROMISE: Explicit commitments made between them (\"I'll help you with...\")\n"
    "- SHARED_EXPERIENCE: Events they experienced together (\"We fought the boss...\")\n"
    "- RECURRING_JOKE: Running gags or inside jokes (\"Every time you mention cats...\")\n"
    "- UNFINISHED_ACTIVITY: Activities started but not completed (\"We were building a house...\")\n"
    "- RELATIONSHIP_PROGRESSION: Notable shifts in their dynamic (\"You've become more open...\")\n"
    "- PERSISTENT_DECISION: Choices they made together that persist (\"We agreed to use code names...\")\n\n"
    "DO NOT extract:\n"
    "- Facts about the user alone (preferences, background) → User Memory\n"
    "- Facts about the character's canon/lore → PKB/Canon\n"
    "- Raw conversation history → Conversation History\n"
    "- Speculative or assumed information\n\n"
    "Respond with a JSON array of memories, each with:\n"
    '{"type": "PROMISE|SHARED_EXPERIENCE|RECURRING_JOKE|UNFINISHED_ACTIVITY|RELATIONSHIP_PROGRESSION|PERSISTENT_DECISION", '
    '"content": "concise description", "importance": 0.0-1.0, "source_message_ids": [ids]}\n'
    "Return empty array [] if no qualifying memories found.\n"
    "Be selective — only extract genuinely memorable relationship moments."
)


async def extract_memories_from_conversation(
    guild_id: int,
    channel_id: int,
    user_id: int,
    persona_id: str,
    provider_name: str,
    model_name: str,
    client: Any = None,
) -> List[CharacterMemory]:
    """
    Extract character memories from recent conversation history.
    
    This consumes ConversationManager as the source (per ADR-0003 boundaries).
    """
    from utils.conversation import build_conversation_context
    from utils.providers import generate_text

    # Get recent conversation (source for extraction)
    history = await build_conversation_context(
        guild_id=guild_id,
        channel_id=channel_id,
        user_id=user_id,
    )

    if not history or not history.strip():
        return []

    # Run extraction via LLM
    full_prompt = f"{EXTRACTION_PROMPT}\n\nConversation:\n{history}"

    try:
        raw = await asyncio.to_thread(
            generate_text,
            full_prompt,
            system_prompt="You are a JSON-only memory extraction assistant.",
            provider=provider_name,
            model=model_name,
            max_output_tokens=1024,
        )
        raw = (raw or "").strip()

        if not raw or raw.lower() == "null" or raw == "[]":
            return []

        # Parse JSON response
        try:
            extracted = json.loads(raw)
        except json.JSONDecodeError:
            # Try to extract JSON from Markdown code block
            import re
            match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", raw, re.DOTALL)
            if match:
                extracted = json.loads(match.group(1))
            else:
                logger.warning(f"Character memory extraction returned invalid JSON: {raw[:200]}")
                return []

        if not isinstance(extracted, list):
            return []

        # Convert to CharacterMemory objects
        memories = []
        now = datetime.now(timezone.utc).isoformat()
        for item in extracted:
            try:
                mem_type = MemoryType(item["type"].lower())
                importance = float(item["importance"])
                if importance < MIN_IMPORTANCE:
                    continue
                
                memory = CharacterMemory(
                    memory_id=str(uuid.uuid4()),
                    guild_id=guild_id,
                    user_id=user_id,
                    persona_id=persona_id,
                    memory_type=mem_type,
                    content=item["content"].strip(),
                    importance=min(max(importance, 0.0), 1.0),
                    timestamp=now,
                    source_message_ids=item.get("source_message_ids", []),
                )
                memories.append(memory)
            except (KeyError, ValueError, TypeError) as e:
                logger.warning(f"Skipping invalid memory extraction: {e}")
                continue

        return memories

    except Exception as e:
        logger.warning(f"Character memory extraction failed: {e}")
        return []


async def store_extracted_memories(memories: List[CharacterMemory]) -> int:
    """Store a batch of extracted memories, enforcing budget."""
    if not memories:
        return 0

    stored = 0
    for memory in memories:
        try:
            await store_memory(memory)
            stored += 1
        except Exception as e:
            logger.warning(f"Failed to store character memory: {e}")

    # Enforce budget after storing
    if stored > 0 and memories:
        scope = (memories[0].guild_id, memories[0].user_id, memories[0].persona_id)
        await enforce_memory_budget(*scope)

    return stored


async def enforce_memory_budget(
    guild_id: int,
    user_id: int,
    persona_id: str,
    max_memories: int = MAX_MEMORIES_PER_SCOPE,
) -> int:
    """
    Enforce memory budget by removing lowest-importance memories.
    Returns number of memories removed.
    """
    async with aiosqlite.connect(_get_character_memory_file_path()) as db:
        db.row_factory = aiosqlite.Row
        # Get all memories for scope ordered by importance ASC (lowest first)
        async with db.execute("""
            SELECT memory_id FROM character_memories
            WHERE guild_id = ? AND user_id = ? AND persona_id = ?
            ORDER BY importance ASC, timestamp ASC
        """, (str(guild_id), str(user_id), persona_id)) as cursor:
            rows = await cursor.fetchall()
            rows = list(rows)  # Convert Iterable to list for len() and indexing

        if len(rows) <= max_memories:
            return 0

        to_remove = len(rows) - max_memories
        removed = 0
        for row in rows[:to_remove]:
            await db.execute(
                "DELETE FROM character_memories WHERE memory_id = ?",
                (row["memory_id"],)
            )
            removed += 1

        await db.commit()
        return removed


# ---------------------------------------------------------------------------
# Periodic Extraction Task
# ---------------------------------------------------------------------------

_extraction_task: Optional[asyncio.Task] = None


async def run_extraction_cycle(
    guild_id: int,
    channel_id: int,
    user_id: int,
    persona_id: str,
    provider_name: str,
    model_name: str,
    client: Any = None,
) -> int:
    """
    Run a single extraction cycle for a specific conversation scope.
    Returns number of new memories stored.
    """
    memories = await extract_memories_from_conversation(
        guild_id=guild_id,
        channel_id=channel_id,
        user_id=user_id,
        persona_id=persona_id,
        provider_name=provider_name,
        model_name=model_name,
        client=client,
    )
    if memories:
        stored = await store_extracted_memories(memories)
        logger.info(f"Character memory extraction: stored {stored} new memories for "
                    f"guild={guild_id}, user={user_id}, persona={persona_id}")
        return stored
    return 0


async def start_extraction_task(
    interval_seconds: int = EXTRACTION_INTERVAL_SECONDS,
) -> None:
    """
    Start the periodic extraction task.
    
    Note: This is a framework-level task. Actual extraction requires
    knowing which (guild, channel, user, persona) scopes are active.
    The genai cog should call run_extraction_cycle for active conversations.
    """
    global _extraction_task
    if _extraction_task and not _extraction_task.done():
        return


async def stop_extraction_task() -> None:
    """Stop the periodic extraction task."""
    global _extraction_task
    if _extraction_task and not _extraction_task.done():
        _extraction_task.cancel()
        try:
            await _extraction_task
        except asyncio.CancelledError:
            pass


__all__ = [
    "CharacterMemory",
    "MemoryType",
    "init_db",
    "store_memory",
    "update_memory",
    "delete_memory",
    "get_memories",
    "get_memory_by_id",
    "get_memory_count",
    "clear_memories",
    "build_character_memory_context",
    "extract_memories_from_conversation",
    "store_extracted_memories",
    "enforce_memory_budget",
    "run_extraction_cycle",
    "start_extraction_task",
    "stop_extraction_task",
    "CHARACTER_MEMORY_FILE_PATH",
    "MAX_MEMORIES_PER_SCOPE",
    "MIN_IMPORTANCE",
]