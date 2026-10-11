#!/usr/bin/env python3
# tests/test_generation.py: Unit tests for generation module
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from utils.generation import (
    ConversationResponse,
    GenerationError,
    MessageSegment,
    _send_first_segment_with_reply,
    _strip_reasoning_tags,
    clean_text,
    extract_attachments,
    generate,
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
            segments=[MessageSegment(text="Hello world", typing=False, delay=0)]
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
            segments=[MessageSegment(text="Reply fallback", typing=False, delay=0)]
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


class TestExtractAttachments(unittest.IsolatedAsyncioTestCase):
    async def test_extracts_slash_command_attachment_without_message(self):
        attachment = MagicMock(spec=discord.Attachment)
        attachment.content_type = "image/png"
        attachment.read = AsyncMock(return_value=b"image-data")

        result = await extract_attachments(None, attachment)

        self.assertEqual(result, [(b"image-data", "image/png")])
        attachment.read.assert_awaited_once_with()

    async def test_extracts_message_and_explicit_attachments(self):
        message_attachment = MagicMock(spec=discord.Attachment)
        message_attachment.content_type = "image/jpeg"
        message_attachment.read = AsyncMock(return_value=b"message-image")
        slash_attachment = MagicMock(spec=discord.Attachment)
        slash_attachment.content_type = "image/png"
        slash_attachment.read = AsyncMock(return_value=b"slash-image")
        message = MagicMock(spec=discord.Message)
        message.attachments = [message_attachment]

        result = await extract_attachments(message, slash_attachment)

        self.assertEqual(
            result,
            [(b"message-image", "image/jpeg"), (b"slash-image", "image/png")],
        )


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
        """clean_text should work normally without reasoning tags."""
        text = "x" * 5000
        result = clean_text(text, limit=100)
        self.assertLessEqual(len(result), 100)
        self.assertNotIn("<thought>", result)


class TestGeneratePipeline(unittest.IsolatedAsyncioTestCase):
    async def test_follow_up_reuses_recent_image(self):
        earlier_image = [(b"original-image", "image/png")]
        with (
            patch("utils.generation.rate_limit", new_callable=AsyncMock),
            patch("utils.generation.sanitize_prompt", side_effect=lambda value: value),
            patch("utils.generation.add_user_message", new_callable=AsyncMock),
            patch("utils.generation.get_recent_image_attachments", new_callable=AsyncMock, return_value=earlier_image) as get_images,
            patch("utils.generation.build_system_prompt", new_callable=AsyncMock, return_value="system"),
            patch("utils.generation.generate_text", return_value="It shows a worksheet.") as provider,
            patch("utils.generation.add_assistant_message", new_callable=AsyncMock),
            patch("utils.generation.get_provider_name", return_value="openai"),
            patch("utils.generation.get_provider_model", return_value="model-x"),
            patch("utils.generation.get_model_name", return_value="fallback-model"),
            patch("utils.generation.get_model_temperature", return_value=0.4),
            patch("utils.generation.KB_ENABLED", False),
        ):
            await generate(
                "What is in the same photo?", current_persona="persona",
                guild_id=2, channel_id=3, user_id=1,
            )

        get_images.assert_awaited_once_with(2, 3, 1)
        self.assertEqual(provider.call_args.kwargs["attachments"], earlier_image)

    async def test_missing_referenced_image_is_disclosed_to_provider(self):
        with (
            patch("utils.generation.rate_limit", new_callable=AsyncMock),
            patch("utils.generation.sanitize_prompt", side_effect=lambda value: value),
            patch("utils.generation.add_user_message", new_callable=AsyncMock),
            patch("utils.generation.get_recent_image_attachments", new_callable=AsyncMock, return_value=[]),
            patch("utils.generation.build_system_prompt", new_callable=AsyncMock, return_value="system"),
            patch("utils.generation.generate_text", return_value="I cannot access that image now.") as provider,
            patch("utils.generation.add_assistant_message", new_callable=AsyncMock),
            patch("utils.generation.get_provider_name", return_value="openai"),
            patch("utils.generation.get_provider_model", return_value="model-x"),
            patch("utils.generation.get_model_name", return_value="fallback-model"),
            patch("utils.generation.get_model_temperature", return_value=0.4),
            patch("utils.generation.KB_ENABLED", False),
        ):
            await generate(
                "Please inspect the same photo again", current_persona="persona",
                guild_id=2, channel_id=3, user_id=1,
            )

        self.assertEqual(provider.call_args.kwargs["attachments"], [])
        self.assertIn("do not imply they never uploaded it", provider.call_args.kwargs["instruction_prefix"])

    async def test_generate_preserves_serialized_context_and_provider_handoff(self):
        prompt = {
            "content": "hello",
            "mentions": [{"id": 8, "name": "Lin", "mention": "<@8>"}],
            "reply": {"content": "question"},
            "embeds": ["context"],
        }
        attachments = [(b"image-bytes", "image/png")]
        with (
            patch("utils.generation.rate_limit", new_callable=AsyncMock),
            patch("utils.generation.sanitize_prompt", side_effect=lambda value: f"clean:{value}"),
            patch("utils.generation.add_user_message", new_callable=AsyncMock) as add_user,
            patch("utils.generation.build_system_prompt", new_callable=AsyncMock, return_value="assembled context") as build_prompt,
            patch("utils.generation.generate_text", return_value=("Hello <thought>private</thought>", "interaction-2")) as provider,
            patch("utils.generation.add_assistant_message", new_callable=AsyncMock) as add_assistant,
            patch("utils.generation.get_provider_name", return_value="gemini"),
            patch("utils.generation.get_provider_model", return_value="model-x"),
            patch("utils.generation.get_model_name", return_value="fallback-model"),
            patch("utils.generation.get_model_temperature", return_value=0.4),
            patch("utils.generation.KB_ENABLED", True),
            patch("utils.generation.KB_TOP_K", 5),
            patch("utils.conversation.get_last_interaction_id", new_callable=AsyncMock, return_value="interaction-1"),
            patch("utils.conversation.set_last_interaction_id", new_callable=AsyncMock) as set_interaction,
        ):
            response = await generate(
                prompt,
                current_persona="persona text",
                persona_id="persona-a",
                channel_id=3,
                guild_id=2,
                user_id=1,
                message_id=4,
                username="Ada",
                attachments=attachments,
            )

        add_user.assert_awaited_once_with(
            2,
            3,
            1,
            "clean:hello",
            4,
            "Ada",
            prompt["mentions"],
            prompt["reply"],
            prompt["embeds"],
            attachments,
        )
        assert build_prompt.await_args is not None
        self.assertEqual(build_prompt.await_args.kwargs["persona_id"], "persona-a")
        self.assertEqual(build_prompt.await_args.kwargs["user_message"], "clean:hello")
        self.assertEqual(provider.call_args.args[0], "clean:hello")
        self.assertEqual(provider.call_args.kwargs["system_prompt"], "assembled context")
        self.assertEqual(provider.call_args.kwargs["attachments"], attachments)
        self.assertEqual(
            provider.call_args.kwargs["extra_payload"],
            {"previous_interaction_id": "interaction-1"},
        )
        set_interaction.assert_awaited_once_with(2, 3, 1, "interaction-2")
        add_assistant.assert_awaited_once_with(2, 3, 1, "Hello")
        self.assertEqual(response.first_text(), "Hello")

    async def test_generate_classifies_provider_timeout(self):
        with (
            patch("utils.generation.rate_limit", new_callable=AsyncMock),
            patch("utils.generation.sanitize_prompt", side_effect=lambda value: value),
            patch("utils.generation.add_user_message", new_callable=AsyncMock),
            patch("utils.generation.get_recent_image_attachments", new_callable=AsyncMock) as get_images,
            patch("utils.generation.build_system_prompt", new_callable=AsyncMock, return_value="system"),
            patch("utils.generation.generate_text", side_effect=TimeoutError("request timed out")),
            patch("utils.generation.get_provider_name", return_value="openai"),
            patch("utils.generation.get_provider_model", return_value="model-x"),
            patch("utils.generation.get_model_name", return_value="fallback-model"),
            patch("utils.generation.get_model_temperature", return_value=0.4),
            patch("utils.generation.KB_ENABLED", False),
            patch("utils.generation.KB_TOP_K", 5),
        ):
            with self.assertRaises(GenerationError) as raised:
                await generate("hello", current_persona="persona")
        self.assertEqual(type(raised.exception).__name__, "TimeoutGenerationError")
        get_images.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
