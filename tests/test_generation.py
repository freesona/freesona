# tests/test_generation.py: Unit tests for generation module

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import discord

from utils.generation import (
    ConversationResponse,
    MessageSegment,
    _send_first_segment_with_reply,
    _strip_reasoning_tags,
    clean_text,
    send_response,
)

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class TestSendResponse(unittest.IsolatedAsyncioTestCase):
    """Tests for send_response function."""

    async def test_send_response_basic(self):
        """send_response should send segments to channel."""
        channel = AsyncMock()

        typing_cm = AsyncMock()
        typing_cm.__aenter__ = AsyncMock(return_value=None)
        typing_cm.__aexit__ = AsyncMock(return_value=None)
        channel.typing = MagicMock(return_value=typing_cm)

        response = ConversationResponse(
            segments=[
                MessageSegment(text="Hello world", typing=False, delay=0)
            ]
        )

        await send_response(response, channel)

        channel.send.assert_called_once_with("Hello world")

    async def test_send_response_with_typing(self):
        """send_response should trigger typing indicator
        when segment has typing=True."""
        channel = AsyncMock()

        # Mock the async context manager for channel.typing()
        typing_cm = AsyncMock()
        typing_cm.__aenter__ = AsyncMock(return_value=None)
        typing_cm.__aexit__ = AsyncMock(return_value=None)
        channel.typing = MagicMock(return_value=typing_cm)

        response = ConversationResponse(
            segments=[MessageSegment(text="Hello", typing=True, delay=1)]
        )

        await send_response(response, channel)

        channel.typing.assert_called_once()
        channel.send.assert_called_once_with("Hello")

    async def test_send_response_reply_to_message(self):
        """send_response should use reply for first segment
        when reply_to is provided."""
        channel = AsyncMock()

        typing_cm = AsyncMock()
        typing_cm.__aenter__ = AsyncMock(return_value=None)
        typing_cm.__aexit__ = AsyncMock(return_value=None)
        channel.typing = MagicMock(return_value=typing_cm)

        reply_to = MagicMock(spec=discord.Message)
        reply_to.reply = AsyncMock()

        response = ConversationResponse(
            segments=[
                MessageSegment(text="First reply", typing=False, delay=0),
                MessageSegment(text="Second message", typing=False, delay=0),
            ]
        )

        await send_response(response, channel, reply_to=reply_to)

        # First segment should use reply
        reply_to.reply.assert_called_once_with("First reply")
        # Second segment should use regular send
        channel.send.assert_called_once_with("Second message")

    async def test_send_response_reply_not_found_fallback(self):
        """send_response should fall back to channel.send
        when reply_to raises NotFound."""
        channel = AsyncMock()

        typing_cm = AsyncMock()
        typing_cm.__aenter__ = AsyncMock(return_value=None)
        typing_cm.__aexit__ = AsyncMock(return_value=None)
        channel.typing = MagicMock(return_value=typing_cm)

        reply_to = MagicMock(spec=discord.Message)
        reply_to.reply = AsyncMock(
            side_effect=discord.NotFound(MagicMock(), "Not found")
        )

        response = ConversationResponse(
            segments=[
                MessageSegment(text="Reply fallback", typing=False, delay=0)
            ]
        )

        await send_response(response, channel, reply_to=reply_to)

        # Should fall back to channel.send
        reply_to.reply.assert_called_once()
        channel.send.assert_called_once_with("Reply fallback")

    async def test_send_response_forbidden_stops_sending(self):
        """send_response should stop sending when Forbidden error occurs."""
        channel = AsyncMock()

        typing_cm = AsyncMock()
        typing_cm.__aenter__ = AsyncMock(return_value=None)
        typing_cm.__aexit__ = AsyncMock(return_value=None)
        channel.typing = MagicMock(return_value=typing_cm)

        channel.send = AsyncMock(
            side_effect=discord.Forbidden(MagicMock(), "Forbidden")
        )

        response = ConversationResponse(
            segments=[
                MessageSegment(text="First", typing=False, delay=0),
                MessageSegment(text="Second", typing=False, delay=0),
            ]
        )

        await send_response(response, channel)

        # Should only try to send the first segment
        self.assertEqual(channel.send.call_count, 1)

    async def test_send_response_empty_segments(self):
        """send_response should handle empty segments list."""
        channel = AsyncMock()

        response = ConversationResponse(segments=[])

        await send_response(response, channel)

        channel.send.assert_not_called()

    async def test_send_response_whitespace_only_segments(self):
        """send_response should skip whitespace-only segments."""
        channel = AsyncMock()

        typing_cm = AsyncMock()
        typing_cm.__aenter__ = AsyncMock(return_value=None)
        typing_cm.__aexit__ = AsyncMock(return_value=None)
        channel.typing = MagicMock(return_value=typing_cm)

        response = ConversationResponse(
            segments=[
                MessageSegment(text="   ", typing=False, delay=0),
                MessageSegment(text="\n\t", typing=False, delay=0),
                MessageSegment(text="Valid message", typing=False, delay=0),
            ]
        )

        await send_response(response, channel)

        # Only the valid message should be sent
        channel.send.assert_called_once_with("Valid message")


class TestSendFirstSegmentWithReply(unittest.IsolatedAsyncioTestCase):
    """Tests for _send_first_segment_with_reply helper function."""

    async def test_reply_success(self):
        """Should use reply when successful."""
        channel = AsyncMock()
        reply_to = MagicMock(spec=discord.Message)
        reply_to.reply = AsyncMock()

        await _send_first_segment_with_reply(channel, "Test message", reply_to)

        reply_to.reply.assert_called_once_with("Test message")
        channel.send.assert_not_called()

    async def test_reply_not_found_fallback(self):
        """Should fall back to channel.send when reply raises NotFound."""
        channel = AsyncMock()
        reply_to = MagicMock(spec=discord.Message)
        reply_to.reply = AsyncMock(
            side_effect=discord.NotFound(MagicMock(), "Not found")
        )

        await _send_first_segment_with_reply(channel, "Test message", reply_to)

        reply_to.reply.assert_called_once_with("Test message")
        channel.send.assert_called_once_with("Test message")


class TestStripReasoningTags(unittest.TestCase):
    """Tests for _strip_reasoning_tags function."""

    def test_strip_thought_tags(self):
        """Should strip <thought>...</thought> tags."""
        text = "Hello <thought>thinking</thought> world"
        result = _strip_reasoning_tags(text)
        self.assertEqual(result, "Hello  world")

    def test_strip_thinking_tags(self):
        """Should strip <thinking>...</thinking> tags."""
        text = "Hello <thinking>reasoning</thinking> world"
        result = _strip_reasoning_tags(text)
        self.assertEqual(result, "Hello  world")

    def test_strip_reasoning_tags(self):
        """Should strip <reasoning>...</reasoning> tags."""
        text = "Hello <reasoning>analysis</reasoning> world"
        result = _strip_reasoning_tags(text)
        self.assertEqual(result, "Hello  world")

    def test_strip_self_closing_tags(self):
        """Should strip self-closing tags like <thought/>."""
        text = "Hello <thought/> world"
        result = _strip_reasoning_tags(text)
        self.assertEqual(result, "Hello  world")

    def test_strip_multiple_tags(self):
        """Should strip multiple different tag types."""
        text = (
            "<thought>think</thought> Hello "
            "<thinking>reason</thinking> world "
            "<reasoning>analyze</reasoning>"
        )
        result = _strip_reasoning_tags(text)
        self.assertEqual(result, "Hello  world")

    def test_strip_multiline_tags(self):
        """Should strip tags with multiline content."""
        text = "Hello\n<thought>\nline1\nline2\n</thought>\nworld"
        result = _strip_reasoning_tags(text)
        self.assertEqual(result, "Hello\n\nworld")

    def test_case_insensitive(self):
        """Should be case insensitive."""
        text = "Hello <THOUGHT>thinking</THOUGHT> world"
        result = _strip_reasoning_tags(text)
        self.assertEqual(result, "Hello  world")

    def test_no_tags_unchanged(self):
        """Should not modify text without reasoning tags."""
        text = "Hello world"
        result = _strip_reasoning_tags(text)
        self.assertEqual(result, "Hello world")


class TestCleanText(unittest.TestCase):
    """Tests for clean_text function with reasoning tag stripping."""

    def test_clean_text_strips_reasoning_tags(self):
        """clean_text should strip reasoning tags before truncating."""
        text = "Hello <thought>secret thought</thought> world"
        result = clean_text(text, limit=100)
        self.assertEqual(result, "Hello  world")

    def test_clean_text_truncates_after_strip(self):
        """clean_text should truncate after stripping tags."""
        text = "Hello <thought>secret</thought> " + "x" * 5000
        result = clean_text(text, limit=100)
        self.assertLessEqual(len(result), 100)
        self.assertNotIn("<thought>", result)

    def test_clean_text_no_tags_normal_truncate(self):
        """clean_text should work normally without tags."""
        text = "x" * 5000
        result = clean_text(text, limit=100)
        self.assertLessEqual(len(result), 100)
        self.assertNotIn("<thought>", result)


if __name__ == "__main__":
    unittest.main()
