# utils/memory.py: Long-term SQLite facts + per-channel interaction ID store.
# Short-term memory (channel_memory, channel_summary, push_memory, maybe_summarize,
# memory_to_contents) has been removed — conversation history is now managed
# server-side by the Interactions API via previous_interaction_id.

import os
import json
import asyncio
import logging
import aiosqlite
import re
from datetime import datetime, timezone

from dotenv import load_dotenv
from utils.providers import generate_text

load_dotenv()

logger = logging.getLogger("FreesonaBot")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
MEMORY_FILE_PATH = os.getenv("MEMORY_FILE_PATH", "./memory.db")
JSON_PATH        = os.getenv("LEGACY_PATH", "./memory.json")

MAX_FACTS_PER_USER = 20
MIN_IMPORTANCE     = 0.3

FACT_EXTRACT_PROMPT = (
    "You are a memory assistant. Given the following user message, determine if it reveals "
    "any fact worth remembering about the user. "
    "Respond with a JSON object: "
    '{"content": "<one concise fact>", "importance": <float 0.0-1.0>} '
    "or exactly: null"
)

# ---------------------------------------------------------------------------
# Per-user interaction ID store (replaces channel_memory / channel_summary)
# Gemini conversation continuity must be scoped by guild + channel + user,
# otherwise one user's interaction chain can bleed into another user's reply.
# ---------------------------------------------------------------------------

_interaction_store: dict[tuple[int, int, int], str] = {}


def _interaction_key(guild_id: int, channel_id: int, user_id: int) -> tuple[int, int, int]:
    return (guild_id, channel_id, user_id)


def get_interaction_id(guild_id: int, channel_id: int, user_id: int) -> str | None:
    return _interaction_store.get(_interaction_key(guild_id, channel_id, user_id))


def set_interaction_id(guild_id: int, channel_id: int, user_id: int, interaction_id: str) -> None:
    _interaction_store[_interaction_key(guild_id, channel_id, user_id)] = interaction_id


def clear_interaction_id(channel_id: int, guild_id: int | None = None, user_id: int | None = None) -> None:
    """
    Clear the per-user interaction chain for a channel.

    When called with only a channel id, the command clears the full channel scope.
    When called with guild_id + user_id, it clears only that user's continuity.
    """
    if guild_id is None and user_id is None:
        for key in list(_interaction_store):
            if key[1] == channel_id:
                _interaction_store.pop(key, None)
        return

    if guild_id is None or user_id is None:
        raise ValueError("guild_id and user_id must be provided together when clearing a single user chain.")

    _interaction_store.pop(_interaction_key(guild_id, channel_id, user_id), None)


# ---------------------------------------------------------------------------
# Database core
# ---------------------------------------------------------------------------

async def init_db():
    async with aiosqlite.connect(MEMORY_FILE_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS user_facts (
                guild_id   TEXT,
                user_id    TEXT,
                content    TEXT,
                importance REAL,
                timestamp  TEXT,
                message_id TEXT,
                channel_id TEXT,
                PRIMARY KEY (message_id)
            )
        ''')
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_guild ON user_facts (user_id, guild_id)"
        )
        await db.commit()

async def get_user_facts_prompt(guild_id: int, user_id: int, display_name: str) -> str:
    async with aiosqlite.connect(MEMORY_FILE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT content FROM user_facts "
            "WHERE guild_id = ? AND user_id = ? ORDER BY importance DESC",
            (str(guild_id), str(user_id))
        ) as cursor:
            rows = await cursor.fetchall()

            if not rows:
                return (
                    f"\n[Known facts about {display_name or f'Discord user {user_id}'}]\n"
                    "None. You have no record of any past interactions with this user."
                )

            lines = [f"- {row['content']}" for row in rows]
            return f"\n[Known facts about {display_name or f'Discord user {user_id}'}]\n" + "\n".join(lines)


async def inject_user_memory(guild_id: int, user_id: int, display_name: str) -> str:
    return await get_user_facts_prompt(guild_id, user_id, display_name)


# ---------------------------------------------------------------------------
# Fact extraction & storage
# ---------------------------------------------------------------------------

async def extract_and_store_fact(
    message_content,
    display_name,
    guild_id,
    user_id,
    message_id,
    channel_id,
    client,
    model_name,
    provider_name: str | None = None,
):
    if not message_content.strip():
        return

    provider_name = (provider_name or "gemini").strip().lower()
    prompt = f"{FACT_EXTRACT_PROMPT}\n\nUser message: {message_content}"
    try:
        if provider_name == "gemini" and client is not None:
            interaction = await asyncio.to_thread(
                client.interactions.create,
                model=model_name,
                input=prompt,
                store=False,
            )
            raw = (getattr(interaction, "output_text", "") or "").strip()
        else:
            raw = await asyncio.to_thread(
                generate_text,
                message_content,
                system_prompt=FACT_EXTRACT_PROMPT,
                provider=provider_name,
                model=model_name,
                max_output_tokens=256,
            )
            raw = (raw or "").strip()

        if not raw or raw.lower() == "null":
            return

        if "```" in raw:
            raw = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()

        parsed = json.loads(raw)
        content = parsed.get("content", "").strip()
        importance = float(parsed.get("importance", 0.0))

        if not content or importance < MIN_IMPORTANCE:
            return

        async with aiosqlite.connect(MEMORY_FILE_PATH) as db:
            await db.execute(
                "INSERT OR IGNORE INTO user_facts VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    str(guild_id), str(user_id), content, importance,
                    datetime.now(timezone.utc).isoformat(),
                    str(message_id), str(channel_id),
                )
            )
            await db.execute('''
                DELETE FROM user_facts
                WHERE guild_id = ? AND user_id = ? AND message_id NOT IN (
                    SELECT message_id FROM user_facts
                    WHERE guild_id = ? AND user_id = ?
                    ORDER BY importance DESC LIMIT ?
                )
            ''', (str(guild_id), str(user_id), str(guild_id), str(user_id), MAX_FACTS_PER_USER))
            await db.commit()

    except Exception as e:
        logger.warning(f"Fact extraction failed: {e}")

# ---------------------------------------------------------------------------
# Migration (JSON -> SQLite) — unchanged
# ---------------------------------------------------------------------------

async def run_migration():
    if not os.path.exists(JSON_PATH):
        return False, "No JSON file found."

    try:
        async with aiosqlite.connect(MEMORY_FILE_PATH) as db:
            with open(JSON_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)

            count = 0
            for key, user_data in data.items():
                if ":" not in key:
                    continue
                guild_id, user_id = key.split(":")
                for fact in user_data.get("facts", []):
                    m_id = fact.get("message_id", f"migrated_{count}_{user_id}")
                    ts   = fact.get("timestamp", datetime.now(timezone.utc).isoformat())
                    await db.execute(
                        "INSERT OR IGNORE INTO user_facts VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (str(guild_id), str(user_id), fact["content"], fact["importance"], ts, str(m_id), "0")
                    )
                    count += 1
            await db.commit()

        os.rename(JSON_PATH, f"{JSON_PATH}.bak")
        return True, f"Migrated {count} facts successfully."
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return False, str(e)