# tests/test_character_memory.py: Unit tests for Character Memory subsystem

import os
import sys
import tempfile
import shutil
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class TestMemoryType(unittest.TestCase):
    """Tests for MemoryType enum."""

    def test_memory_type_values(self):
        from utils.character_memory import MemoryType
        self.assertEqual(MemoryType.PROMISE.value, "promise")
        self.assertEqual(MemoryType.SHARED_EXPERIENCE.value, "shared_experience")
        self.assertEqual(MemoryType.RECURRING_JOKE.value, "recurring_joke")
        self.assertEqual(MemoryType.UNFINISHED_ACTIVITY.value, "unfinished_activity")
        self.assertEqual(MemoryType.RELATIONSHIP_PROGRESSION.value, "relationship_progression")
        self.assertEqual(MemoryType.PERSISTENT_DECISION.value, "persistent_decision")


class TestCharacterMemoryDataclass(unittest.TestCase):
    """Tests for CharacterMemory dataclass."""

    def test_character_memory_creation(self):
        from utils.character_memory import CharacterMemory, MemoryType
        mem = CharacterMemory(
            memory_id="test-id",
            guild_id=1,
            user_id=2,
            persona_id="chisato",
            memory_type=MemoryType.PROMISE,
            content="We promised to play chess.",
            importance=0.9,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self.assertEqual(mem.memory_id, "test-id")
        self.assertEqual(mem.guild_id, 1)
        self.assertEqual(mem.user_id, 2)
        self.assertEqual(mem.persona_id, "chisato")
        self.assertEqual(mem.memory_type, MemoryType.PROMISE)
        self.assertEqual(mem.content, "We promised to play chess.")
        self.assertEqual(mem.importance, 0.9)
        self.assertEqual(mem.source_message_ids, [])
        self.assertEqual(mem.metadata, {})

    def test_character_memory_to_dict(self):
        from utils.character_memory import CharacterMemory, MemoryType
        mem = CharacterMemory(
            memory_id="test-id",
            guild_id=1,
            user_id=2,
            persona_id="chisato",
            memory_type=MemoryType.PROMISE,
            content="We promised to play chess.",
            importance=0.9,
            timestamp=datetime.now(timezone.utc).isoformat(),
            source_message_ids=[100, 101],
            metadata={"key": "value"},
        )
        d = mem.to_dict()
        self.assertEqual(d["memory_id"], "test-id")
        self.assertEqual(d["guild_id"], 1)
        self.assertEqual(d["user_id"], 2)
        self.assertEqual(d["persona_id"], "chisato")
        self.assertEqual(d["memory_type"], "promise")
        self.assertEqual(d["content"], "We promised to play chess.")
        self.assertEqual(d["importance"], 0.9)
        self.assertEqual(d["source_message_ids"], [100, 101])
        self.assertEqual(d["metadata"], {"key": "value"})


class TestCharacterMemoryDatabase(unittest.IsolatedAsyncioTestCase):
    """Tests for character memory database operations."""

    async def asyncSetUp(self):
        # Create a unique temporary database for each test
        self.temp_dir = tempfile.mkdtemp()
        self.test_db = os.path.join(self.temp_dir, "test_character_memory.db")
        
        # Set env var BEFORE importing the module
        os.environ["CHARACTER_MEMORY_FILE_PATH"] = self.test_db
        
        # Import/reload to pick up new path
        import importlib
        import utils.character_memory
        importlib.reload(utils.character_memory)
        
        from utils.character_memory import init_db
        await init_db()

    async def asyncTearDown(self):
        import importlib
        os.environ["CHARACTER_MEMORY_FILE_PATH"] = "./character_memory.db"
        import utils.character_memory
        importlib.reload(utils.character_memory)
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    async def test_store_and_get_memory(self):
        from utils.character_memory import CharacterMemory, MemoryType, store_memory, get_memories
        mem = CharacterMemory(
            memory_id="mem-1",
            guild_id=1,
            user_id=2,
            persona_id="chisato",
            memory_type=MemoryType.PROMISE,
            content="We promised to play chess next week.",
            importance=0.9,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        
        await store_memory(mem)
        
        memories = await get_memories(1, 2, "chisato")
        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0].memory_id, "mem-1")
        self.assertEqual(memories[0].content, "We promised to play chess next week.")
        self.assertEqual(memories[0].importance, 0.9)
        self.assertEqual(memories[0].memory_type, MemoryType.PROMISE)

    async def test_get_memories_ordered_by_importance(self):
        from utils.character_memory import CharacterMemory, MemoryType, store_memory, get_memories
        for imp, content in [(0.5, "Low importance"), (0.9, "High importance"), (0.7, "Medium importance")]:
            mem = CharacterMemory(
                memory_id=f"mem-{imp}",
                guild_id=1,
                user_id=2,
                persona_id="chisato",
                memory_type=MemoryType.SHARED_EXPERIENCE,
                content=content,
                importance=imp,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            await store_memory(mem)
        
        memories = await get_memories(1, 2, "chisato")
        self.assertEqual(len(memories), 3)
        # Should be ordered by importance DESC
        self.assertEqual(memories[0].importance, 0.9)
        self.assertEqual(memories[1].importance, 0.7)
        self.assertEqual(memories[2].importance, 0.5)

    async def test_get_memories_respects_limit(self):
        from utils.character_memory import CharacterMemory, MemoryType, store_memory, get_memories
        for i in range(10):
            mem = CharacterMemory(
                memory_id=f"mem-{i}",
                guild_id=1,
                user_id=2,
                persona_id="chisato",
                memory_type=MemoryType.SHARED_EXPERIENCE,
                content=f"Memory {i}",
                importance=0.5 + (i * 0.05),
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            await store_memory(mem)
        
        memories = await get_memories(1, 2, "chisato", limit=5)
        self.assertEqual(len(memories), 5)

    async def test_get_memories_respects_min_importance(self):
        from utils.character_memory import CharacterMemory, MemoryType, store_memory, get_memories
        for imp in [0.2, 0.4, 0.6, 0.8]:
            mem = CharacterMemory(
                memory_id=f"mem-{imp}",
                guild_id=1,
                user_id=2,
                persona_id="chisato",
                memory_type=MemoryType.SHARED_EXPERIENCE,
                content=f"Memory with importance {imp}",
                importance=imp,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            await store_memory(mem)
        
        # MIN_IMPORTANCE is 0.3 by default
        memories = await get_memories(1, 2, "chisato", min_importance=0.5)
        self.assertEqual(len(memories), 2)  # Only 0.6 and 0.8

    async def test_update_memory(self):
        from utils.character_memory import CharacterMemory, MemoryType, store_memory, update_memory, get_memory_by_id
        mem = CharacterMemory(
            memory_id="mem-1",
            guild_id=1,
            user_id=2,
            persona_id="chisato",
            memory_type=MemoryType.PROMISE,
            content="Original content",
            importance=0.5,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        await store_memory(mem)
        
        mem.content = "Updated content"
        mem.importance = 0.8
        await update_memory(mem)
        
        retrieved = await get_memory_by_id("mem-1")
        assert retrieved is not None
        retrieved = retrieved  # type: ignore[reportAssignmentType]
        self.assertEqual(retrieved.content, "Updated content")
        self.assertEqual(retrieved.importance, 0.8)

    async def test_delete_memory(self):
        from utils.character_memory import CharacterMemory, MemoryType, store_memory, delete_memory, get_memory_by_id
        mem = CharacterMemory(
            memory_id="mem-1",
            guild_id=1,
            user_id=2,
            persona_id="chisato",
            memory_type=MemoryType.PROMISE,
            content="To be deleted",
            importance=0.5,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        await store_memory(mem)
        
        await delete_memory("mem-1")
        
        retrieved = await get_memory_by_id("mem-1")
        self.assertIsNone(retrieved)

    async def test_clear_memories(self):
        from utils.character_memory import CharacterMemory, MemoryType, store_memory, clear_memories, get_memories
        for i in range(3):
            mem = CharacterMemory(
                memory_id=f"mem-{i}",
                guild_id=1,
                user_id=2,
                persona_id="chisato",
                memory_type=MemoryType.SHARED_EXPERIENCE,
                content=f"Memory {i}",
                importance=0.5,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            await store_memory(mem)
        
        count = await clear_memories(1, 2, "chisato")
        self.assertEqual(count, 3)
        
        memories = await get_memories(1, 2, "chisato")
        self.assertEqual(len(memories), 0)

    async def test_get_memory_count(self):
        from utils.character_memory import CharacterMemory, MemoryType, store_memory, get_memory_count
        for i in range(3):
            mem = CharacterMemory(
                memory_id=f"mem-{i}",
                guild_id=1,
                user_id=2,
                persona_id="chisato",
                memory_type=MemoryType.SHARED_EXPERIENCE,
                content=f"Memory {i}",
                importance=0.5,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            await store_memory(mem)
        
        count = await get_memory_count(1, 2, "chisato")
        self.assertEqual(count, 3)
        
        # Different scope should have 0
        count2 = await get_memory_count(1, 3, "chisato")
        self.assertEqual(count2, 0)

    async def test_scope_isolation(self):
        """Test that memories are isolated by (guild_id, user_id, persona_id)."""
        from utils.character_memory import CharacterMemory, MemoryType, store_memory, get_memories
        # Store in scope (1, 2, "chisato")
        mem1 = CharacterMemory(
            memory_id="mem-1",
            guild_id=1,
            user_id=2,
            persona_id="chisato",
            memory_type=MemoryType.PROMISE,
            content="Memory in scope 1",
            importance=0.9,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        await store_memory(mem1)
        
        # Store in scope (1, 2, "takina") - different persona
        mem2 = CharacterMemory(
            memory_id="mem-2",
            guild_id=1,
            user_id=2,
            persona_id="takina",
            memory_type=MemoryType.PROMISE,
            content="Memory in scope 2",
            importance=0.9,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        await store_memory(mem2)
        
        # Store in scope (1, 3, "chisato") - different user
        mem3 = CharacterMemory(
            memory_id="mem-3",
            guild_id=1,
            user_id=3,
            persona_id="chisato",
            memory_type=MemoryType.PROMISE,
            content="Memory in scope 3",
            importance=0.9,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        await store_memory(mem3)
        
        # Store in scope (2, 2, "chisato") - different guild
        mem4 = CharacterMemory(
            memory_id="mem-4",
            guild_id=2,
            user_id=2,
            persona_id="chisato",
            memory_type=MemoryType.PROMISE,
            content="Memory in scope 4",
            importance=0.9,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        await store_memory(mem4)
        
        # Each scope should only see its own memories
        m1 = await get_memories(1, 2, "chisato")
        self.assertEqual(len(m1), 1)
        self.assertEqual(m1[0].content, "Memory in scope 1")
        
        m2 = await get_memories(1, 2, "takina")
        self.assertEqual(len(m2), 1)
        self.assertEqual(m2[0].content, "Memory in scope 2")
        
        m3 = await get_memories(1, 3, "chisato")
        self.assertEqual(len(m3), 1)
        self.assertEqual(m3[0].content, "Memory in scope 3")
        
        m4 = await get_memories(2, 2, "chisato")
        self.assertEqual(len(m4), 1)
        self.assertEqual(m4[0].content, "Memory in scope 4")


class TestBuildCharacterMemoryContext(unittest.IsolatedAsyncioTestCase):
    """Tests for build_character_memory_context function."""

    async def asyncSetUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_db = os.path.join(self.temp_dir, "test_character_memory_context.db")
        
        os.environ["CHARACTER_MEMORY_FILE_PATH"] = self.test_db
        
        import importlib
        import utils.character_memory
        importlib.reload(utils.character_memory)
        
        from utils.character_memory import init_db
        await init_db()

    async def asyncTearDown(self):
        import importlib
        os.environ["CHARACTER_MEMORY_FILE_PATH"] = "./character_memory.db"
        import utils.character_memory
        importlib.reload(utils.character_memory)
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    async def test_build_context_empty(self):
        from utils.character_memory import build_character_memory_context
        result = await build_character_memory_context(
            guild_id=1,
            user_id=2,
            persona_id="chisato",
            username="TestUser",
        )
        self.assertIn("Character Memory with TestUser", result)
        self.assertIn("No shared history recorded yet", result)

    async def test_build_context_with_memories(self):
        from utils.character_memory import CharacterMemory, MemoryType, store_memory, build_character_memory_context
        for mem_type, content, imp in [
            (MemoryType.PROMISE, "We promised to play chess.", 0.9),
            (MemoryType.SHARED_EXPERIENCE, "We defeated the boss together.", 0.7),
            (MemoryType.RECURRING_JOKE, "The rubber duck incident.", 0.5),
        ]:
            mem = CharacterMemory(
                memory_id=f"mem-{mem_type.value}",
                guild_id=1,
                user_id=2,
                persona_id="chisato",
                memory_type=mem_type,
                content=content,
                importance=imp,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            await store_memory(mem)
        
        result = await build_character_memory_context(
            guild_id=1,
            user_id=2,
            persona_id="chisato",
            username="TestUser",
        )
        
        self.assertIn("Character Memory with TestUser", result)
        self.assertIn("[PROMISE] We promised to play chess. (importance: 0.9)", result)
        self.assertIn("[SHARED_EXPERIENCE] We defeated the boss together. (importance: 0.7)", result)
        self.assertIn("[RECURRING_JOKE] The rubber duck incident. (importance: 0.5)", result)

    async def test_build_context_without_username(self):
        from utils.character_memory import CharacterMemory, MemoryType, store_memory, build_character_memory_context
        mem = CharacterMemory(
            memory_id="mem-1",
            guild_id=1,
            user_id=2,
            persona_id="chisato",
            memory_type=MemoryType.PROMISE,
            content="Test promise",
            importance=0.8,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        await store_memory(mem)
        
        result = await build_character_memory_context(
            guild_id=1,
            user_id=2,
            persona_id="chisato",
            username="",  # Empty username
        )
        self.assertIn("Character Memory with User 2", result)


class TestExtractionPipeline(unittest.IsolatedAsyncioTestCase):
    """Tests for the memory extraction pipeline."""

    @patch("utils.providers.generate_text")
    @patch("utils.conversation.build_conversation_context")
    async def test_extract_memories_from_conversation(self, mock_build_context, mock_generate):
        # Mock conversation history
        mock_build_context.return_value = (
            "User: Hey, let's play chess next week.\n"
            "Assistant: Sure, I'd love to!\n"
            "User: It's a promise then.\n"
            "Assistant: It's a promise."
        )
        
        # Mock LLM response
        mock_generate.return_value = json.dumps([
            {
                "type": "PROMISE",
                "content": "We promised to play chess next week.",
                "importance": 0.9,
                "source_message_ids": [1, 2, 3, 4]
            }
        ])
        
        from utils.character_memory import extract_memories_from_conversation, MemoryType
        
        memories = await extract_memories_from_conversation(
            guild_id=1,
            channel_id=100,
            user_id=2,
            persona_id="chisato",
            provider_name="gemini",
            model_name="gemini-pro",
        )
        
        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0].memory_type, MemoryType.PROMISE)
        self.assertEqual(memories[0].content, "We promised to play chess next week.")
        self.assertEqual(memories[0].importance, 0.9)
        self.assertEqual(memories[0].guild_id, 1)
        self.assertEqual(memories[0].user_id, 2)
        self.assertEqual(memories[0].persona_id, "chisato")

    @patch("utils.providers.generate_text")
    @patch("utils.conversation.build_conversation_context")
    async def test_extract_memories_empty_response(self, mock_build_context, mock_generate):
        mock_build_context.return_value = "User: Hello\nAssistant: Hi"
        mock_generate.return_value = "[]"
        
        from utils.character_memory import extract_memories_from_conversation
        
        memories = await extract_memories_from_conversation(
            guild_id=1,
            channel_id=100,
            user_id=2,
            persona_id="chisato",
            provider_name="gemini",
            model_name="gemini-pro",
        )
        
        self.assertEqual(len(memories), 0)

    @patch("utils.providers.generate_text")
    @patch("utils.conversation.build_conversation_context")
    async def test_extract_memories_filters_low_importance(self, mock_build_context, mock_generate):
        mock_build_context.return_value = "Some conversation"
        mock_generate.return_value = json.dumps([
            {"type": "PROMISE", "content": "High importance", "importance": 0.9, "source_message_ids": []},
            {"type": "SHARED_EXPERIENCE", "content": "Low importance", "importance": 0.1, "source_message_ids": []},
        ])
        
        from utils.character_memory import extract_memories_from_conversation
        
        memories = await extract_memories_from_conversation(
            guild_id=1,
            channel_id=100,
            user_id=2,
            persona_id="chisato",
            provider_name="gemini",
            model_name="gemini-pro",
        )
        
        # MIN_IMPORTANCE is 0.3, so only the first should pass
        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0].content, "High importance")


class TestEnforceMemoryBudget(unittest.IsolatedAsyncioTestCase):
    """Tests for memory budget enforcement."""

    async def asyncSetUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_db = os.path.join(self.temp_dir, "test_character_memory_budget.db")
        
        os.environ["CHARACTER_MEMORY_FILE_PATH"] = self.test_db
        os.environ["CHARACTER_MEMORY_MAX_MEMORIES"] = "3"
        
        import importlib
        import utils.character_memory
        importlib.reload(utils.character_memory)
        from utils.character_memory import init_db
        await init_db()

    async def asyncTearDown(self):
        import importlib
        os.environ["CHARACTER_MEMORY_FILE_PATH"] = "./character_memory.db"
        if "CHARACTER_MEMORY_MAX_MEMORIES" in os.environ:
            del os.environ["CHARACTER_MEMORY_MAX_MEMORIES"]
        import utils.character_memory
        importlib.reload(utils.character_memory)
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    async def test_enforce_budget_removes_lowest_importance(self):
        from utils.character_memory import CharacterMemory, MemoryType, store_memory, enforce_memory_budget, get_memories
        # Store 5 memories with varying importance
        for i, imp in enumerate([0.9, 0.7, 0.5, 0.3, 0.1]):
            mem = CharacterMemory(
                memory_id=f"mem-{i}",
                guild_id=1,
                user_id=2,
                persona_id="chisato",
                memory_type=MemoryType.SHARED_EXPERIENCE,
                content=f"Memory {i}",
                importance=imp,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            await store_memory(mem)
        
        # Budget is 3, so 2 lowest should be removed
        removed = await enforce_memory_budget(1, 2, "chisato", max_memories=3)
        self.assertEqual(removed, 2)
        
        memories = await get_memories(1, 2, "chisato")
        self.assertEqual(len(memories), 3)
        # Should keep the 3 highest importance
        self.assertEqual(memories[0].importance, 0.9)
        self.assertEqual(memories[1].importance, 0.7)
        self.assertEqual(memories[2].importance, 0.5)

    async def test_enforce_budget_noop_when_under_limit(self):
        from utils.character_memory import CharacterMemory, MemoryType, store_memory, enforce_memory_budget, get_memories
        for i in range(2):
            mem = CharacterMemory(
                memory_id=f"mem-{i}",
                guild_id=1,
                user_id=2,
                persona_id="chisato",
                memory_type=MemoryType.SHARED_EXPERIENCE,
                content=f"Memory {i}",
                importance=0.5,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            await store_memory(mem)
        
        removed = await enforce_memory_budget(1, 2, "chisato", max_memories=5)
        self.assertEqual(removed, 0)
        
        memories = await get_memories(1, 2, "chisato")
        self.assertEqual(len(memories), 2)


if __name__ == "__main__":
    unittest.main()
