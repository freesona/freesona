# utils/generation.py: Python module.
import asyncio
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any

import discord
from dotenv import load_dotenv

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

from utils.chroma import query_knowledge
from utils.config import (
    get_kb_top_k,
    get_model_name,
    get_model_temperature,
    get_provider_model,
    get_provider_name,
    load_config,
)
from utils.conversation import (
    add_assistant_message,
    add_user_message,
)
from utils.persona import PERSONA_DATA as GLOBAL_PERSONA_DATA
from utils.prompt_builder import build_system_prompt
from utils.providers import generate_text
from utils.security import sanitize_prompt

load_dotenv()

logger = logging.getLogger("FreesonaBot")

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
BOT_NAME = os.getenv("BOT_NAME", "Bot")

PROVIDER = get_provider_name()

# Knowledge base config
KB_TOP_K = get_kb_top_k()
KB_ENABLED = os.getenv("KB_ENABLED", "true").lower() == "true"

# Global state tracking for rate limiting
call_timestamps: list[float] = []

# Split messaging - loaded from config


def _get_split_min_length() -> int:
    return int(load_config().get("generation_split_min_length", 280))


def _get_split_delay_base() -> float:
    return float(load_config().get("generation_split_delay_base", 1.2))


def _get_split_delay_per_char() -> float:
    return float(load_config().get("generation_split_delay_per_char", 0.012))


def _get_split_delay_max() -> float:
    return float(load_config().get("generation_split_delay_max", 3.5))


# Rate limiter - loaded from config


def _get_rate_limit() -> int:
    return int(load_config().get("generation_rate_limit", 5))


# Note: We no longer use Gemini's Interactions API for conversation continuity.
# Conversation history is now managed by Freesona's ConversationManager (utils/conversation.py)
# which provides provider-agnostic short-term memory for ALL providers.
# The client is kept for other Gemini-specific operations if needed.
client = None
if PROVIDER == "gemini" and genai is not None and GOOGLE_API_KEY:
    client = genai.Client(api_key=GOOGLE_API_KEY)

# ---------------------------------------------------------------------------
# Response types
# ---------------------------------------------------------------------------


@dataclass
class MessageSegment:
    text: str
    delay: float = _get_split_delay_base()
    typing: bool = True
    attachment: str | None = None


@dataclass
class ConversationResponse:
    segments: list[MessageSegment] = field(default_factory=list)
    reactions: list[str] = field(default_factory=list)
    suggested_gif: str | None = None

    @property
    def is_empty(self) -> bool:
        return not self.segments

    def first_text(self) -> str:
        return " ".join(s.text for s in self.segments)


# ---------------------------------------------------------------------------
# Error classes
# ---------------------------------------------------------------------------


class GenerationError(Exception):
    pass


class TransientError(GenerationError):
    pass


class RateLimitError(GenerationError):
    pass


class MalformedResponseError(GenerationError):
    pass


class TimeoutGenerationError(GenerationError):
    pass


def _classify_error(e: Exception) -> GenerationError:
    msg = str(e).lower()
    if "429" in msg or "quota" in msg or "rate" in msg:
        return RateLimitError(str(e))
    if "timeout" in msg or "timed out" in msg:
        return TimeoutGenerationError(str(e))
    if "500" in msg or "503" in msg or "internal" in msg:
        return TransientError(str(e))
    return GenerationError(str(e))


_ERROR_MESSAGES: dict[type, str] = {
    RateLimitError: "Maybe pipe down on those requests. Try again in a bit.",
    TimeoutGenerationError: "I lost my train of thought. Try again?",
    TransientError: "Must have been the wind... Try again?",
    MalformedResponseError: "Say what now?",
    GenerationError: "Something went wrong. Try again.",
}


def _user_facing_error(e: GenerationError) -> str:
    return _ERROR_MESSAGES.get(type(e), _ERROR_MESSAGES[GenerationError])


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------


async def rate_limit():
    global call_timestamps
    now = time.time()
    call_timestamps = [t for t in call_timestamps if now - t < 60]
    if len(call_timestamps) >= _get_rate_limit():
        wait_time = 60 - (now - call_timestamps[0])
        await asyncio.sleep(wait_time)
    call_timestamps.append(time.time())


# ---------------------------------------------------------------------------
# Text splitter + response builder
# ---------------------------------------------------------------------------


def split_into_segments(text: str) -> list[str]:
    if len(text) < _get_split_min_length():
        return [text]

    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    if len(paragraphs) <= 1:
        sentences = re.split(r"(?<=[.!?])\s+", text)
        chunks: list[str] = []
        current = ""
        for s in sentences:
            if len(current) + len(s) > 220 and current:
                chunks.append(current.strip())
                current = s
            else:
                current = (current + " " + s).strip() if current else s
        if current:
            chunks.append(current.strip())
        return chunks if len(chunks) > 1 else [text]

    return paragraphs


def build_response(text: str) -> ConversationResponse:
    segments_text = split_into_segments(text)
    segments = []
    for seg in segments_text:
        delay = min(
            _get_split_delay_base() + len(seg) * _get_split_delay_per_char(),
            _get_split_delay_max(),
        )
        segments.append(MessageSegment(text=seg, delay=delay, typing=True))
    return ConversationResponse(segments=segments)


def _strip_reasoning_tags(text: str) -> str:
    """
    Strip reasoning/thinking tags from AI output.

    Some models (especially reasoning models) output their thought process
    in XML-like tags such as <thought>, <thinking>, <reasoning>, etc.
    These should not be shown to users.
    """
    # Pattern matches: <thought>...</thought>, <thinking>...</thinking>,
    # <reasoning>...</reasoning>, and self-closing variants like <thought/> or <thought id="1"/>
    reasoning_tags = [
        r"<thought>.*?</thought>",
        r"<thinking>.*?</thinking>",
        r"<reasoning>.*?</reasoning>",
        r"<reflection>.*?</reflection>",
        r"<analysis>.*?</analysis>",
        r"<internal_monologue>.*?</internal_monologue>",
        r"<scratchpad>.*?</scratchpad>",
        # Self-closing tags (with optional attributes)
        r"<thought(?:\s[^>]*)?\s*/>",
        r"<thinking(?:\s[^>]*)?\s*/>",
        r"<reasoning(?:\s[^>]*)?\s*/>",
        r"<reflection(?:\s[^>]*)?\s*/>",
        r"<analysis(?:\s[^>]*)?\s*/>",
        r"<internal_monologue(?:\s[^>]*)?\s*/>",
        r"<scratchpad(?:\s[^>]*)?\s*/>",
    ]

    for pattern in reasoning_tags:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE | re.DOTALL)

    # Clean up any extra whitespace left by removed tags
    text = re.sub(r"\n\s*\n\s*\n", "\n\n", text)  # Max 2 consecutive newlines
    text = text.strip()

    return text


def clean_text(text: str, limit: int = 4000) -> str:
    # Strip reasoning tags first
    text = _strip_reasoning_tags(text)

    if len(text) <= limit:
        return text
    cut = text[:limit]
    last_dot = cut.rfind(".")
    if last_dot > 1000:
        return cut[: last_dot + 1]
    return cut


# ---------------------------------------------------------------------------
# Multi-message sender
# ---------------------------------------------------------------------------


async def send_response(
    response: ConversationResponse,
    channel: discord.abc.Messageable,
    *,
    reply_to: discord.Message | None = None,
) -> None:
    if not response.segments:
        return

    segments = [s for s in response.segments if s.text.strip()]
    if not segments:
        return

    for i, segment in enumerate(segments):
        try:
            if segment.typing and segment.delay > 0:
                async with channel.typing():
                    await asyncio.sleep(segment.delay)

            if i == 0 and reply_to is not None:
                await _send_first_segment_with_reply(
                    channel, segment.text, reply_to
                )
            else:
                await channel.send(segment.text)
        except discord.Forbidden:
            channel_id = getattr(channel, "id", "Unknown")
            logger.warning(
                f"Missing permissions to send messages in channel {channel_id}"
            )
            return


async def _send_first_segment_with_reply(
    channel: discord.abc.Messageable,
    text: str,
    reply_to: discord.Message,
) -> None:
    """Send the first segment, trying reply first then falling back to regular send."""
    try:
        await reply_to.reply(text)
    except discord.NotFound:
        # Message was deleted or is inaccessible; fall back to regular send
        logger.debug(
            "Reply target message not found, falling back to channel.send"
        )
        await channel.send(text)


# ---------------------------------------------------------------------------
# Attachment helper
# ---------------------------------------------------------------------------


async def extract_attachments(
    message: discord.Message | None,
) -> list[tuple[bytes, str]]:
    if not message or not message.attachments:
        return []

    results = []
    for att in message.attachments:
        mime = att.content_type or ""
        mime_base = mime.split(";")[0].strip()
        try:
            data = await att.read()
            results.append((data, mime_base))
        except (discord.HTTPException, OSError, asyncio.TimeoutError) as e:
            logger.error(f"Failed to read attachment {att.filename}: {e}")

    return results


# ---------------------------------------------------------------------------
# Knowledge Base Retrieval
# ---------------------------------------------------------------------------


async def retrieve_knowledge_context(
    query: str,
    persona: str,
    top_k: int = KB_TOP_K,
) -> str:
    """
    Retrieves relevant knowledge base entries for the given persona and query.

    Args:
        query: The user's message/query to search for.
        persona: The active persona identifier.
        top_k: Maximum number of entries to retrieve.

    Returns:
        Formatted knowledge context string, or empty string if disabled/no results.
    """
    if not KB_ENABLED:
        return ""

    if not persona or not persona.strip():
        return ""

    try:
        # Run query off-thread to avoid blocking
        entries = await asyncio.to_thread(
            query_knowledge, query, limit=top_k, persona=persona
        )

        if not entries:
            return ""

        # Format entries as context
        lines = ["Relevant Canonical Context"]
        for i, entry in enumerate(entries, 1):
            meta = entry.get("metadata", {})
            document = entry.get("document", "").strip()
            source = meta.get("source", "unknown")
            entry_type = meta.get("entry_type", "unknown")
            scene = meta.get("scene", "")
            speaker = meta.get("speaker", "")
            chapter = meta.get("chapter", "")
            timestamp = meta.get("timestamp", "")
            canon_level = meta.get("canon_level", "")

            context_parts = [f"{i}. {document}"]
            details = []
            if source and source != "unknown":
                details.append(f"Source: {source}")
            if entry_type and entry_type != "unknown":
                details.append(f"Type: {entry_type}")
            if scene:
                details.append(f"Scene: {scene}")
            if speaker:
                details.append(f"Speaker: {speaker}")
            if chapter:
                details.append(f"Chapter: {chapter}")
            if timestamp:
                details.append(f"Timestamp: {timestamp}")
            if canon_level:
                details.append(f"Canon: {canon_level}")

            if details:
                context_parts.append(f"   ({', '.join(details)})")

            lines.extend(context_parts)

        return "\n".join(lines)
    except (RuntimeError, ValueError, OSError) as e:
        logger.warning(f"Knowledge base retrieval failed: {e}")
        return ""


# ---------------------------------------------------------------------------
# Core generation
# ---------------------------------------------------------------------------


async def generate(
    prompt: dict[str, Any] | str | None,
    *,
    current_persona: str,
    channel_id: int | None = None,
    guild_id: int | None = None,
    user_id: int | None = None,
    message_id: int | None = None,
    apply_persona: bool = True,
    instruction_prefix: str = "",
    username: str = "",
    attachments: list[tuple[bytes, str]] | None = None,
    persona_id: str = "",
    guild_world_accessor: Any = None,
) -> ConversationResponse:
    await rate_limit()

    # Extract content and metadata from prompt dict (payload from listener)
    if isinstance(prompt, dict):
        text = prompt.get("content", "")
        mentions = prompt.get("mentions", [])
        reply = prompt.get("reply")
        embeds = prompt.get("embeds", [])
    else:
        text = prompt or ""
        mentions = []
        reply = None
        embeds = []

    text = sanitize_prompt(text)

    # Add user message to conversation history (short-term memory)
    if guild_id and channel_id and user_id:
        await add_user_message(
            guild_id,
            channel_id,
            user_id,
            text,
            message_id,
            username,
            mentions,
            reply,
            embeds,
        )

    # Build system prompt using PromptBuilder (includes conversation history
    # via ConversationHistoryProvider)
    persona = await build_system_prompt(
        current_persona=current_persona,
        persona_id=persona_id,
        guild_id=guild_id,
        channel_id=channel_id,
        user_id=user_id,
        username=username,
        apply_persona=apply_persona,
        instruction_prefix=instruction_prefix,
        kb_enabled=KB_ENABLED,
        kb_top_k=KB_TOP_K,
        user_message=text,
        persona_data=GLOBAL_PERSONA_DATA,
        guild_world_accessor=guild_world_accessor,
    )

    try:
        provider_name = get_provider_name()
        current_model = get_provider_model() or get_model_name()
        current_temperature = get_model_temperature()

        # All providers now use the same stateless generate_text interface.
        # Conversation history is injected via the system prompt (ConversationHistoryProvider),
        # NOT via provider-specific APIs like Gemini's Interactions API.
        # This makes providers completely stateless and interchangeable.

        # Get previous interaction ID for Gemini multi-turn support
        previous_interaction_id = None
        if provider_name == "gemini" and guild_id and channel_id and user_id:
            from utils.conversation import get_last_interaction_id

            previous_interaction_id = await get_last_interaction_id(
                guild_id, channel_id, user_id
            )

        output = generate_text(
            text,
            system_prompt=persona,
            provider=provider_name,
            model=current_model,
            max_output_tokens=2048,
            temperature=current_temperature,
            attachments=attachments,
            instruction_prefix=instruction_prefix,
            username=username,
            user_id=user_id,
            extra_payload=(
                {"previous_interaction_id": previous_interaction_id}
                if previous_interaction_id
                else None
            ),
        )

        # Handle new return type (tuple of output_text, interaction_id)
        if isinstance(output, tuple):
            output_text, interaction_id = output
        else:
            output_text = output or "Something went wrong."
            interaction_id = None

        # Store interaction ID for next turn
        if (
            interaction_id
            and provider_name == "gemini"
            and guild_id
            and channel_id
            and user_id
        ):
            from utils.conversation import set_last_interaction_id

            await set_last_interaction_id(
                guild_id, channel_id, user_id, interaction_id
            )

        # Add assistant response to conversation history
        if guild_id and channel_id and user_id and output_text:
            await add_assistant_message(
                guild_id, channel_id, user_id, output_text
            )

        return build_response(
            clean_text(output_text or "Something went wrong.")
        )

    except Exception as e:
        logger.error(f"Generation error: {e}")
        raise _classify_error(e) from e


async def safe_generate(*args, **kwargs) -> ConversationResponse:
    try:
        return await generate(*args, **kwargs)
    except GenerationError as e:
        return build_response(_user_facing_error(e))
    except (RuntimeError, ValueError, OSError, discord.DiscordException) as e:
        logger.error(f"Unexpected error in safe_generate: {e}")
        return build_response("Something went wrong. Try again.")


__all__ = [
    "ConversationResponse",
    "build_response",
    "extract_attachments",
    "retrieve_knowledge_context",
    "safe_generate",
    "send_response",
]
