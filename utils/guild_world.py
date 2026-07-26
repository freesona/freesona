# utils/guild_world.py: Guild World Context — Environmental grounding for the persona.
#
# Provides lightweight environmental context (guild name, channel name, topic)
# so the character knows "where" they are without storing it as memory.
#
# This is NOT memory — it's the current environment. Fetched fresh each request.
# No persistence, no history, no cross-guild awareness.

from __future__ import annotations

import logging
import discord
from dataclasses import dataclass
from typing import Optional, Protocol

logger = logging.getLogger("FreesonaBot")


# =============================================================================
# Channel Info Dataclass
# =============================================================================

@dataclass
class GuildChannelInfo:
    """
    Lightweight channel metadata for KB 2.0 and environmental awareness.
    
    This is NOT memory — it's the current server structure.
    Fetched fresh when needed, no persistence.
    """
    id: int
    name: str
    type: str  # "text", "voice", "category", "stage", "forum", "thread"
    topic: Optional[str] = None
    position: int = 0
    category_id: Optional[int] = None
    nsfw: bool = False
    
    def format_for_prompt(self) -> str:
        """Format as a compact line for prompt injection."""
        parts = [f"#{self.name}"]
        if self.topic:
            parts.append(f"({self.topic})")
        if self.type != "text":
            parts.append(f"[{self.type}]")
        if self.nsfw:
            parts.append("[NSFW]")
        return " ".join(parts)


# =============================================================================
# GuildWorldAccessor Protocol
# =============================================================================

class GuildWorldAccessor(Protocol):
    """
    Protocol for fetching guild/channel metadata without coupling to Discord.py.
    
    Implementations should be provided by the caller (generation.py / cogs) 
    which has access to the bot and Discord objects.
    """
    
    async def get_guild_name(self, guild_id: int) -> Optional[str]:
        """Return the guild (server) name, or None if unavailable."""
        ...
    
    async def get_channel_name(self, channel_id: int) -> Optional[str]:
        """Return the channel name, or None if unavailable."""
        ...
    
    async def get_channel_topic(self, channel_id: int) -> Optional[str]:
        """Return the channel topic/description, or None if unavailable."""
        ...
    
    async def get_guild_member_count(self, guild_id: int) -> Optional[int]:
        """Return approximate member count, or None if unavailable."""
        ...
    
    async def get_guild_channels(self, guild_id: int) -> list[GuildChannelInfo]:
        """
        Return a list of all channels in the guild with basic metadata.
        
        Useful for KB 2.0 to understand server structure, tag knowledge to channels,
        or let the persona reference other channels by name.
        
        Returns empty list if unavailable.
        """
        ...


# Default no-op accessor (used when Discord context is unavailable)
class NullGuildWorldAccessor:
    """Null implementation that returns no data — safe default for testing/fallback."""
    
    async def get_guild_name(self, guild_id: int) -> Optional[str]:
        _ = guild_id
        return None
    
    async def get_channel_name(self, channel_id: int) -> Optional[str]:
        _ = channel_id
        return None
    
    async def get_channel_topic(self, channel_id: int) -> Optional[str]:
        _ = channel_id
        return None
    
    async def get_guild_member_count(self, guild_id: int) -> Optional[int]:
        _ = guild_id
        return None
    
    async def get_guild_channels(self, guild_id: int) -> list[GuildChannelInfo]:
        _ = guild_id
        return []


NULL_ACCESSOR = NullGuildWorldAccessor()


# =============================================================================
# Context Data Class
# =============================================================================

@dataclass
class GuildWorldContext:
    """
    Structured environmental context for a single generation request.
    
    All fields are optional — provider gracefully handles missing data.
    """
    guild_id: int
    channel_id: int
    guild_name: Optional[str] = None
    channel_name: Optional[str] = None
    channel_topic: Optional[str] = None
    member_count: Optional[int] = None
    
    def format_for_prompt(self) -> str:
        """Format as a human-readable context block for the system prompt."""
        lines = ["[Guild World Context]"]
        
        if self.guild_name:
            lines.append(f"Server: {self.guild_name}")
            if self.member_count:
                lines.append(f"Population: ~{self.member_count:,}")
        
        if self.channel_name:
            lines.append(f"Channel: #{self.channel_name}")
            if self.channel_topic:
                lines.append(f"Topic: {self.channel_topic}")
        
        if len(lines) == 1:
            return ""  # No useful context
        
        return "\n".join(lines)


# =============================================================================
# Core Function: Build Guild World Context
# =============================================================================

async def build_guild_world_context(
    guild_id: int,
    channel_id: int,
    accessor: GuildWorldAccessor = NULL_ACCESSOR,
) -> str:
    """
    Fetch environmental metadata and format for prompt injection.
    
    This is called fresh on every generation — no caching, no persistence.
    The character should react to where they are *right now*.
    
    Args:
        guild_id: Discord guild (server) ID
        channel_id: Discord channel ID
        accessor: Implementation of GuildWorldAccessor (injected by caller)
        
    Returns:
        Formatted context string, or empty string if no data available
    """
    try:
        # Fetch all metadata concurrently
        guild_name = await accessor.get_guild_name(guild_id)
        channel_name = await accessor.get_channel_name(channel_id)
        channel_topic = await accessor.get_channel_topic(channel_id)
        member_count = await accessor.get_guild_member_count(guild_id)
        
        context = GuildWorldContext(
            guild_id=guild_id,
            channel_id=channel_id,
            guild_name=guild_name,
            channel_name=channel_name,
            channel_topic=channel_topic,
            member_count=member_count,
        )
        
        return context.format_for_prompt()
        
    except Exception as e:
        logger.warning(f"GuildWorldContext fetch failed for guild={guild_id}, channel={channel_id}: {e}")
        return ""


# =============================================================================
# Discord.py Implementation (for use in generation.py / cogs)
# =============================================================================

class DiscordGuildWorldAccessor:
    """
    Discord.py implementation of GuildWorldAccessor.
    
    Uses the bot's cache — no API calls unless cache is cold.
    """
    
    def __init__(self, bot):
        self.bot = bot
    
    async def get_guild_name(self, guild_id: int) -> Optional[str]:
        guild = self.bot.get_guild(guild_id)
        return guild.name if guild else None
    
    async def get_channel_name(self, channel_id: int) -> Optional[str]:
        channel = self.bot.get_channel(channel_id)
        if channel and hasattr(channel, 'name'):
            return channel.name
        return None
    
    async def get_channel_topic(self, channel_id: int) -> Optional[str]:
        channel = self.bot.get_channel(channel_id)
        topic = getattr(channel, 'topic', None) if channel else None
        return topic
    
    async def get_guild_member_count(self, guild_id: int) -> Optional[int]:
        guild = self.bot.get_guild(guild_id)
        return guild.member_count if guild else None
    
    async def get_guild_channels(self, guild_id: int) -> list[GuildChannelInfo]:
        """
        Return all channels in the guild with lightweight metadata.
        
        Uses bot's cache — no API calls. Includes text, voice, category,
        stage, forum, and thread channels.
        
        Returns empty list if guild not in cache.
        """
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []
        
        channels = []
        for channel in guild.channels:
            # Determine channel type
            channel_type = "unknown"
            if isinstance(channel, discord.TextChannel):
                channel_type = "text"
            elif isinstance(channel, discord.VoiceChannel):
                channel_type = "voice"
            elif isinstance(channel, discord.CategoryChannel):
                channel_type = "category"
            elif isinstance(channel, discord.StageChannel):
                channel_type = "stage"
            elif isinstance(channel, discord.ForumChannel):
                channel_type = "forum"
            elif isinstance(channel, discord.Thread):
                channel_type = "thread"
            
            # Get topic (only text/forum/stage channels have topics)
            topic = getattr(channel, 'topic', None)
            
            # Get NSFW flag (text/forum/voice channels)
            nsfw = getattr(channel, 'nsfw', False)
            
            # Get category/parent
            category_id = getattr(channel, 'category_id', None)
            
            channels.append(GuildChannelInfo(
                id=channel.id,
                name=channel.name,
                type=channel_type,
                topic=topic,
                position=getattr(channel, 'position', 0),
                category_id=category_id,
                nsfw=nsfw,
            ))
        
        return channels


__all__ = [
    "GuildWorldAccessor",
    "NullGuildWorldAccessor",
    "NULL_ACCESSOR",
    "GuildWorldContext",
    "build_guild_world_context",
    "DiscordGuildWorldAccessor",
    "GuildChannelInfo",
]