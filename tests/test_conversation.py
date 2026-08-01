# tests/test_conversation.py: Unit tests for ConversationManager

from utils.conversation import (
    ConversationMessage,
    ConversationState,
    _estimate_tokens,
    add_assistant_message,
    add_user_message,
    build_conversation_context,
    cleanup_expired_conversations,
    clear_conversation,
    get_conversation,
    get_conversation_stats,
)
import utils.conversation as conversation_module
import sys
import time
import unittest
from collections import deque
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


_conversation_store = conversation_module._conversation_store
_store_lock = conversation_module._store_lock
_conversation_key = conversation_module._conversation_key


class TestConversationMessage(unittest.TestCase):
    """Tests for ConversationMessage dataclass."""

    def test_message_creation(self):
        msg = ConversationMessage(
            role="user",
            content="Hello",
            username="testuser",
            timestamp=time.time(),
        )
        self.assertEqual(msg.role, "user")
        self.assertEqual(msg.content, "Hello")
        self.assertEqual(msg.username, "testuser")

    def test_message_without_username(self):
        msg = ConversationMessage(
            role="assistant",
            content="Hi there!",
            timestamp=time.time(),
        )
        self.assertEqual(msg.role, "assistant")
        self.assertIsNone(msg.username)


class TestConversationState(unittest.TestCase):
    """Tests for ConversationState dataclass."""

    def test_state_creation(self):
        state = ConversationState()
        self.assertEqual(len(state.messages), 0)
        # summary field removed

    def test_state_with_messages(self):
        msg = ConversationMessage(
            role="user",
            content="Test",
            timestamp=time.time(),
        )
        state = ConversationState(
            messages=deque([msg]),
            # summary field removed
        )
        self.assertEqual(len(state.messages), 1)
        # summary field removed


class TestConversationKey(unittest.TestCase):
    """Tests for conversation key generation."""

    def test_key_format(self):
        key = _conversation_key(1, 2, 3)
        self.assertEqual(key, (1, 2, 3))


class TestAddUserMessage(unittest.IsolatedAsyncioTestCase):
    """Tests for add_user_message function."""

    async def asyncSetUp(self):
        async with _store_lock:
            _conversation_store.clear()

    async def asyncTearDown(self):
        async with _store_lock:
            _conversation_store.clear()

    async def test_add_user_message_creates_conversation(self):
        await add_user_message(
            guild_id=1,
            channel_id=2,
            user_id=3,
            content="Hello",
            message_id=100,
            username="testuser",
        )
        state = await get_conversation(1, 2, 3)
        self.assertEqual(len(state.messages), 1)
        self.assertEqual(state.messages[0].role, "user")
        self.assertEqual(state.messages[0].content, "Hello")
        self.assertEqual(state.messages[0].username, "testuser")

    async def test_add_multiple_user_messages(self):
        await add_user_message(1, 2, 3, "First", 100, "user1")
        await add_user_message(1, 2, 3, "Second", 101, "user1")
        state = await get_conversation(1, 2, 3)
        self.assertEqual(len(state.messages), 2)
        self.assertEqual(state.messages[0].content, "First")
        self.assertEqual(state.messages[1].content, "Second")

    async def test_separate_users_have_separate_conversations(self):
        await add_user_message(1, 2, 3, "User A", 100, "usera")
        await add_user_message(1, 2, 4, "User B", 101, "userb")
        state_a = await get_conversation(1, 2, 3)
        state_b = await get_conversation(1, 2, 4)
        self.assertEqual(len(state_a.messages), 1)
        self.assertEqual(len(state_b.messages), 1)
        self.assertEqual(state_a.messages[0].content, "User A")
        self.assertEqual(state_b.messages[0].content, "User B")

    async def test_separate_channels_have_separate_conversations(self):
        await add_user_message(1, 2, 3, "Channel A", 100, "user")
        await add_user_message(1, 3, 3, "Channel B", 101, "user")
        state_a = await get_conversation(1, 2, 3)
        state_b = await get_conversation(1, 3, 3)
        self.assertEqual(len(state_a.messages), 1)
        self.assertEqual(len(state_b.messages), 1)
        self.assertEqual(state_a.messages[0].content, "Channel A")
        self.assertEqual(state_b.messages[0].content, "Channel B")


class TestAddAssistantMessage(unittest.IsolatedAsyncioTestCase):
    """Tests for add_assistant_message function."""

    async def asyncSetUp(self):
        async with _store_lock:
            _conversation_store.clear()

    async def asyncTearDown(self):
        async with _store_lock:
            _conversation_store.clear()

    async def test_add_assistant_message(self):
        await add_user_message(1, 2, 3, "Hello", 100, "user")
        await add_assistant_message(1, 2, 3, "Hi there!")
        state = await get_conversation(1, 2, 3)
        self.assertEqual(len(state.messages), 2)
        self.assertEqual(state.messages[0].role, "user")
        self.assertEqual(state.messages[1].role, "assistant")
        self.assertEqual(state.messages[1].content, "Hi there!")


class TestGetConversation(unittest.IsolatedAsyncioTestCase):
    """Tests for get_conversation function."""

    async def asyncSetUp(self):
        async with _store_lock:
            _conversation_store.clear()

    async def asyncTearDown(self):
        async with _store_lock:
            _conversation_store.clear()

    async def test_get_nonexistent_returns_empty_state(self):
        state = await get_conversation(999, 999, 999)
        self.assertIsInstance(state, ConversationState)
        self.assertEqual(len(state.messages), 0)

    async def test_get_existing_returns_state(self):
        await add_user_message(1, 2, 3, "Test", 100, "user")
        state = await get_conversation(1, 2, 3)
        self.assertEqual(len(state.messages), 1)


class TestBuildConversationContext(unittest.IsolatedAsyncioTestCase):
    """Tests for build_conversation_context function."""

    async def asyncSetUp(self):
        async with _store_lock:
            _conversation_store.clear()

    async def asyncTearDown(self):
        async with _store_lock:
            _conversation_store.clear()

    async def test_empty_conversation_returns_empty_string(self):
        result = await build_conversation_context(1, 2, 3)
        self.assertEqual(result, "")

    async def test_with_user_message_only(self):
        await add_user_message(1, 2, 3, "Hello", 100, "testuser")
        result = await build_conversation_context(1, 2, 3)
        self.assertIn("[Conversation History]", result)
        self.assertIn("User (testuser, ID: 3):", result)
        self.assertIn("Message:\nHello", result)

    async def test_with_user_and_assistant_messages(self):
        await add_user_message(1, 2, 3, "Hello", 100, "testuser")
        await add_assistant_message(1, 2, 3, "Hi there!")
        result = await build_conversation_context(1, 2, 3)
        self.assertIn("[Conversation History]", result)
        self.assertIn("User (testuser, ID: 3):", result)
        self.assertIn("Message:\nHello", result)
        self.assertIn("Assistant: Hi there!", result)

    async def test_with_summary(self):
        # Add a message first to create the conversation state
        await add_user_message(1, 2, 3, "New message", 100, "user")
        # Manually inject a summary (but summary field is removed,
                # so this tests nothing now)
        # We'll just verify the function still works without the summary
        # parameter
        result = await build_conversation_context(1, 2, 3)
        self.assertIn("[Conversation History]", result)
        self.assertIn("User (user, ID: 3):", result)
        self.assertIn("Message:\nNew message", result)

    async def test_without_summary_flag(self):
        # Add a message first to create the conversation state
        await add_user_message(1, 2, 3, "New message", 100, "user")
        result = await build_conversation_context(1, 2, 3)
        self.assertIn("[Conversation History]", result)
        self.assertIn("User (user, ID: 3):", result)
        self.assertIn("Message:\nNew message", result)


class TestClearConversation(unittest.IsolatedAsyncioTestCase):
    """Tests for clear_conversation function."""

    async def asyncSetUp(self):
        async with _store_lock:
            _conversation_store.clear()

    async def asyncTearDown(self):
        async with _store_lock:
            _conversation_store.clear()

    async def test_clear_specific_user(self):
        await add_user_message(1, 2, 3, "User A msg", 100, "usera")
        await add_user_message(1, 2, 4, "User B msg", 101, "userb")
        await clear_conversation(1, 2, user_id=3)
        state_a = await get_conversation(1, 2, 3)
        state_b = await get_conversation(1, 2, 4)
        self.assertEqual(len(state_a.messages), 0)
        self.assertEqual(len(state_b.messages), 1)

    async def test_clear_all_users_in_channel(self):
        await add_user_message(1, 2, 3, "User A msg", 100, "usera")
        await add_user_message(1, 2, 4, "User B msg", 101, "userb")
        await clear_conversation(1, 2)
        state_a = await get_conversation(1, 2, 3)
        state_b = await get_conversation(1, 2, 4)
        self.assertEqual(len(state_a.messages), 0)
        self.assertEqual(len(state_b.messages), 0)

    async def test_clear_nonexistent_does_not_error(self):
        await clear_conversation(999, 999)
        await clear_conversation(999, 999, user_id=999)


class TestBudgetEnforcement(unittest.IsolatedAsyncioTestCase):
    """Tests for message count and token budget enforcement."""

    async def asyncSetUp(self):
        async with _store_lock:
            _conversation_store.clear()

    async def asyncTearDown(self):
        async with _store_lock:
            _conversation_store.clear()

    async def test_message_count_limit_enforced(self):
        # Default max_messages is 20, add 25 messages
        for i in range(25):
            await add_user_message(1, 2, 3, f"Message {i}", i, "user")
        state = await get_conversation(1, 2, 3)
        # Should be trimmed to max_messages
        self.assertEqual(len(state.messages), 20)

    async def test_token_budget_enforced(self):
        # Create a conversation with long messages to trigger token budget
        # token_budget is 4000, rough estimate is chars // 4
        # So we need ~16000 chars to exceed budget
        long_content = "x" * 2000  # ~500 tokens each
        for i in range(10):
            await add_user_message(1, 2, 3, long_content, i, "user")
        state = await get_conversation(1, 2, 3)
        # Should have trimmed to fit within token budget
        self.assertLessEqual(_estimate_tokens(state), 4000)


class TestGetConversationStats(unittest.IsolatedAsyncioTestCase):
    """Tests for get_conversation_stats function."""

    async def asyncSetUp(self):
        async with _store_lock:
            _conversation_store.clear()

    async def asyncTearDown(self):
        async with _store_lock:
            _conversation_store.clear()

    async def test_stats_for_empty_conversation(self):
        stats = await get_conversation_stats(1, 2, 3)
        self.assertEqual(stats["message_count"], 0)
        # has_summary removed
        self.assertIn("token_estimate", stats)
        self.assertIn("last_accessed", stats)

    async def test_stats_for_populated_conversation(self):
        await add_user_message(1, 2, 3, "Hello", 100, "user")
        await add_assistant_message(1, 2, 3, "Hi!")
        stats = await get_conversation_stats(1, 2, 3)
        self.assertEqual(stats["message_count"], 2)
        # has_summary removed
        self.assertIn("token_estimate", stats)
        self.assertGreater(stats["token_estimate"], 0)
        self.assertIn("last_accessed", stats)


class TestCleanupExpiredConversations(unittest.IsolatedAsyncioTestCase):
    """Tests for cleanup_expired_conversations function."""

    async def asyncSetUp(self):
        async with _store_lock:
            _conversation_store.clear()

    async def asyncTearDown(self):
        async with _store_lock:
            _conversation_store.clear()

    async def test_cleanup_removes_expired(self):
        await add_user_message(1, 2, 3, "Test", 100, "user")
        # Manually set last_accessed to be very old
        async with _store_lock:
            state = _conversation_store[(1, 2, 3)]
            state.last_accessed = time.time() - 7200  # 2 hours ago

        removed = await cleanup_expired_conversations()
        self.assertEqual(removed, 1)
        state = await get_conversation(1, 2, 3)
        self.assertEqual(len(state.messages), 0)

    async def test_cleanup_keeps_recent(self):
        await add_user_message(1, 2, 3, "Test", 100, "user")
        removed = await cleanup_expired_conversations()
        self.assertEqual(removed, 0)
        state = await get_conversation(1, 2, 3)
        self.assertEqual(len(state.messages), 1)


class TestConversationIsolation(unittest.IsolatedAsyncioTestCase):
    """Tests to verify conversation isolation across dimensions."""

    async def asyncSetUp(self):
        async with _store_lock:
            _conversation_store.clear()

    async def asyncTearDown(self):
        async with _store_lock:
            _conversation_store.clear()

    async def test_isolation_by_guild(self):
        await add_user_message(1, 2, 3, "Guild 1", 100, "user")
        await add_user_message(2, 2, 3, "Guild 2", 101, "user")
        state_1 = await get_conversation(1, 2, 3)
        state_2 = await get_conversation(2, 2, 3)
        self.assertEqual(state_1.messages[0].content, "Guild 1")
        self.assertEqual(state_2.messages[0].content, "Guild 2")

    async def test_isolation_by_channel(self):
        await add_user_message(1, 2, 3, "Channel 1", 100, "user")
        await add_user_message(1, 3, 3, "Channel 2", 101, "user")
        state_1 = await get_conversation(1, 2, 3)
        state_2 = await get_conversation(1, 3, 3)
        self.assertEqual(state_1.messages[0].content, "Channel 1")
        self.assertEqual(state_2.messages[0].content, "Channel 2")

    async def test_isolation_by_user(self):
        await add_user_message(1, 2, 3, "User A", 100, "usera")
        await add_user_message(1, 2, 4, "User B", 101, "userb")
        state_a = await get_conversation(1, 2, 3)
        state_b = await get_conversation(1, 2, 4)
        self.assertEqual(state_a.messages[0].content, "User A")
        self.assertEqual(state_b.messages[0].content, "User B")


class TestConversationFormat(unittest.IsolatedAsyncioTestCase):
    """Tests for the exact format of conversation context."""

    async def asyncSetUp(self):
        async with _store_lock:
            _conversation_store.clear()

    async def asyncTearDown(self):
        async with _store_lock:
            _conversation_store.clear()

    async def test_format_matches_expected_output(self):
        await add_user_message(1, 2, 3, "Hello", 100, "Alice")
        await add_assistant_message(1, 2, 3, "Hi Alice!")
        await add_user_message(1, 2, 3, "How are you?", 102, "Alice")

        result = await build_conversation_context(1, 2, 3)

        expected_parts = [
            "[Conversation History]",
            "User (Alice, ID: 3):",
            "Message:\nHello",
            "Assistant: Hi Alice!",
            "User (Alice, ID: 3):",
            "Message:\nHow are you?",
        ]

        for part in expected_parts:
            self.assertIn(part, result)

        # Verify order
        idx_user1 = result.index("User (Alice, ID: 3):")
        idx_msg1 = result.index("Message:\nHello")
        idx_assistant = result.index("Assistant: Hi Alice!")
        idx_user2 = result.index("User (Alice, ID: 3):", idx_assistant)
        idx_msg2 = result.index("Message:\nHow are you?")
        self.assertLess(idx_user1, idx_msg1)
        self.assertLess(idx_msg1, idx_assistant)
        self.assertLess(idx_assistant, idx_user2)
        self.assertLess(idx_user2, idx_msg2)


class TestConversationEmbeds(unittest.IsolatedAsyncioTestCase):
    """Tests for embeds in conversation context."""

    async def asyncSetUp(self):
        async with _store_lock:
            _conversation_store.clear()

    async def asyncTearDown(self):
        async with _store_lock:
            _conversation_store.clear()

    async def test_build_context_with_embeds_in_user_message(self):
        """Test that embeds in user messages are included
        in conversation context."""
        await add_user_message(
            guild_id=1,
            channel_id=2,
            user_id=3,
            content="Check this out",
            message_id=100,
            username="Alice",
            embeds=["**Title**\nDescription\n**Field**: Value"],
        )

        result = await build_conversation_context(1, 2, 3)

        self.assertIn("Embeds:", result)
        self.assertIn("**Title**\nDescription\n**Field**: Value", result)

    async def test_build_context_with_multiple_embeds_in_user_message(self):
        """Test that multiple embeds in user messages are all included."""
        await add_user_message(
            guild_id=1,
            channel_id=2,
            user_id=3,
            content="Multiple embeds",
            message_id=100,
            username="Alice",
            embeds=["Embed 1 content", "Embed 2 content", "Embed 3 content"],
        )

        result = await build_conversation_context(1, 2, 3)

        self.assertIn("Embeds:", result)
        self.assertIn("Embed 1 content", result)
        self.assertIn("Embed 2 content", result)
        self.assertIn("Embed 3 content", result)

    async def test_build_context_with_embeds_in_reply(self):
        """Test that embeds in reply messages are included
        in conversation context."""
        await add_user_message(
            guild_id=1,
            channel_id=2,
            user_id=3,
            content="Replying to this",
            message_id=101,
            username="Alice",
            reply={
                "role": "user",
                "author": "Bob",
                "author_id": 4,
                "content": "Original message",
                "embeds": ["**Reply Embed**\nEmbed description"],
            },
        )

        result = await build_conversation_context(1, 2, 3)

        self.assertIn("Reply to:", result)
        self.assertIn("Reply Embed", result)
        self.assertIn("Embed description", result)
        # Check that embeds are indented under reply
        self.assertIn("  Embeds:", result)
        self.assertIn("    **Reply Embed**\nEmbed description", result)

    async def test_build_context_with_embeds_in_both_message_and_reply(self):
        """Test that embeds in both message and reply are included."""
        await add_user_message(
            guild_id=1,
            channel_id=2,
            user_id=3,
            content="My message with embed",
            message_id=100,
            username="Alice",
            embeds=["**Message Embed**\nContent here"],
            reply={
                "role": "assistant",
                "author": "Bot",
                "author_id": 999,
                "content": "Bot reply",
                "embeds": ["**Reply Embed**\nReply content"],
            },
        )

        result = await build_conversation_context(1, 2, 3)

        # Check message embeds
        self.assertIn("**Message Embed**\nContent here", result)
        # Check reply embeds
        self.assertIn("**Reply Embed**\nReply content", result)

    async def test_token_estimation_includes_embeds(self):
        """Test that token estimation includes embeds content."""
        state = await get_conversation(1, 2, 3)

        # Add message with embeds
        msg = conversation_module.ConversationMessage(
            role="user",
            content="Hello",
            timestamp=time.time(),
            embeds=["Embed content here"],
        )
        state.messages.append(msg)

        # Add message with reply embeds
        msg2 = conversation_module.ConversationMessage(
            role="user",
            content="Reply",
            timestamp=time.time(),
            reply={"embeds": ["Reply embed content"]},
        )
        state.messages.append(msg2)

        tokens = _estimate_tokens(state)

        # "Hello" (5) + "Reply" (5) + "Embed content here" (18) +
        # "Reply embed content" (19) = 47 chars
        # 47 // 4 = 11 tokens
        self.assertGreaterEqual(tokens, 11)

    async def test_token_estimation_includes_reply_embeds(self):
        """Test that token estimation includes reply embeds."""
        state = await get_conversation(1, 2, 3)

        msg = conversation_module.ConversationMessage(
            role="user",
            content="Hi",
            timestamp=time.time(),
            reply={"embeds": ["Reply embed here"]},
        )
        state.messages.append(msg)

        tokens = _estimate_tokens(state)

        # "Hi" (2) + "Reply embed here" (16) = 18 chars
        # 18 // 4 = 4 tokens (minimum)
        self.assertGreaterEqual(tokens, 4)


if __name__ == "__main__":
    unittest.main()
