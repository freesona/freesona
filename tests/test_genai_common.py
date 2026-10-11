import unittest
from unittest.mock import MagicMock

import discord

from cogs.ai.genai_common import get_reply_target, should_respond_in_chat_channel


class TestChatResponseModes(unittest.TestCase):
    def setUp(self):
        self.bot_user = MagicMock(spec=discord.ClientUser)
        self.bot_user.id = 99
        self.message = MagicMock(spec=discord.Message)
        self.message.mentions = []
        self.message.reference = None
        self.message.attachments = []

    def test_all_mode_always_accepts(self):
        self.assertTrue(
            should_respond_in_chat_channel(self.message, self.bot_user, "all")
        )

    def test_mentions_mode_requires_mention_or_reply_to_bot(self):
        self.assertFalse(
            should_respond_in_chat_channel(self.message, self.bot_user, "mentions")
        )
        self.message.mentions = [self.bot_user]
        self.assertTrue(
            should_respond_in_chat_channel(self.message, self.bot_user, "mentions")
        )
        self.message.mentions = []
        reference = MagicMock()
        reference.resolved = MagicMock()
        reference.resolved.author = self.bot_user
        self.message.reference = reference
        self.assertTrue(
            should_respond_in_chat_channel(self.message, self.bot_user, "mentions")
        )

    def test_smart_mode_also_accepts_attachments(self):
        self.assertFalse(
            should_respond_in_chat_channel(self.message, self.bot_user, "smart")
        )
        self.message.attachments = [object()]
        self.assertTrue(
            should_respond_in_chat_channel(self.message, self.bot_user, "smart")
        )

    def test_unknown_mode_preserves_current_accept_behavior(self):
        self.assertTrue(
            should_respond_in_chat_channel(self.message, self.bot_user, "unknown")
        )


class TestReplyTarget(unittest.TestCase):
    def test_no_bot_user_returns_current_message(self):
        message = MagicMock(spec=discord.Message)
        self.assertIs(get_reply_target(message, None), message)

    def test_bot_mention_returns_current_message_even_when_it_is_a_reply(self):
        bot_user = MagicMock(spec=discord.ClientUser)
        bot_user.id = 99
        referenced_author = MagicMock()
        referenced_author.id = 7
        referenced = MagicMock(spec=discord.Message)
        referenced.author = referenced_author
        message = MagicMock(spec=discord.Message)
        message.mentions = [bot_user]
        message.reference = MagicMock()
        message.reference.resolved = referenced
        self.assertIs(get_reply_target(message, bot_user), message)

    def test_reply_to_another_user_targets_the_referenced_message(self):
        bot_user = MagicMock(spec=discord.ClientUser)
        referenced = MagicMock(spec=discord.Message)
        referenced.author = MagicMock()
        referenced.author.id = 7
        message = MagicMock(spec=discord.Message)
        message.mentions = []
        message.reference = MagicMock()
        message.reference.resolved = referenced
        self.assertIs(get_reply_target(message, bot_user), referenced)

    def test_reply_to_bot_targets_current_message(self):
        bot_user = MagicMock(spec=discord.ClientUser)
        referenced = MagicMock(spec=discord.Message)
        referenced.author = bot_user
        message = MagicMock(spec=discord.Message)
        message.mentions = []
        message.reference = MagicMock()
        message.reference.resolved = referenced
        self.assertIs(get_reply_target(message, bot_user), message)


if __name__ == "__main__":
    unittest.main()
