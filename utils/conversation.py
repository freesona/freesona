# utils/conversation.py: Provider-agnostic Conversation Manager (Short-Term Memory)
# Freesona owns recent messages, summaries, token budgets, expiration, and context assembly.
# Replaces Gemini-specific continuity while preserving identical behavior across every provider.

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional
from collections import deque

from utils.config import load_config

logger = logging.getLogger("FreesonaBot")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ConversationMessage:
    """A single message in the conversation history."""
    role: str              # "user" or "assistant"
    content: str
    timestamp: float       # Unix timestamp
    message_id: Optional[int] = None
    user_id: Optional[int] = None
    username: Optional[str] = None


@dataclass
class ConversationState:
    """Conversation state for a single (guild, channel, user) scope."""
    messages: deque[ConversationMessage] = field(default_factory=deque)
    last_accessed: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _get_conversation_max_messages() -> int:
    return int(load_config().get("conversation_max_messages", 20))

def _get_conversation_token_budget() -> int:
    return int(load_config().get("conversation_token_budget", 4000))

def _get_conversation_ttl_seconds() -> int:
    return int(load_config().get("conversation_ttl_seconds", 3600))  # 1 hour default


# ---------------------------------------------------------------------------
# Global conversation store
# ---------------------------------------------------------------------------

_conversation_store: dict[tuple[int, int, int], ConversationState] = {}
_store_lock = asyncio.Lock()


def _conversation_key(guild_id: int, channel_id: int, user_id: int) -> tuple[int, int, int]:
    return guild_id, channel_id, user_id


# ---------------------------------------------------------------------------
# Core operations
# ---------------------------------------------------------------------------

async def get_conversation(guild_id: int, channel_id: int, user_id: int) -> ConversationState:
    """Get or create conversation state for the given scope."""
    key = _conversation_key(guild_id, channel_id, user_id)
    async with _store_lock:
        if key not in _conversation_store:
            _conversation_store[key] = ConversationState()
        state = _conversation_store[key]
        state.last_accessed = time.time()
        return state


async def add_message(
    guild_id: int,
    channel_id: int,
    user_id: int,
    role: str,
    content: str,
    message_id: Optional[int] = None,
    username: Optional[str] = None,
) -> None:
    """Add a message to the conversation history."""
    if not content or not content.strip():
        return
    
    state = await get_conversation(guild_id, channel_id, user_id)
    msg = ConversationMessage(
        role=role,
        content=content.strip(),
        timestamp=time.time(),
        message_id=message_id,
        user_id=user_id,
        username=username,
    )
    state.messages.append(msg)
    await _enforce_limits(state)


async def add_user_message(
    guild_id: int,
    channel_id: int,
    user_id: int,
    content: str,
    message_id: Optional[int] = None,
    username: Optional[str] = None,
) -> None:
    """Add a user message to the conversation history."""
    await add_message(guild_id, channel_id, user_id, "user", content, message_id, username)


async def add_assistant_message(
    guild_id: int,
    channel_id: int,
    user_id: int,
    content: str,
) -> None:
    """Add an assistant message to the conversation history."""
    await add_message(guild_id, channel_id, user_id, "assistant", content)


async def get_recent_messages(
    guild_id: int,
    channel_id: int,
    user_id: int,
    limit: Optional[int] = None,
) -> list[ConversationMessage]:
    """Get recent messages for the conversation scope."""
    state = await get_conversation(guild_id, channel_id, user_id)
    max_msgs = limit or _get_conversation_max_messages()
    # Return most recent messages, up to limit
    messages = list(state.messages)[-max_msgs:]
    return messages


async def build_conversation_context(
    guild_id: int,
    channel_id: int,
    user_id: int,
) -> str:
    """
    Build conversation context string for prompt injection.
    
    Format:
    [Conversation History]
    User: message
    Assistant: response
    ...
    """
    state = await get_conversation(guild_id, channel_id, user_id)
    
    if not state.messages:
        return ""
    
    parts = ["[Conversation History]"]
    
    for msg in state.messages:
        role_label = "User" if msg.role == "user" else "Assistant"
        if msg.role == "user":
            name_info = []
            if msg.username:
                name_info.append(msg.username)
            if msg.user_id:
                name_info.append(f"ID: {msg.user_id}")
            name_part = f" ({', '.join(name_info)})" if name_info else ""
        else:
            name_part = ""
        
        parts.append(f"{role_label}{name_part}: {msg.content}")
    
    return "\n".join(parts)


async def clear_conversation(
    guild_id: int,
    channel_id: int,
    user_id: Optional[int] = None,
) -> None:
    """Clear conversation history for a channel or specific user."""
    async with _store_lock:
        if user_id is not None:
            key = _conversation_key(guild_id, channel_id, user_id)
            _conversation_store.pop(key, None)
        else:
            # Clear all users in this channel
            keys_to_remove = [
                k for k in _conversation_store.keys()
                if k[0] == guild_id and k[1] == channel_id
            ]
            for key in keys_to_remove:
                _conversation_store.pop(key, None)


async def get_conversation_stats(
    guild_id: int,
    channel_id: int,
    user_id: int,
) -> dict:
    """Get statistics about the conversation state."""
    state = await get_conversation(guild_id, channel_id, user_id)
    return {
        "message_count": len(state.messages),
        "last_accessed": state.last_accessed,
        "token_estimate": _estimate_tokens(state),
    }


def _estimate_tokens(state: ConversationState) -> int:
    """Rough token estimation for the conversation."""
    total_chars = 0
    for msg in state.messages:
        total_chars += len(msg.content)
    # Rough estimate: 4 chars per token
    return total_chars // 4


async def _enforce_limits(state: ConversationState) -> None:
    """Enforce message count and token budget limits."""
    max_messages = _get_conversation_max_messages()
    token_budget = _get_conversation_token_budget()
    
    # Enforce message count limit
    while len(state.messages) > max_messages:
        state.messages.popleft()
    
    # Enforce token budget (rough estimation)
    while _estimate_tokens(state) > token_budget and len(state.messages) > 2:
        # Keep at least 2 messages (1 exchange)
        state.messages.popleft()


async def cleanup_expired_conversations() -> int:
    """Remove conversations that haven't been accessed within TTL. Returns count removed."""
    ttl = _get_conversation_ttl_seconds()
    now = time.time()
    removed = 0
    
    async with _store_lock:
        keys_to_remove = [
            key for key, state in _conversation_store.items()
            if now - state.last_accessed > ttl
        ]
        for key in keys_to_remove:
            _conversation_store.pop(key, None)
            removed += 1
    
    if removed:
        logger.info(f"Cleaned up {removed} expired conversations")
    return removed


# ---------------------------------------------------------------------------
# Periodic cleanup task
# ---------------------------------------------------------------------------

_cleanup_task: Optional[asyncio.Task] = None


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
            except Exception as e:
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


__all__ = [
    "ConversationMessage",
    "ConversationState",
    "get_conversation",
    "add_message",
    "add_user_message",
    "add_assistant_message",
    "get_recent_messages",
    "build_conversation_context",
    "clear_conversation",
    "get_conversation_stats",
    "start_cleanup_task",
    "stop_cleanup_task",
    "cleanup_expired_conversations",
]