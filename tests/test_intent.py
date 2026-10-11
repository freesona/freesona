import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

import discord

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.intent import (
    FREQUENCY_THRESHOLD,
    INTENT_GENERAL_CHAT,
    INTENT_IGNORE,
    evaluate_intent,
)


class TestEvaluateIntent(unittest.TestCase):
    def make_message(self, content="", *, mentions=None, attachments=None):
        message = MagicMock(spec=discord.Message)
        message.content = content
        message.mentions = mentions or []
        message.attachments = attachments or []
        message.reference = None
        return message

    def test_empty_message_without_attachments_is_ignored(self):
        result = evaluate_intent(self.make_message(), None)
        self.assertEqual(result.intent, INTENT_IGNORE)
        self.assertEqual(result.confidence, 0.0)
        self.assertFalse(result.requires_response)
        self.assertEqual(result.targets, ["empty_message"])

    def test_question_uses_semantic_and_question_signals(self):
        result = evaluate_intent(self.make_message("How does this work?"), None)
        self.assertEqual(result.intent, INTENT_GENERAL_CHAT)
        self.assertEqual(result.confidence, 0.6)
        self.assertTrue(result.requires_response)
        self.assertEqual(result.targets, ["semantic_trigger", "question_mark"])

    def test_short_filler_is_ignored(self):
        result = evaluate_intent(self.make_message("lol"), None)
        self.assertEqual(result.intent, INTENT_IGNORE)
        self.assertEqual(result.confidence, 0.0)
        self.assertIn("short_filler", result.targets)

    def test_mention_scores_high_enough_to_respond(self):
        bot_user = MagicMock(spec=discord.ClientUser)
        bot_user.id = 99
        result = evaluate_intent(
            self.make_message("hey", mentions=[bot_user]), bot_user
        )
        self.assertEqual(result.confidence, 0.9)
        self.assertTrue(result.requires_response)
        self.assertIn("mention_or_reply", result.targets)

    def test_confidence_is_clamped(self):
        bot_user = MagicMock(spec=discord.ClientUser)
        bot_user.id = 99
        attachment = MagicMock()
        attachment.content_type = "image/png"
        message = self.make_message(
            "How do I fix this? `code`",
            mentions=[bot_user],
            attachments=[attachment],
        )
        result = evaluate_intent(message, bot_user)
        self.assertEqual(result.confidence, 1.0)

    def test_frequency_thresholds_remain_current(self):
        self.assertEqual(
            FREQUENCY_THRESHOLD,
            {"low": 0.70, "default": 0.50, "high": 0.35},
        )


if __name__ == "__main__":
    unittest.main()
