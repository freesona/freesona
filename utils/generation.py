# utils/generation.py: Core AI generation pipeline, response types, and message sender.

import os
import re
import asyncio
import logging
import time
import base64
import io

from PIL import Image
from dataclasses import dataclass, field
from typing import Optional, Union, Dict, Any, List

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

    # Catch 25MB payload limits explicitly
    if "400" in msg and "payload is below" in msg:
        return GenerationError("The attached file exceeds the 25 MB size limit.")
    
    # Use regex to match whole words and prevent false positives from URLs
    if "429" in msg or re.search(r'\b(quota|rate limit)\b', msg):
        return RateLimitError(str(e))
    if "timeout" in msg or "timed out" in msg:
        return TimeoutGenerationError(str(e))
    if "500" in msg or "503" in msg or "internal" in msg:
        return TransientError(str(e))
    
    return GenerationError(str(e))

_ERROR_MESSAGES: dict[type, str] = {
    RateLimitError:         "Maybe pipe down on those requests. Try again in a bit.",
    TimeoutGenerationError: "I lost my train of thought. Try again?",
    TransientError:         "Must have been the wind... Try again?",
    MalformedResponseError: "Say what now?",
    GenerationError:        "Something went wrong. Try again.",
}

def _user_facing_error(e: GenerationError) -> str:
    return _ERROR_MESSAGES.get(type(e), _ERROR_MESSAGES[GenerationError])

async def rate_limit():
    global call_timestamps
    now = time.time()
    call_timestamps = [t for t in call_timestamps if now - t < 60]
    if len(call_timestamps) >= _get_rate_limit():
        wait_time = 60 - (now - call_timestamps[0])
        await asyncio.sleep(wait_time)
    call_timestamps.append(time.time())

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

def compress_image_bytes(image_data: bytes, max_size: int = 25_000_000) -> bytes:
    if len(image_data) <= max_size:
        return image_data
    try:
        with Image.open(io.BytesIO(image_data)) as img:
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            output = io.BytesIO()
            img.save(output, format="JPEG", optimize=True, quality=85)
            return output.getvalue()
    except Exception as e:
        logger.error(f"Image compression failed: {e}")
        return image_data

async def extract_attachments(message: Optional[discord.Message]) -> list[tuple[bytes, str]]:
    if not message or not message.attachments:
        return []
    results = []
    for att in message.attachments:
        mime = att.content_type or ""
        mime_base = mime.split(";")[0].strip()
        try:
            data = await att.read()
            results.append((data, mime_base))
        except Exception as e:
            logger.error(f"Failed to read attachment {att.filename}: {e}")
    return results

def _build_gemini_contents(
    text: str,
    attachments: Optional[list[tuple[bytes, str]]],
    reply: Optional[dict],
    instruction_prefix: str,
    username: str = "",
) -> List[Any]:
    if types is None:
        return []

    parts = []
    if reply:
        parts.append(types.Part.from_text(text="When replying, address the author of the most recent message."))
        parts.append(types.Part.from_text(text=f"[quoted from {reply['author']}]:\n{reply['content']}"))

    user_text = f"{instruction_prefix}\n\n[{username}]: {text}".strip() if username else text.strip()
    if user_text:
        parts.append(types.Part.from_text(text=user_text))

    for att_bytes, att_mime in (attachments or []):
        parts.append(types.Part.from_bytes(data=att_bytes, mime_type=att_mime))

    if not parts:
        parts.append(types.Part.from_text(text="Hello"))

    return [types.Content(role="user", parts=parts)]

def _consume_stream(client_obj, kwargs_dict):
    stream = client_obj.interactions.create(stream=True, **kwargs_dict)
    text_acc = ""
    last_interaction_id = None
    for event in stream:
        event_type = getattr(event, "event_type", None)
        if event_type == "step.delta":
            delta = getattr(event, "delta", None)
            if delta and hasattr(delta, "text"):
                text_acc += str(delta.text)
        elif event_type == "interaction.completed":
            interaction = getattr(event, "interaction", None)
            if interaction and getattr(interaction, "id", None):
                last_interaction_id = str(interaction.id)
    return text_acc, last_interaction_id

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

    text = prompt.get("content", "") if isinstance(prompt, dict) else (prompt or "")
    text = sanitize_prompt(text)
    
    persona = current_persona if apply_persona else ""
    if apply_persona and guild_id and user_id:
        memory_block = await inject_user_memory(guild_id, user_id, username)
        if memory_block:
            persona = f"{current_persona}\n\n{memory_block}"

    if attachments:
        processed_attachments = []
        for att_bytes, att_mime in attachments:
            if att_mime.startswith("image/"):
                att_bytes = compress_image_bytes(att_bytes)
                att_mime = "image/jpeg"
            processed_attachments.append((att_bytes, att_mime))
        attachments = processed_attachments

    try:
        provider_name = get_provider_name()
        current_model = get_provider_model() or get_model_name()

        if provider_name != "gemini":
            output = generate_text(text, system_prompt=persona, provider=provider_name, model=current_model)
            return build_response(output if output else "Something went wrong.")

        if not client:
            raise RuntimeError("Gemini client not initialized.")

        gemini_contents = _build_gemini_contents(text, attachments, None, instruction_prefix, username)

        if hasattr(client, "interactions"):
            kwargs_interaction = {
                "model": current_model,
                "contents": gemini_contents, 
                "generation_config": {"max_output_tokens": 1024},
            }
            if apply_persona and persona:
                kwargs_interaction["system_instruction"] = persona

            full_text, _ = await asyncio.to_thread(_consume_stream, client, kwargs_interaction)
            output_text = full_text
        else:
            config = types.GenerateContentConfig(system_instruction=persona) if (types and persona) else None
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=current_model,
                contents=gemini_contents,
                config=config,
            )
            output_text = response.text if response else None

        return build_response(clean_text(output_text) if output_text else "I couldn't generate a response.")

    except Exception as e:
        logger.error(f"Generation error: {e}")
        raise _classify_error(e) from e

async def safe_generate(*args, **kwargs) -> ConversationResponse:
    try:
        return await generate(*args, **kwargs)
    except GenerationError as e:
        return build_response(_user_facing_error(e))
    except Exception:
        return build_response("Something went wrong. Try again.")