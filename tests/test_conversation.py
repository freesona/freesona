# tests/test_conversation.py: Unit tests for ConversationManager

import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
import time
from collections import deque

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils.conversation import (
    ConversationMessage,
    ConversationState,
    add_user_message,
    add_assistant_message,
    get_conversation,
    build_conversation_context,
    clear_conversation,
    get_conversation_stats,
    cleanup_expired_conversations,
    _conversation_store,
    _store_lock,
    _enforce_limits,
    _estimate_tokens,
)


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
        from utils.conversation import _conversation_key
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
        self.assertIn("User (testuser): Hello", result)

    async def test_with_user_and_assistant_messages(self):
        await add_user_message(1, 2, 3, "Hello", 100, "testuser")
        await add_assistant_message(1, 2, 3, "Hi there!")
        result = await build_conversation_context(1, 2, 3)
        self.assertIn("User (testuser): Hello", result)
        self.assertIn("Assistant: Hi there!", result)

    async def test_with_summary(self):
        # Add a message first to create the conversation state
        await add_user_message(1, 2, 3, "New message", 100, "user")
        # Manually inject a summary (but summary field is removed, so this tests nothing now)
        # We'll just verify the function still works without the summary parameter
        result = await build_conversation_context(1, 2, 3)
        self.assertIn("[Conversation History]", result)
        self.assertIn("User (user): New message", result)

    async def test_without_summary_flag(self):
        # Add a message first to create the conversation state
        await add_user_message(1, 2, 3, "New message", 100, "user")
        result = await build_conversation_context(1, 2, 3)
        self.assertIn("[Conversation History]", result)
        self.assertIn("User (user): New message", result)


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
        self.assertEqual(len(state.messages), 20)  # Should be trimmed to max_messages

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
            "User (Alice): Hello",
            "Assistant: Hi Alice!",
            "User (Alice): How are you?",
        ]
        
        for part in expected_parts:
            self.assertIn(part, result)
        
        # Verify order
        idx_user1 = result.index("User (Alice): Hello")
        idx_assistant = result.index("Assistant: Hi Alice!")
        idx_user2 = result.index("User (Alice): How are you?")
        self.assertLess(idx_user1, idx_assistant)
        self.assertLess(idx_assistant, idx_user2)


if __name__ == "__main__":
    unittest.main()