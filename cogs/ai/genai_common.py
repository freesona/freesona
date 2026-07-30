# cogs/ai/genai_common.py: Shared constants and helpers for AI cogs.

import asyncio
import logging
import os

import discord
from dotenv import load_dotenv

load_dotenv()

BOT_NAME = os.getenv("BOT_NAME", "Bot")
MEMORY_FILE_PATH = os.getenv("MEMORY_FILE_PATH", "./memory.db")

logger = logging.getLogger("FreesonaBot")

# Debounce + autonomy state
_pending_responses: dict[tuple[int, int], asyncio.Task[None]] = {}
_autonomy_cooldown: dict[int, float] = {}
_autonomy_user_cooldown: dict[int, float] = {}

CHAT_RESPONSE_MODES = {"all", "mentions", "smart"}


def should_respond_in_chat_channel(
    message: discord.Message, bot_user: discord.ClientUser | None, mode: str
) -> bool:
    if mode == "all":
        return True

    is_mention = bot_user is not None and bot_user in message.mentions
    is_reply = (
        bot_user is not None
        and message.reference is not None
        and getattr(message.reference.resolved, "author", None) == bot_user
    )

    if mode == "mentions":
        return is_mention or is_reply
    if mode == "smart":
        return is_mention or is_reply or bool(message.attachments)
    return True


def get_reply_target(
    message: discord.Message, bot_user: discord.ClientUser | None
) -> discord.Message:
    """
    Determine which message to reply to.

    If the message mentions the bot AND is a reply to another user's message (not the bot),
    return the referenced message (the original) so the bot replies to that instead of the reply.
    """
    if bot_user is None:
        return message

    # Check if bot is mentioned in this message
    is_mention = bot_user in message.mentions

    # Check if this message is a reply to another message
    if not is_mention or not message.reference or not isinstance(message.reference.resolved, discord.Message):
        return message

    ref = message.reference.resolved

    # If the referenced message author is the bot, reply to the current message (normal flow)
    if ref.author == bot_user:
        return message

    # Otherwise, the user replied to someone else and mentioned the bot
    # Reply to the original message instead
    return ref


def clean_sources_block(sources_text: str, max_length: int = 1024) -> str:
    """
    Convert sources block markdown into a safer list format and clamp length.
    - Strips opaque grounding redirect links from markdown links.
    - Keeps up to 5 entries.
    """
    links = []
    for line in sources_text.splitlines():
        line = line.strip()
        if not line:
            continue

        markdown_link = None
        if line.startswith("-"):
            markdown_link = line[1:].strip()

        if markdown_link and markdown_link.startswith("[") and "](" in markdown_link and markdown_link.endswith(")"):
            text = markdown_link[1: markdown_link.index("](")]
            url = markdown_link[markdown_link.index("](") + 2: -1]
            links.append((text, url))

    if not links:
        fallback = sources_text[:max_length].strip()
        return fallback if fallback else "No source links available."

    cleaned_links = []
    current_length = 0

    for text, url in links[:5]:
        if "grounding-api-redirect" in url:
            entry = f"• {text}"
        else:
            entry = f"• [{text}]({url})"

        if current_length + len(entry) + 1 > max_length:
            break

        cleaned_links.append(entry)
        current_length += len(entry) + 1

    return "\n".join(cleaned_links)