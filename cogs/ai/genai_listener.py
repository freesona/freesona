# cogs/ai/genai_listener.py: Discord event listeners for AI mentions and
# message handling.

import asyncio
import time
from typing import TypeAlias, TypedDict

import discord
from discord.ext import commands

from utils.config import load_config
from utils.conversation import start_cleanup_task, stop_cleanup_task
from utils.generation import extract_attachments, safe_generate, send_response
from utils.guild_world import DiscordGuildWorldAccessor
from utils.intent import FREQUENCY_THRESHOLD, INTENT_IGNORE, evaluate_intent
from utils.memory import extract_and_store_fact
from utils.persona import CURRENT_PERSONA, CURRENT_PERSONA_ID
from utils.roles import resolve_message_role

from .genai_common import (
    _autonomy_cooldown,
    _autonomy_user_cooldown,
    _pending_responses,
    get_reply_target,
    logger,
    should_respond_in_chat_channel,
)


class MentionPayload(TypedDict):
    id: int
    name: str
    mention: str


class ReplyPayload(TypedDict, total=False):
    author: str
    author_id: int
    content: str
    is_bot: bool
    is_webhook: bool
    role: str
    embeds: list[str]


PayloadValue: TypeAlias = (
    str | int | bool | None | list[MentionPayload] | ReplyPayload | list[str]
)
PayloadDict: TypeAlias = dict[str, PayloadValue]


def _extract_embeds(embeds: list[discord.Embed]) -> list[str]:
    """
    Extract text representation from Discord embeds.

    Args:
        embeds: List of Discord Embed objects.

    Returns:
        List of text representations of the embeds.
    """
    embed_texts = []
    for embed in embeds:
        parts = []
        if embed.title:
            parts.append(f"**{embed.title}**")
        if embed.description:
            parts.append(embed.description)
        if embed.fields:
            for field in embed.fields:
                parts.append(f"**{field.name}**: {field.value}")
        if embed.footer and embed.footer.text:
            parts.append(f"*{embed.footer.text}*")
        if embed.author and embed.author.name:
            parts.append(f"-- {embed.author.name}")
        if parts:
            embed_texts.append("\n".join(parts))
    return embed_texts


def build_payload(message: discord.Message, role: str, bot_id: int) -> PayloadDict:
    """
    Build a standardized payload from a Discord message.

    Eliminates duplicated payload construction between conversation and autonomy paths.
    """
    payload: PayloadDict = {
        "role": role,
        "author_id": message.author.id,
        "username": message.author.display_name,
        "author_mention": message.author.mention,
        "content": message.content,
        "mentions": [
            {
                "id": member.id,
                "name": member.display_name,
                "mention": member.mention,
            }
            for member in message.mentions
        ],
        "reply": None,
    }

    # Include embeds from any message with embeds
    # Embeds are converted to text representation for the AI to process
    if message.embeds:
        embed_texts = _extract_embeds(message.embeds)
        if embed_texts:
            payload["embeds"] = embed_texts

    if message.reference and isinstance(message.reference.resolved, discord.Message):
        ref = message.reference.resolved
        reply_payload: ReplyPayload = {
            "author": ref.author.display_name,
            "author_id": ref.author.id,
            "content": ref.content or "",
            "is_bot": ref.author.bot,
            "is_webhook": ref.webhook_id is not None,
            "role": resolve_message_role(ref, bot_id),
        }
        # Also include embeds from replied-to message
        if ref.embeds:
            embed_texts = _extract_embeds(ref.embeds)
            if embed_texts:
                reply_payload["embeds"] = embed_texts
        payload["reply"] = reply_payload

    return payload


class GenAIListenerCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        from utils.memory import init_db

        await init_db()
        await start_cleanup_task()

    async def cog_unload(self):
        for task in _pending_responses.values():
            task.cancel()
        _pending_responses.clear()
        await stop_cleanup_task()

    # -------------------------------------------------------------------
    # on_message
    # -------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None:
            return
        if message.type not in (
            discord.MessageType.default,
            discord.MessageType.reply,
        ):
            return
        # Ignore interaction messages / slash command triggers
        if message.interaction_metadata is not None:
            return

        prefix = await self.bot.get_prefix(message)
        prefixes = [prefix] if isinstance(prefix, str) else prefix
        if any(message.content.startswith(p) for p in prefixes):
            return

        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return

        bot_user = self.bot.user
        if bot_user is None:
            return
        bot_id = bot_user.id
        if message.author.id == bot_id:
            return

        config = load_config()
        whitelist = [int(x) for x in config.get("whitelist_bot_ids", [])]

        if (
            message.author.bot
            and not message.webhook_id
            and message.author.id not in whitelist
        ):
            return

        role = resolve_message_role(message, bot_id)

        # -------------------------------------------------------------------
        # Conversation channel
        # -------------------------------------------------------------------
        chat_channel_id = config.get("chat_channel_id")
        if chat_channel_id and message.channel.id == chat_channel_id:
            response_mode = config.get("conversation_response_mode", "all")
            if not should_respond_in_chat_channel(message, bot_user, response_mode):
                return

            user_id = message.author.id
            channel_snapshot = message.channel
            username_snapshot = message.author.display_name
            message_snapshot = message
            guild_id_snapshot = message.guild.id

            payload = build_payload(message, role, bot_id)

            _debounce_key = (user_id, channel_snapshot.id)
            if _debounce_key in _pending_responses:
                _pending_responses[_debounce_key].cancel()

            async def debounced_respond(_key=_debounce_key):
                try:
                    current_config = load_config()
                    debounce_seconds = current_config.get("debounce_seconds", 1.2)
                    await asyncio.sleep(debounce_seconds)

                    # Check bot permissions before processing
                    guild = channel_snapshot.guild
                    bot_member = guild.get_member(bot_id) if guild else None
                    if (
                        bot_member
                        and not channel_snapshot.permissions_for(
                            bot_member
                        ).send_messages
                    ):
                        return

                    async with channel_snapshot.typing():
                        attachments = await extract_attachments(message_snapshot)
                        response = await safe_generate(
                            payload,
                            current_persona=CURRENT_PERSONA,
                            persona_id=CURRENT_PERSONA_ID,
                            channel_id=channel_snapshot.id,
                            guild_id=guild_id_snapshot,
                            user_id=user_id,
                            message_id=message_snapshot.id,
                            username=username_snapshot,
                            attachments=attachments,
                            guild_world_accessor=DiscordGuildWorldAccessor(self.bot),
                        )
                        reply_target = get_reply_target(message_snapshot, self.bot.user)
                        await send_response(
                            response, channel_snapshot, reply_to=reply_target
                        )

                    # Extract and store long-term user facts after responding
                    try:
                        provider_name = current_config.get("provider", "gemini")
                        model_name = current_config.get(
                            "provider_model"
                        ) or current_config.get(
                            "model_name", "gemini-flash-lite-latest"
                        )
                        await extract_and_store_fact(
                            message_content=message_snapshot.content,
                            display_name=username_snapshot,
                            guild_id=guild_id_snapshot,
                            user_id=user_id,
                            message_id=message_snapshot.id,
                            channel_id=channel_snapshot.id,
                            client=None,
                            model_name=model_name,
                            provider_name=provider_name,
                        )
                    except (RuntimeError, ValueError, OSError) as fact_exc:
                        logger.warning(
                            f"Fact extraction failed for user {user_id}: {fact_exc}"
                        )
                except asyncio.CancelledError:
                    pass
                except (
                    RuntimeError,
                    ValueError,
                    OSError,
                    discord.DiscordException,
                ) as exc:
                    logger.error(
                        f"Error in debounced response for user {user_id}: {exc}"
                    )
                finally:
                    _pending_responses.pop(_key, None)

            _pending_responses[_debounce_key] = asyncio.create_task(debounced_respond())
            return

        # -------------------------------------------------------------------
        # Autonomy
        # -------------------------------------------------------------------
        autonomy_on = config.get("autonomy", False)

        if autonomy_on and role == "user":
            bot_member = message.guild.get_member(bot_id)
            if bot_member:
                perms = message.channel.permissions_for(bot_member)
                if not perms.send_messages:
                    return

            freq_setting = config.get("autonomy_frequency", "default")
            threshold = FREQUENCY_THRESHOLD.get(freq_setting, 0.50)
            now = time.time()
            last_channel = _autonomy_cooldown.get(message.channel.id, 0)
            autonomy_cooldown_seconds = config.get("autonomy_cooldown_seconds", 120)
            autonomy_user_cooldown = config.get("autonomy_user_cooldown", 60)

            last_user = _autonomy_user_cooldown.get(message.author.id, 0)

            channel_ready = now - last_channel > autonomy_cooldown_seconds
            user_ready = now - last_user > autonomy_user_cooldown

            if channel_ready and user_ready:
                intent = evaluate_intent(message, self.bot.user, False)

                if intent.intent != INTENT_IGNORE and intent.confidence >= threshold:
                    _autonomy_cooldown[message.channel.id] = now
                    _autonomy_user_cooldown[message.author.id] = now

                    autonomy_payload = build_payload(message, role, bot_id)

                    async with message.channel.typing():
                        attachments = await extract_attachments(message)
                        response = await safe_generate(
                            autonomy_payload,
                            current_persona=CURRENT_PERSONA,
                            persona_id=CURRENT_PERSONA_ID,
                            channel_id=message.channel.id,
                            guild_id=message.guild.id,
                            user_id=message.author.id,
                            message_id=message.id,
                            username=message.author.display_name,
                            attachments=attachments,
                            guild_world_accessor=DiscordGuildWorldAccessor(self.bot),
                        )
                        reply_target = get_reply_target(message, self.bot.user)
                        await send_response(
                            response, message.channel, reply_to=reply_target
                        )

                    # Extract and store long-term user facts after responding
                    try:
                        current_config = load_config()
                        provider_name = current_config.get("provider", "gemini")
                        model_name = current_config.get(
                            "provider_model"
                        ) or current_config.get(
                            "model_name", "gemini-flash-lite-latest"
                        )
                        await extract_and_store_fact(
                            message_content=message.content,
                            display_name=message.author.display_name,
                            guild_id=message.guild.id,
                            user_id=message.author.id,
                            message_id=message.id,
                            channel_id=message.channel.id,
                            client=None,
                            model_name=model_name,
                            provider_name=provider_name,
                        )
                    except (RuntimeError, ValueError, OSError) as fact_exc:
                        logger.warning(
                            f"Fact extraction failed for user {message.author.id}: {
                                fact_exc
                            }"
                        )
