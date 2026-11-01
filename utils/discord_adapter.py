#!/usr/bin/env python3
# utils/discord_adapter.py: Discord-specific helpers for sending responses
# and extracting attachments. Keeps Discord types out of the generation layer.


import asyncio
import logging

import discord

from utils.generation import ConversationResponse, MessageSegment

logger = logging.getLogger("FreesonaBot")


async def send_response(
    response: ConversationResponse,
    channel: discord.abc.Messageable,
    *,
    reply_to: discord.Message | None = None,
) -> None:
    """Send a formatted response to a Discord channel.

    Args:
        response: ConversationResponse containing message segments.
        channel: Discord channel or messageable target.
        reply_to: Optional message to reply to.
    """

    if not response.segments:
        return

    segments = [s for s in response.segments if s.text.strip()]

    if not segments:
        # Ensure we always have at least one segment to send

        segments = [MessageSegment(text=".", delay=0, typing=False)]

    for i, segment in enumerate(segments):
        if segment.typing and segment.delay > 0:
            async with channel.typing():
                await asyncio.sleep(segment.delay)

        try:
            if i == 0 and reply_to is not None:
                await _send_first_segment_with_reply(
                    channel, segment.text, reply_to
                )

            else:
                await channel.send(segment.text)

        except discord.Forbidden:
            # Stop sending when Forbidden error occurs (e.g., lack of
            # permissions).

            return


async def _send_first_segment_with_reply(
    channel: discord.abc.Messageable,
    text: str,
    reply_to: discord.Message,
) -> None:
    """Send the first segment, trying reply first then

    falling back to regular send."""

    try:
        await reply_to.reply(text)

    except discord.NotFound:
        # Message was deleted or is inaccessible; fall back to regular send

        logger.debug(
            "Reply target message not found, falling back to channel.send"
        )

        await channel.send(text)


async def extract_attachments(
    message: discord.Message | None,
    attachment: discord.Attachment | None = None,
) -> list[tuple[bytes, str]]:
    """Extract attachments from a Discord message.

    Args:
        message: Discord message object possibly containing attachments.
        attachment: Attachment provided as a slash-command option.

    Returns:
        List of (bytes, mime_type) tuples for each attachment.
    """

    message_attachments = message.attachments if message else []
    all_attachments = list(message_attachments)
    if attachment is not None and attachment not in all_attachments:
        all_attachments.append(attachment)

    if not all_attachments:
        return []

    results = []

    for att in all_attachments:
        mime = att.content_type or ""

        mime_base = mime.split(";")[0].strip()

        try:
            data = await att.read()

            results.append((data, mime_base))

        except (discord.HTTPException, OSError, asyncio.TimeoutError) as e:
            logger.error(f"Failed to read attachment {att.filename}: {e}")

    return results
