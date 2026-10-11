import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from cogs.ai import genai_listener
from utils.generation import ConversationResponse
from utils.intent import INTENT_GENERAL_CHAT, IntentResult


class FakeTask:
    def __init__(self):
        self.cancelled = False

    def cancel(self):
        self.cancelled = True


class TestBuildPayload(unittest.TestCase):
    def test_serializes_message_fields_mentions_and_embeds(self):
        author = MagicMock()
        author.id = 1
        author.display_name = "Ada"
        author.mention = "<@1>"
        mentioned = MagicMock()
        mentioned.id = 2
        mentioned.display_name = "Lin"
        mentioned.mention = "<@2>"
        embed = discord.Embed(title="Notice", description="Read this")
        embed.add_field(name="Topic", value="Context")
        embed.set_footer(text="Source")
        message = MagicMock(spec=discord.Message)
        message.author = author
        message.content = "Hello"
        message.mentions = [mentioned]
        message.embeds = [embed]
        message.reference = None

        payload = genai_listener.build_payload(message, "user", 99)

        self.assertEqual(payload["content"], "Hello")
        self.assertEqual(payload["role"], "user")
        self.assertEqual(payload["author_id"], 1)
        self.assertEqual(payload["username"], "Ada")
        self.assertEqual(payload["author_mention"], "<@1>")
        self.assertEqual(
            payload["mentions"],
            [{"id": 2, "name": "Lin", "mention": "<@2>"}],
        )
        self.assertEqual(
            payload["embeds"],
            ["**Notice**\nRead this\n**Topic**: Context\n*Source*"],
        )
        self.assertIsNone(payload["reply"])

    def test_empty_embed_is_omitted(self):
        author = MagicMock()
        author.id = 1
        author.display_name = "Ada"
        author.mention = "<@1>"
        message = MagicMock(spec=discord.Message)
        message.author = author
        message.content = "Hello"
        message.mentions = []
        message.embeds = [discord.Embed()]
        message.reference = None
        payload = genai_listener.build_payload(message, "user", 99)
        self.assertNotIn("embeds", payload)


class TestListenerBehavior(unittest.IsolatedAsyncioTestCase):
    def make_message(self, *, content="How does this work?", user_id=7, channel_id=5):
        bot_user = MagicMock(spec=discord.ClientUser)
        bot_user.id = 99
        bot_member = MagicMock()
        guild = MagicMock()
        guild.id = 3
        guild.get_member = lambda member_id: bot_member if member_id == 99 else None
        typing_context = AsyncMock()
        typing_context.__aenter__ = AsyncMock(return_value=None)
        typing_context.__aexit__ = AsyncMock(return_value=None)
        channel = MagicMock()
        channel.id = channel_id
        channel.guild = guild
        perms = MagicMock()
        perms.send_messages = True
        channel.permissions_for = MagicMock(return_value=perms)
        channel.typing = MagicMock(return_value=typing_context)
        author = MagicMock()
        author.id = user_id
        author.display_name = f"user-{user_id}"
        author.mention = f"<@{user_id}>"
        author.bot = False
        message = MagicMock(spec=discord.Message)
        message.guild = guild
        message.type = discord.MessageType.default
        message.interaction_metadata = None
        message.content = content
        message.author = author
        message.channel = channel
        message.mentions = []
        message.embeds = []
        message.reference = None
        message.attachments = []
        message.webhook_id = None
        bot = MagicMock()
        bot.user = bot_user
        bot.get_prefix = AsyncMock(return_value="!")
        ctx_mock = MagicMock()
        ctx_mock.valid = False
        bot.get_context = AsyncMock(return_value=ctx_mock)
        return message, bot

    async def test_direct_message_is_ignored_before_prefix_lookup(self):
        message, bot = self.make_message()
        message.guild = None
        cog = genai_listener.GenAIListenerCog(bot)
        with patch.object(genai_listener, "safe_generate", new_callable=AsyncMock) as gen:
            await cog.on_message(message)
        bot.get_prefix.assert_not_awaited()
        gen.assert_not_awaited()

    async def test_chat_debounce_cancels_old_task_and_processes_latest_message(self):
        first, bot = self.make_message(content="first")
        second, _ = self.make_message(content="latest")
        second.author = first.author
        second.channel = first.channel
        second.guild = first.guild
        old_task = FakeTask()
        new_task = FakeTask()
        pending = {(7, 5): old_task}
        coroutines = []
        tasks = [old_task, new_task]

        def capture_task(coro):
            coroutines.append(coro)
            return tasks[len(coroutines) - 1]

        response = ConversationResponse(segments=[])
        with (
            patch.object(genai_listener, "_pending_responses", pending),
            patch.object(genai_listener, "load_config", return_value={
                "chat_channel_id": 5,
                "conversation_response_mode": "all",
                "debounce_seconds": 0,
            }),
            patch.object(genai_listener, "resolve_message_role", return_value="user"),
            patch.object(genai_listener.asyncio, "create_task", side_effect=capture_task),
            patch.object(genai_listener, "extract_attachments", new_callable=AsyncMock, return_value=[]),
            patch.object(genai_listener, "safe_generate", new_callable=AsyncMock, return_value=response) as generate,
            patch.object(genai_listener, "send_response", new_callable=AsyncMock) as send,
            patch.object(genai_listener, "extract_and_store_fact", new_callable=AsyncMock),
            patch.object(genai_listener, "get_reply_target", return_value=None),
            patch.object(genai_listener, "DiscordGuildWorldAccessor", return_value=object()),
        ):
            cog = genai_listener.GenAIListenerCog(bot)
            try:
                await cog.on_message(first)
                await cog.on_message(second)
                self.assertTrue(old_task.cancelled)
                self.assertIs(pending[(7, 5)], new_task)
                await coroutines[-1]
            finally:
                coroutines[0].close()

        self.assertEqual(generate.await_count, 1)
        assert generate.await_args is not None
        self.assertEqual(generate.await_args.args[0]["content"], "latest")
        send.assert_awaited_once_with(response, second.channel, reply_to=None)
        self.assertNotIn((7, 5), pending)

    async def test_autonomy_permission_denial_skips_intent_and_generation(self):
        message, bot = self.make_message()
        message.channel.permissions_for.return_value.send_messages = False
        cooldowns = {}
        user_cooldowns = {}
        with (
            patch.object(genai_listener, "load_config", return_value={"autonomy": True}),
            patch.object(genai_listener, "resolve_message_role", return_value="user"),
            patch.object(genai_listener, "_autonomy_cooldown", cooldowns),
            patch.object(genai_listener, "_autonomy_user_cooldown", user_cooldowns),
            patch.object(genai_listener, "evaluate_intent") as intent,
            patch.object(genai_listener, "safe_generate", new_callable=AsyncMock) as generate,
        ):
            await genai_listener.GenAIListenerCog(bot).on_message(message)
        intent.assert_not_called()
        generate.assert_not_awaited()
        self.assertEqual(cooldowns, {})
        self.assertEqual(user_cooldowns, {})

    async def test_autonomy_below_threshold_does_not_generate_or_set_cooldowns(self):
        message, bot = self.make_message()
        cooldowns = {}
        user_cooldowns = {}
        intent_result = IntentResult(
            intent=INTENT_GENERAL_CHAT,
            confidence=0.49,
            requires_response=False,
        )
        with (
            patch.object(genai_listener, "load_config", return_value={"autonomy": True, "autonomy_frequency": "default"}),
            patch.object(genai_listener, "resolve_message_role", return_value="user"),
            patch.object(genai_listener, "_autonomy_cooldown", cooldowns),
            patch.object(genai_listener, "_autonomy_user_cooldown", user_cooldowns),
            patch.object(genai_listener.time, "time", return_value=1000.0),
            patch.object(genai_listener, "evaluate_intent", return_value=intent_result) as intent,
            patch.object(genai_listener, "safe_generate", new_callable=AsyncMock) as generate,
        ):
            await genai_listener.GenAIListenerCog(bot).on_message(message)
        intent.assert_called_once()
        generate.assert_not_awaited()
        self.assertEqual(cooldowns, {})
        self.assertEqual(user_cooldowns, {})

    async def test_autonomy_accepted_hands_payload_to_generation_and_sends_response(self):
        message, bot = self.make_message()
        cooldowns = {}
        user_cooldowns = {}
        response = ConversationResponse(segments=[])
        with (
            patch.object(genai_listener, "load_config", return_value={"autonomy": True, "autonomy_frequency": "default"}),
            patch.object(genai_listener, "resolve_message_role", return_value="user"),
            patch.object(genai_listener, "_autonomy_cooldown", cooldowns),
            patch.object(genai_listener, "_autonomy_user_cooldown", user_cooldowns),
            patch.object(genai_listener.time, "time", return_value=1000.0),
            patch.object(
                genai_listener,
                "evaluate_intent",
                return_value=IntentResult(INTENT_GENERAL_CHAT, 0.5, True),
            ),
            patch.object(genai_listener, "extract_attachments", new_callable=AsyncMock, return_value=[]),
            patch.object(genai_listener, "safe_generate", new_callable=AsyncMock, return_value=response) as generate,
            patch.object(genai_listener, "send_response", new_callable=AsyncMock) as send,
            patch.object(genai_listener, "extract_and_store_fact", new_callable=AsyncMock),
            patch.object(genai_listener, "get_reply_target", return_value=None),
            patch.object(genai_listener, "DiscordGuildWorldAccessor", return_value=object()),
        ):
            await genai_listener.GenAIListenerCog(bot).on_message(message)

        self.assertEqual(generate.await_count, 1)
        assert generate.await_args is not None
        payload = generate.await_args.args[0]
        self.assertEqual(payload["content"], message.content)
        self.assertEqual(generate.await_args.kwargs["guild_id"], message.guild.id)
        self.assertEqual(generate.await_args.kwargs["channel_id"], message.channel.id)
        self.assertEqual(generate.await_args.kwargs["user_id"], message.author.id)
        send.assert_awaited_once_with(response, message.channel, reply_to=None)
        self.assertIn(message.channel.id, cooldowns)
        self.assertIn(message.author.id, user_cooldowns)

    async def test_autonomy_cooldowns_block_channel_and_user_retries(self):
        first, bot = self.make_message(user_id=7, channel_id=5)
        same_channel_new_user, _ = self.make_message(user_id=8, channel_id=5)
        same_user_new_channel, _ = self.make_message(user_id=7, channel_id=6)
        channel_cooldowns = {}
        user_cooldowns = {}
        time_values = iter([1000.0, 1001.0, 1002.0])
        with (
            patch.object(genai_listener, "load_config", return_value={"autonomy": True, "autonomy_frequency": "default"}),
            patch.object(genai_listener, "resolve_message_role", return_value="user"),
            patch.object(genai_listener, "_autonomy_cooldown", channel_cooldowns),
            patch.object(genai_listener, "_autonomy_user_cooldown", user_cooldowns),
            patch.object(genai_listener.time, "time", side_effect=lambda: next(time_values)),
            patch.object(genai_listener, "evaluate_intent", return_value=IntentResult(INTENT_GENERAL_CHAT, 0.5, True)) as intent,
            patch.object(genai_listener, "extract_attachments", new_callable=AsyncMock, return_value=[]),
            patch.object(genai_listener, "safe_generate", new_callable=AsyncMock, return_value=ConversationResponse(segments=[])) as generate,
            patch.object(genai_listener, "send_response", new_callable=AsyncMock),
            patch.object(genai_listener, "extract_and_store_fact", new_callable=AsyncMock),
            patch.object(genai_listener, "get_reply_target", return_value=None),
            patch.object(genai_listener, "DiscordGuildWorldAccessor", return_value=object()),
        ):
            cog = genai_listener.GenAIListenerCog(bot)
            await cog.on_message(first)
            await cog.on_message(same_channel_new_user)
            await cog.on_message(same_user_new_channel)

        intent.assert_called_once()
        generate.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
