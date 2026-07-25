import asyncio
import time

import discord
from discord.ext import commands

from utils.config import load_config
from utils.generation import extract_attachments, safe_generate, send_response
from utils.guild_world import DiscordGuildWorldAccessor
from utils.intent import FREQUENCY_THRESHOLD, INTENT_IGNORE, evaluate_intent
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


class GenAIListenerCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        from utils.memory import init_db

        await init_db()

    async def cog_unload(self):
        for task in _pending_responses.values():
            task.cancel()
        _pending_responses.clear()

    # -------------------------------------------------------------------
    # on_message
    # -------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None:
            return
        if message.type not in (discord.MessageType.default, discord.MessageType.reply):
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

        if message.author.bot and not message.webhook_id and message.author.id not in whitelist:
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

            payload: dict[str, str | int | bool | dict[str, str | int | bool] | None] = {
                "role": role,
                "author_id": user_id,
                "username": username_snapshot,
                "content": message.content,
                "reply": None,
            }

            if message.reference and isinstance(message.reference.resolved, discord.Message):
                ref = message.reference.resolved
                payload["reply"] = {
                    "author": ref.author.display_name,
                    "author_id": ref.author.id,
                    "content": ref.content or "",
                    "is_bot": ref.author.bot,
                    "is_webhook": ref.webhook_id is not None,
                    "role": resolve_message_role(ref, bot_id),
                }

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
                    if bot_member and not channel_snapshot.permissions_for(bot_member).send_messages:
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
                        await send_response(response, channel_snapshot, reply_to=reply_target)
                except asyncio.CancelledError:
                    pass
                except Exception as exc:
                    logger.error(f"Error in debounced response for user {user_id}: {exc}")
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

                    autonomy_payload: dict[str, str | int | None | dict[str, str | int | bool]] = {
                        "role": role,
                        "author_id": message.author.id,
                        "username": message.author.display_name,
                        "content": message.content,
                        "reply": None,
                    }

                    if message.reference and isinstance(message.reference.resolved, discord.Message):
                        ref = message.reference.resolved
                        autonomy_payload["reply"] = {
                            "author": ref.author.display_name,
                            "author_id": ref.author.id,
                            "content": ref.content or "",
                            "is_bot": ref.author.bot,
                            "is_webhook": ref.webhook_id is not None,
                            "role": resolve_message_role(ref, bot_id),
                        }

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
                        await send_response(response, message.channel, reply_to=reply_target)
