#!/usr/bin/env python3

# utils/conversation.py: Provider-agnostic Conversation Manager

# (Short-Term Memory) Freesona owns recent messages, summaries, token

# budgets, expiration, and context assembly. Replaces Gemini-specific

# continuity while preserving identical behavior across every provider.


import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field

from utils.config import load_config

logger = logging.getLogger("FreesonaBot")

_MAX_RETAINED_IMAGE_BYTES = 8 * 1024 * 1024


# ---------------------------------------------------------------------------

# Data structures

# ---------------------------------------------------------------------------


@dataclass
class ConversationMessage:
    """A single message in the conversation history."""

    role: str  # "user" or "assistant"

    content: str

    timestamp: float  # Unix timestamp

    message_id: int | None = None

    user_id: int | None = None

    username: str | None = None

    mentions: list[dict] | None = None

    reply: dict | None = None

    # For Gemini Interactions API multi-turn support

    interaction_id: str | None = None

    embeds: list[str] | None = None  # Text representation of message embeds

    attachments: list[tuple[bytes, str]] | None = None

    has_image_attachment: bool = False


@dataclass
class ConversationState:
    """Conversation state for a single (guild, channel, user) scope."""

    messages: deque[ConversationMessage] = field(default_factory=deque)

    last_accessed: float = field(default_factory=time.time)

    # Store latest Gemini interaction ID for multi-turn

    last_interaction_id: str | None = None


# ---------------------------------------------------------------------------

# Configuration

# ---------------------------------------------------------------------------


def _get_conversation_max_messages() -> int:

    return int(load_config().get("conversation_max_messages", 20))


def _get_conversation_token_budget() -> int:

    return int(load_config().get("conversation_token_budget", 4000))


def _get_conversation_ttl_seconds() -> int:

    return int(
        load_config().get("conversation_ttl_seconds", 3600)
    )  # 1 hour default


# ---------------------------------------------------------------------------

# ConversationManager — standalone conversation orchestration

# ---------------------------------------------------------------------------


class ConversationManager:
    """Manages short-term conversation state per (guild, channel, user) scope.

    All state is owned by this instance. No Discord types are referenced;
    scope identifiers are plain integers.
    """

    def __init__(
        self,
        max_messages: int | None = None,
        token_budget: int | None = None,
        ttl_seconds: int | None = None,
        max_retained_image_bytes: int = _MAX_RETAINED_IMAGE_BYTES,
    ) -> None:
        self._store: dict[tuple[int, int, int], ConversationState] = {}
        self._lock = asyncio.Lock()
        self._max_messages = max_messages
        self._token_budget = token_budget
        self._ttl_seconds = ttl_seconds
        self._max_retained_image_bytes = max_retained_image_bytes

    def _key(
        self, guild_id: int, channel_id: int, user_id: int
    ) -> tuple[int, int, int]:

        return guild_id, channel_id, user_id

    async def get_conversation(
        self, guild_id: int, channel_id: int, user_id: int
    ) -> ConversationState:
        """Get or create conversation state for the given scope."""

        key = self._key(guild_id, channel_id, user_id)

        async with self._lock:
            if key not in self._store:
                self._store[key] = ConversationState()

            state = self._store[key]

            state.last_accessed = time.time()

            return state

    async def add_message(
        self,
        guild_id: int,
        channel_id: int,
        user_id: int,
        role: str,
        content: str,
        message_id: int | None = None,
        username: str | None = None,
        mentions: list[dict] | None = None,
        reply: dict | None = None,
        embeds: list[str] | None = None,
        attachments: list[tuple[bytes, str]] | None = None,
    ) -> None:
        """Add a message to the conversation history."""

        if (not content or not content.strip()) and not attachments:
            return

        state = await self.get_conversation(guild_id, channel_id, user_id)

        retained_attachments = None
        if attachments:
            image_attachments = [
                (data, mime)
                for data, mime in attachments
                if mime.startswith("image/")
            ]
            if (
                sum(len(data) for data, _ in image_attachments)
                <= self._max_retained_image_bytes
            ):
                retained_attachments = image_attachments or None

        msg = ConversationMessage(
            role=role,
            content=content.strip(),
            timestamp=time.time(),
            message_id=message_id,
            user_id=user_id,
            username=username,
            mentions=mentions,
            reply=reply,
            embeds=embeds,
            attachments=retained_attachments,
            has_image_attachment=any(
                mime.startswith("image/") for _, mime in (attachments or [])
            ),
        )

        state.messages.append(msg)

        await self._enforce_limits(state)

    async def add_user_message(
        self,
        guild_id: int,
        channel_id: int,
        user_id: int,
        content: str,
        message_id: int | None = None,
        username: str | None = None,
        mentions: list[dict] | None = None,
        reply: dict | None = None,
        embeds: list[str] | None = None,
        attachments: list[tuple[bytes, str]] | None = None,
    ) -> None:
        """Add a user message to the conversation history."""

        await self.add_message(
            guild_id,
            channel_id,
            user_id,
            "user",
            content,
            message_id,
            username,
            mentions,
            reply,
            embeds,
            attachments,
        )

    async def get_recent_image_attachments(
        self, guild_id: int, channel_id: int, user_id: int
    ) -> list[tuple[bytes, str]]:
        """Return image bytes from the most recent attachment-bearing user
        message.
        """
        state = await self.get_conversation(guild_id, channel_id, user_id)
        for message in reversed(state.messages):
            if message.has_image_attachment:
                return message.attachments or []
        return []

    async def add_assistant_message(
        self,
        guild_id: int,
        channel_id: int,
        user_id: int,
        content: str,
    ) -> None:
        """Add an assistant message to the conversation history."""

        await self.add_message(guild_id, channel_id, user_id, "assistant", content)

    async def set_last_interaction_id(
        self,
        guild_id: int,
        channel_id: int,
        user_id: int,
        interaction_id: str,
    ) -> None:
        """Store the latest interaction ID for multi-turn conversations."""

        state = await self.get_conversation(guild_id, channel_id, user_id)

        state.last_interaction_id = interaction_id

        # Also update the last assistant message if it exists

        for msg in reversed(state.messages):
            if msg.role == "assistant":
                msg.interaction_id = interaction_id

                break

    async def get_last_interaction_id(
        self,
        guild_id: int,
        channel_id: int,
        user_id: int,
    ) -> str | None:
        """Get the latest interaction ID for multi-turn conversations."""

        state = await self.get_conversation(guild_id, channel_id, user_id)

        return state.last_interaction_id

    async def get_recent_messages(
        self,
        guild_id: int,
        channel_id: int,
        user_id: int,
        limit: int | None = None,
    ) -> list[ConversationMessage]:
        """Get recent messages for the conversation scope."""

        state = await self.get_conversation(guild_id, channel_id, user_id)

        max_msgs = limit or (
            self._max_messages
            if self._max_messages is not None
            else _get_conversation_max_messages()
        )

        # Return most recent messages, up to limit

        messages = list(state.messages)[-max_msgs:]

        return messages

    async def build_conversation_context(
        self, guild_id: int, channel_id: int, user_id: int
    ) -> str:
        """

        Build conversation context string for prompt injection.



        Format:

        [Conversation History]

        User (name, @mention):



        mentions:

        - name (@mention, ID)

        ...



        Message:

        content



        Reply to:

        role (name, @mention): content

        ...



        Assistant:

        content

        ...

        """

        state = await self.get_conversation(guild_id, channel_id, user_id)

        if not state.messages:
            return ""

        parts = ["[Conversation History]"]

        for msg in state.messages:
            if msg.role == "user":
                # Build user header with name and mention

                name_parts = []

                if msg.username:
                    name_parts.append(msg.username)

                if msg.user_id:
                    name_parts.append(f"ID: {msg.user_id}")

                name_part = f" ({', '.join(name_parts)})" if name_parts else ""

                parts.append(f"User{name_part}:")

                # Add mentions if present

                if msg.mentions:
                    parts.append("mentions:")

                    for mention in msg.mentions:
                        if isinstance(mention, dict):
                            m_name = mention.get("name", "Unknown")

                            m_id = mention.get("id", "Unknown")

                            m_mention = mention.get("mention", f"<@{m_id}>")

                            parts.append(f"  - {m_name} ({m_mention}, ID: {m_id})")

                # Add reply context if present

                if msg.reply:
                    parts.append("Reply to:")

                    reply = msg.reply

                    if isinstance(reply, dict):
                        r_role = reply.get("role", "user")

                        r_author = reply.get("author", "Unknown")

                        r_author_id = reply.get("author_id", "Unknown")

                        r_content = reply.get("content", "")

                        parts.append(
                            f"  {r_role.capitalize()} ({r_author}, "
                            f"ID: {r_author_id}): {r_content}"
                        )

                        # Add reply embeds if present

                        if reply.get("embeds"):
                            parts.append("  Embeds:")

                            for embed_text in reply["embeds"]:
                                parts.append(f"    {embed_text}")

                parts.append(f"Message:\n{msg.content}")

                # Add embeds if present

                if msg.embeds:
                    parts.append("Embeds:")

                    for embed_text in msg.embeds:
                        parts.append(f"  {embed_text}")

            else:
                parts.append(f"Assistant: {msg.content}")

        return "\n".join(parts)

    async def clear_conversation(
        self,
        guild_id: int,
        channel_id: int,
        user_id: int | None = None,
    ) -> None:
        """Clear conversation history for a channel or specific user."""

        async with self._lock:
            if user_id is not None:
                key = self._key(guild_id, channel_id, user_id)

                self._store.pop(key, None)

            else:
                # Clear all users in this channel

                keys_to_remove = [
                    k
                    for k in self._store
                    if k[0] == guild_id and k[1] == channel_id
                ]

                for key in keys_to_remove:
                    self._store.pop(key, None)

    async def get_conversation_stats(
        self, guild_id: int, channel_id: int, user_id: int
    ) -> dict:
        """Get statistics about the conversation state."""

        state = await self.get_conversation(guild_id, channel_id, user_id)

        return {
            "message_count": len(state.messages),
            "last_accessed": state.last_accessed,
            "token_estimate": self._estimate_tokens(state),
        }

    def _estimate_tokens(self, state: ConversationState) -> int:
        """Rough token estimation for the conversation."""

        total_chars = 0

        for msg in state.messages:
            total_chars += len(msg.content)

            # Include embeds in token estimation

            if msg.embeds:
                for embed_text in msg.embeds:
                    total_chars += len(embed_text)

            # Include reply embeds in token estimation

            if (
                msg.reply
                and isinstance(msg.reply, dict)
                and msg.reply.get("embeds")
            ):
                for embed_text in msg.reply["embeds"]:
                    total_chars += len(embed_text)

        # Rough estimate: 4 chars per token

        return total_chars // 4

    async def _enforce_limits(self, state: ConversationState) -> None:
        """Enforce message count and token budget limits."""

        # Enforce message count limit

        max_messages = (
            self._max_messages
            if self._max_messages is not None
            else _get_conversation_max_messages()
        )
        token_budget = (
            self._token_budget
            if self._token_budget is not None
            else _get_conversation_token_budget()
        )

        while len(state.messages) > max_messages:
            state.messages.popleft()

        # Enforce token budget (rough estimation)

        while self._estimate_tokens(state) > token_budget and len(
            state.messages
        ) > 2:
            # Keep at least 2 messages (1 exchange)

            state.messages.popleft()

        retained_bytes = sum(
            len(data)
            for message in state.messages
            for data, _ in (message.attachments or [])
        )
        for message in state.messages:
            if retained_bytes <= self._max_retained_image_bytes:
                break
            if message.attachments:
                retained_bytes -= sum(
                    len(data) for data, _ in message.attachments
                )
                message.attachments = None

    async def cleanup_expired_conversations(self) -> int:
        """Remove conversations that haven't been accessed within

        TTL. Returns count removed."""

        now = time.time()

        removed = 0

        async with self._lock:
            keys_to_remove = [
                key
                for key, state in self._store.items()
                if now - state.last_accessed
                > (
                    self._ttl_seconds
                    if self._ttl_seconds is not None
                    else _get_conversation_ttl_seconds()
                )
            ]

            for key in keys_to_remove:
                self._store.pop(key, None)

                removed += 1

        return removed


# ---------------------------------------------------------------------------

# Global conversation store (backward-compatible free functions)

# ---------------------------------------------------------------------------


conversation_manager = ConversationManager()
_conversation_store = conversation_manager._store
_store_lock = conversation_manager._lock


def _conversation_key(
    guild_id: int, channel_id: int, user_id: int
) -> tuple[int, int, int]:

    return guild_id, channel_id, user_id


async def get_conversation(
    guild_id: int, channel_id: int, user_id: int
) -> ConversationState:
    """Get or create conversation state for the given scope."""
    return await conversation_manager.get_conversation(
        guild_id, channel_id, user_id
    )


async def add_message(
    guild_id: int,
    channel_id: int,
    user_id: int,
    role: str,
    content: str,
    message_id: int | None = None,
    username: str | None = None,
    mentions: list[dict] | None = None,
    reply: dict | None = None,
    embeds: list[str] | None = None,
    attachments: list[tuple[bytes, str]] | None = None,
) -> None:
    """Add a message to the conversation history."""
    await conversation_manager.add_message(
        guild_id,
        channel_id,
        user_id,
        role,
        content,
        message_id,
        username,
        mentions,
        reply,
        embeds,
        attachments,
    )


async def add_user_message(
    guild_id: int,
    channel_id: int,
    user_id: int,
    content: str,
    message_id: int | None = None,
    username: str | None = None,
    mentions: list[dict] | None = None,
    reply: dict | None = None,
    embeds: list[str] | None = None,
    attachments: list[tuple[bytes, str]] | None = None,
) -> None:
    """Add a user message to the conversation history."""
    await conversation_manager.add_user_message(
        guild_id,
        channel_id,
        user_id,
        content,
        message_id,
        username,
        mentions,
        reply,
        embeds,
        attachments,
    )


async def get_recent_image_attachments(
    guild_id: int, channel_id: int, user_id: int
) -> list[tuple[bytes, str]]:
    """Return image bytes from the most recent attachment-bearing user
    message.
    """
    return await conversation_manager.get_recent_image_attachments(
        guild_id, channel_id, user_id
    )


async def add_assistant_message(
    guild_id: int,
    channel_id: int,
    user_id: int,
    content: str,
) -> None:
    """Add an assistant message to the conversation history."""
    await conversation_manager.add_assistant_message(
        guild_id, channel_id, user_id, content
    )


async def set_last_interaction_id(
    guild_id: int,
    channel_id: int,
    user_id: int,
    interaction_id: str,
) -> None:
    """Store the latest interaction ID for multi-turn conversations."""
    await conversation_manager.set_last_interaction_id(
        guild_id, channel_id, user_id, interaction_id
    )


async def get_last_interaction_id(
    guild_id: int,
    channel_id: int,
    user_id: int,
) -> str | None:
    """Get the latest interaction ID for multi-turn conversations."""
    return await conversation_manager.get_last_interaction_id(
        guild_id, channel_id, user_id
    )


async def get_recent_messages(
    guild_id: int,
    channel_id: int,
    user_id: int,
    limit: int | None = None,
) -> list[ConversationMessage]:
    """Get recent messages for the conversation scope."""
    return await conversation_manager.get_recent_messages(
        guild_id, channel_id, user_id, limit
    )


async def build_conversation_context(
    guild_id: int,
    channel_id: int,
    user_id: int,
) -> str:
    """

    Build conversation context string for prompt injection.



    Format:

    [Conversation History]

    User (name, @mention):



    mentions:

    - name (@mention, ID)

    ...



    Message:

    content



    Reply to:

    role (name, @mention): content

    ...



    Assistant:

    content

    ...

    """

    return await conversation_manager.build_conversation_context(
        guild_id, channel_id, user_id
    )


async def clear_conversation(
    guild_id: int,
    channel_id: int,
    user_id: int | None = None,
) -> None:
    """Clear conversation history for a channel or specific user."""
    await conversation_manager.clear_conversation(
        guild_id, channel_id, user_id
    )


async def get_conversation_stats(
    guild_id: int,
    channel_id: int,
    user_id: int,
) -> dict:
    """Get statistics about the conversation state."""
    return await conversation_manager.get_conversation_stats(
        guild_id, channel_id, user_id
    )


def _estimate_tokens(state: ConversationState) -> int:
    """Rough token estimation for the conversation."""
    return conversation_manager._estimate_tokens(state)


async def _enforce_limits(state: ConversationState) -> None:
    """Enforce message count and token budget limits."""
    await conversation_manager._enforce_limits(state)


async def cleanup_expired_conversations() -> int:
    """Remove conversations that haven't been accessed within
    TTL. Returns count removed."""
    return await conversation_manager.cleanup_expired_conversations()


# ---------------------------------------------------------------------------

# Periodic cleanup task

# ---------------------------------------------------------------------------


_cleanup_task: asyncio.Task | None = None


async def start_cleanup_task(interval_seconds: int = 300) -> None:
    """Start the periodic cleanup task."""

    global _cleanup_task

    if _cleanup_task and not _cleanup_task.done():
        return

    async def cleanup_loop():

        while True:
            try:
                await asyncio.sleep(interval_seconds)

                await cleanup_expired_conversations()

            except asyncio.CancelledError:
                break

            except (RuntimeError, ValueError, OSError) as e:
                logger.warning(f"Conversation cleanup error: {e}")

    _cleanup_task = asyncio.create_task(cleanup_loop())


async def stop_cleanup_task() -> None:
    """Stop the periodic cleanup task."""

    global _cleanup_task

    if _cleanup_task and not _cleanup_task.done():
        _cleanup_task.cancel()

        try:
            await _cleanup_task

        except asyncio.CancelledError:
            pass

        _cleanup_task = None


__all__ = [
    "ConversationMessage",
    "ConversationState",
    "add_assistant_message",
    "add_message",
    "add_user_message",
    "build_conversation_context",
    "cleanup_expired_conversations",
    "clear_conversation",
    "get_conversation",
    "get_conversation_stats",
    "get_recent_messages",
    "start_cleanup_task",
    "stop_cleanup_task",
]
