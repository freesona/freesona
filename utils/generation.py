# utils/generation.py: Core AI generation pipeline, response types, and message sender.

import os
import re
import asyncio
import logging
import time
import base64

from dataclasses import dataclass, field
from typing import Optional, Union, Dict, Any

import discord
from dotenv import load_dotenv

try:
    from google import genai
    from google.genai import types
except Exception:
    genai = None
    types = None

from utils.memory import (
    get_interaction_id, set_interaction_id,
    inject_user_memory, extract_and_store_fact,
)
from utils.security import sanitize_prompt, unsafe_output
from utils.config import LAST_DEBUG, get_model_name, get_provider_name, get_provider_model, load_config
from utils.providers import build_messages, generate_text
from utils.chroma import query_knowledge

load_dotenv()

logger = logging.getLogger("FreesonaBot")

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
BOT_NAME       = os.getenv("BOT_NAME", "Bot")

PROVIDER = get_provider_name()

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
    attachment: Optional[str] = None

@dataclass
class ConversationResponse:
    segments: list[MessageSegment] = field(default_factory=list)
    reactions: list[str] = field(default_factory=list)
    suggested_gif: Optional[str] = None

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
    RateLimitError:         "I'm a little overwhelmed right now — give me a moment.",
    TimeoutGenerationError: "That took too long. Try again?",
    TransientError:         "Something hiccupped on my end. Try again in a bit.",
    MalformedResponseError: "I got confused by that one. Try rephrasing?",
    GenerationError:        "Something went wrong. Try again.",
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
            _get_split_delay_max()
        )
        segments.append(MessageSegment(text=seg, delay=delay, typing=True))
    return ConversationResponse(segments=segments)


def clean_text(text: str, limit: int = 4000) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit]
    last_dot = cut.rfind('.')
    if last_dot > 1000:
        return cut[:last_dot + 1]
    return cut

# ---------------------------------------------------------------------------
# Multi-message sender
# ---------------------------------------------------------------------------

async def send_response(
    response: ConversationResponse,
    channel: discord.abc.Messageable,
    *,
    reply_to: Optional[discord.Message] = None,
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
                await reply_to.reply(segment.text)
            else:
                await channel.send(segment.text)
        except discord.Forbidden:
            channel_id = getattr(channel, "id", "Unknown")
            logger.warning(f"Missing permissions to send messages in channel {channel_id}")
            return

# ---------------------------------------------------------------------------
# Attachment helper
# ---------------------------------------------------------------------------

SUPPORTED_MIME_TYPES = {
    "image/png", "image/jpeg", "image/webp", "image/gif", "image/heic", "image/heif",
    "application/pdf",
    "text/plain", "text/html", "text/css", "text/markdown", "text/csv",
    "text/xml", "text/rtf",
    "application/rtf",
    "application/x-javascript", "text/javascript",
    "application/x-python", "text/x-python",
    "audio/mpeg", "audio/mp3", "audio/wav", "audio/aiff",
    "audio/aac", "audio/ogg", "audio/flac", "audio/x-flac",
    "video/mp4", "video/mpeg", "video/mov", "video/quicktime",
    "video/avi", "video/x-msvideo", "video/webm",
    "video/wmv", "video/x-ms-wmv", "video/3gpp",
}

async def extract_attachments(message: Optional[discord.Message]) -> list[tuple[bytes, str]]:
    if not message or not message.attachments:
        return []

    results = []
    for att in message.attachments:
        mime = att.content_type or ""
        mime_base = mime.split(";")[0].strip()
        if mime_base not in SUPPORTED_MIME_TYPES:
            continue
        try:
            data = await att.read()
            results.append((data, mime_base))
        except Exception as e:
            logger.error(f"Failed to read attachment {att.filename}: {e}")

    return results

# ---------------------------------------------------------------------------
# Input builders
# ---------------------------------------------------------------------------

def _build_input(
    text: str,
    attachments: Optional[list[tuple[bytes, str]]],
    reply: Optional[dict],
    instruction_prefix: str,
    username: str,
) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []

    if reply:
        clarification = (
            "When replying to a message that quotes or replies to another user's message, "
            "address the author of the most recent message. "
            "Do not attack, blame, or assume intent unless explicitly requested."
        )
        payload.append({"type": "text", "text": clarification})
        payload.append({"type": "text", "text": f"[quoted from {reply['author']}]:\n{reply['content']}"})

    name_tag = f"[{username}]: " if username else ""
    user_text = f"{instruction_prefix}\n\n{name_tag}{text}".strip() if instruction_prefix else f"{name_tag}{text}".strip()

    if user_text:
        payload.append({"type": "text", "text": user_text})

    for att_bytes, att_mime in (attachments or []):
        b64_data = base64.b64encode(att_bytes).decode("utf-8")
        
        if att_mime.startswith("image/"):
            media_type = "image"
        elif att_mime.startswith("audio/"):
            media_type = "audio"
        elif att_mime.startswith("video/"):
            media_type = "video"
        else:
            media_type = "document"

        payload.append({
            "type": media_type,
            "data": b64_data,
            "mime_type": att_mime
        })

    if not payload:
        payload.append({"type": "text", "text": f"[{username}]: Hello" if username else "Hello"})

    return payload


def _build_gemini_contents(
    text: str,
    attachments: Optional[list[tuple[bytes, str]]],
    reply: Optional[dict],
    instruction_prefix: str,
    username: str = "",
) -> list[Any]:
    contents: list[Any] = []

    if reply:
        clarification = (
            "When replying to a message that quotes or replies to another user's message, "
            "address the author of the most recent message. "
            "Do not attack, blame, or assume intent unless explicitly requested."
        )
        contents.append(clarification)
        contents.append(f"[quoted from {reply['author']}]:\n{reply['content']}")

    name_tag = f"[{username}]: " if username else ""
    user_text = f"{instruction_prefix}\n\n{name_tag}{text}".strip() if instruction_prefix else f"{name_tag}{text}".strip()

    if user_text:
        contents.append(user_text)

    for att_bytes, att_mime in (attachments or []):
        if types is not None:
            part = types.Part.from_bytes(data=att_bytes, mime_type=att_mime)
            contents.append(part)

    if not contents:
        contents.append(f"[{username}]: Hello" if username else "Hello")

    return contents


def _consume_stream(client_obj, kwargs_dict):
    stream = client_obj.interactions.create(stream=True, **kwargs_dict)
    text_acc = ""
    last_interaction_id = None

    for event in stream:
        event_type = getattr(event, "event_type", None)

        if event_type == "step.delta":
            delta = getattr(event, "delta", None)
            if delta:
                d_type = getattr(delta, "type", None)
                if d_type == "text":
                    text_acc += str(getattr(delta, "text", ""))
                elif d_type == "thought_summary":
                    content = getattr(delta, "content", {})
                    if isinstance(content, dict) and content.get("text"):
                        text_acc += str(content["text"])

        elif hasattr(event, "text") and event.text:
            text_acc += str(event.text)

        elif event_type == "interaction.completed":
            interaction = getattr(event, "interaction", None)
            if interaction and getattr(interaction, "id", None):
                last_interaction_id = str(interaction.id)

    return text_acc, last_interaction_id

# ---------------------------------------------------------------------------
# Core generation
# ---------------------------------------------------------------------------

async def generate(
    prompt: Optional[Union[Dict[str, Any], str]],
    *,
    current_persona: str,
    channel_id: Optional[int] = None,
    guild_id: Optional[int] = None,
    user_id: Optional[int] = None,
    message_id: Optional[int] = None,
    apply_persona: bool = True,
    instruction_prefix: str = "",
    username: str = "",
    attachments: Optional[list[tuple[bytes, str]]] = None,
) -> ConversationResponse:
    await rate_limit()

    if isinstance(prompt, dict):
        role  = prompt.get("role", "user")
        text  = prompt.get("content", "")
        reply = prompt.get("reply")
    else:
        role  = "user"
        text  = prompt or ""
        reply = None

    text = sanitize_prompt(text)

    persona = current_persona if apply_persona else ""
    if apply_persona and guild_id and user_id:
        memory_block = await inject_user_memory(guild_id, user_id, username)
        if memory_block:
            persona = f"{current_persona}\n\n{memory_block}"

    # Only run vector RAG queries if the prompt isn't a short generic vision question
    # This avoids context bleed from ChromaDB when analyzing images.
    should_query_rag = (
        apply_persona 
        and bool(persona) 
        and (len(text.strip().split()) > 3 or not attachments)
    )

    if should_query_rag:
        knowledge_hits = query_knowledge(text)
        if knowledge_hits:
            knowledge_block = "\n".join(f"- {item}" for item in knowledge_hits)
            persona = f"{persona}\n\n[Relevant knowledge]\n{knowledge_block}"

    input_payload = _build_input(text, attachments, reply, instruction_prefix, username)

    if channel_id is not None:
        LAST_DEBUG[channel_id] = text

    prev_id = (
        get_interaction_id(guild_id, channel_id, user_id)
        if guild_id is not None and channel_id is not None and user_id is not None
        else None
    )

    try:
        provider_name = get_provider_name()
        current_model = get_provider_model() or get_model_name()

        if provider_name != "gemini":
            formatted_user_prompt = f"[{username}]: {text}" if username else text
            output = generate_text(
                formatted_user_prompt,
                system_prompt=persona or "You are a helpful assistant.",
                provider=provider_name,
                model=current_model,
                max_output_tokens=1024,
                attachments=attachments,
            )
            if not output:
                raise MalformedResponseError("Empty response from model.")

            output = clean_text(output)
            if unsafe_output(output):
                logger.warning("Output blocked by safety filter.")
                return build_response("I can't respond to that.")

            if guild_id and user_id and message_id and channel_id and text.strip() and role == "user":
                asyncio.create_task(extract_and_store_fact(
                    message_content=text,
                    display_name=username,
                    guild_id=guild_id,
                    user_id=user_id,
                    message_id=message_id,
                    channel_id=channel_id,
                    client=client,
                    model_name=current_model,
                    provider_name=provider_name,
                ))

            return build_response(output)

        if not client:
            raise RuntimeError("Gemini client not initialized.")

        if hasattr(client, "interactions"):
            kwargs_interaction: dict[str, Any] = {
                "model": current_model,
                "input": input_payload,
                "generation_config": {"max_output_tokens": 1024},
            }
            if apply_persona and persona:
                kwargs_interaction["system_instruction"] = persona
            if prev_id:
                kwargs_interaction["previous_interaction_id"] = prev_id

            full_text, interaction_id = await asyncio.to_thread(
                _consume_stream, client, kwargs_interaction
            )
            if not full_text:
                raise MalformedResponseError("Empty response from model stream.")
            output_text = full_text
        else:
            gemini_contents = _build_gemini_contents(text, attachments, reply, instruction_prefix, username)

            system_instr = persona if (apply_persona and persona) else None

            config_dict: dict[str, Any] = {
                "max_output_tokens": 1024,
            }
            if system_instr:
                config_dict["system_instruction"] = system_instr

            if types is not None and hasattr(types, "GenerateContentConfig"):
                config_arg: Any = types.GenerateContentConfig(**config_dict)
            else:
                config_arg = config_dict

            response = await asyncio.to_thread(
                client.models.generate_content,
                model=current_model,
                contents=gemini_contents,
                config=config_arg,
            )
            output_text = getattr(response, "text", None)
            interaction_id = None

        if not output_text:
            raise MalformedResponseError("Empty response from model.")

        output = clean_text(output_text)

        if unsafe_output(output):
            logger.warning("Output blocked by safety filter.")
            return build_response("I can't respond to that.")

        if guild_id is not None and channel_id is not None and user_id is not None and role in ("user", "webhook"):
            if interaction_id:
                set_interaction_id(guild_id, channel_id, user_id, str(interaction_id))

        if guild_id and user_id and message_id and channel_id and text.strip() and role == "user":
            asyncio.create_task(extract_and_store_fact(
                message_content=text,
                display_name=username,
                guild_id=guild_id,
                user_id=user_id,
                message_id=message_id,
                channel_id=channel_id,
                client=client,
                model_name=current_model,
                provider_name=provider_name,
            ))

        return build_response(output)

    except GenerationError:
        raise
    except Exception as e:
        classified = _classify_error(e)
        logger.error(f"Generation error [{type(classified).__name__}]: {e}")
        raise classified from e

async def safe_generate(
    prompt: Optional[Union[Dict[str, Any], str]],
    *,
    current_persona: str,
    attachments: Optional[list[tuple[bytes, str]]] = None,
    guild_id: Optional[int] = None,
    user_id: Optional[int] = None,
    message_id: Optional[int] = None,
    **kwargs,
) -> ConversationResponse:
    try:
        return await generate(
            prompt,
            current_persona=current_persona,
            attachments=attachments,
            guild_id=guild_id,
            user_id=user_id,
            message_id=message_id,
            **kwargs,
        )
    except GenerationError as e:
        msg = _user_facing_error(e)
        logger.warning(f"safe_generate swallowed error: {type(e).__name__}")
        return build_response(msg)
    except Exception as e:
        logger.error(f"safe_generate unexpected error: {e}")
        return build_response("Something went wrong. Try again.")

__all__ = [
    "ConversationResponse",
    "build_response",
    "extract_attachments",
    "safe_generate",
    "send_response",
]