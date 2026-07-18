import os
import sys
import unittest
import tempfile
import aiosqlite

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils.memory import (
    init_db,
    get_user_facts_prompt,
    inject_user_memory,
    extract_and_store_fact,
    run_migration,
    MAX_FACTS_PER_USER,
    MIN_IMPORTANCE,
)


class UserFactsMemoryTests(unittest.IsolatedAsyncioTestCase):
    """Tests for long-term user facts memory (SQLite)."""

    async def asyncSetUp(self):
        # Use a temporary database for each test
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        os.environ["MEMORY_FILE_PATH"] = self.temp_db.name
        # Re-import to pick up new path
        import importlib
        import utils.memory
        importlib.reload(utils.memory)
        from utils.memory import init_db
        await init_db()

    async def asyncTearDown(self):
        if os.path.exists(self.temp_db.name):
            os.unlink(self.temp_db.name)

    async def test_store_and_retrieve_user_facts(self):
        from utils.memory import get_user_facts_prompt
        guild_id = 1
        user_id = 100
        display_name = "TestUser"

        # Store some facts directly
        async with aiosqlite.connect(self.temp_db.name) as db:
            await db.execute(
                "INSERT INTO user_facts (guild_id, user_id, content, importance, timestamp, message_id, channel_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (str(guild_id), str(user_id), "User likes cats", 0.8, "2024-01-01T00:00:00", "msg1", "1000")
            )
            await db.execute(
                "INSERT INTO user_facts (guild_id, user_id, content, importance, timestamp, message_id, channel_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (str(guild_id), str(user_id), "User hates dogs", 0.5, "2024-01-02T00:00:00", "msg2", "1001")
            )
            await db.commit()

        prompt = await get_user_facts_prompt(guild_id, user_id, display_name)
        self.assertIn("User likes cats", prompt)
        self.assertIn("User hates dogs", prompt)
        self.assertIn("TestUser", prompt)

    async def test_empty_facts_returns_default_message(self):
        from utils.memory import get_user_facts_prompt
        guild_id = 1
        user_id = 999
        display_name = "NoFactsUser"

        prompt = await get_user_facts_prompt(guild_id, user_id, display_name)
        self.assertIn("NoFactsUser", prompt)
        self.assertIn("None. You have no record of any past interactions", prompt)

    async def test_fact_limit_enforced(self):
        # The fact limit is enforced at insertion time (in extract_and_store_fact),
        # not at query time. get_user_facts_prompt returns all facts ordered by importance.
        # We test that the limit works by inserting via the extraction function.
        from utils.memory import extract_and_store_fact
        
        guild_id = 1
        user_id = 200
        display_name = "LimitUser"
        
        # Create a mock client for fact extraction
        class MockClient:
            pass
        
        mock_client = MockClient()
        
        # Mock the generate_text function to return controlled responses
        import utils.providers
        original_generate = utils.providers.generate_text
        
        call_count = [0]
        async def mock_generate_text(prompt, **kwargs):
            call_count[0] += 1
            if call_count[0] <= 25:
                return '{"content": "Fact ' + str(call_count[0]) + '", "importance": ' + str(0.5 + call_count[0] * 0.01) + '}'
            return 'null'
        
        utils.providers.generate_text = mock_generate_text
        
        try:
            # Extract and store 25 facts
            for i in range(25):
                await extract_and_store_fact(
                    message_content=f"Message {i}",
                    display_name=display_name,
                    guild_id=guild_id,
                    user_id=user_id,
                    message_id=i,
                    channel_id=1000,
                    client=mock_client,
                    model_name="test-model",
                    provider_name="gemini",
                )
            
            # Check that only MAX_FACTS_PER_USER facts are stored
            from utils.memory import get_user_facts_prompt
            prompt = await get_user_facts_prompt(guild_id, user_id, display_name)
            lines = prompt.split("\n")
            fact_lines = [l for l in lines if l.startswith("- ")]
            self.assertLessEqual(len(fact_lines), MAX_FACTS_PER_USER)
        finally:
            utils.providers.generate_text = original_generate

    async def test_importance_threshold(self):
        # The importance threshold is enforced at insertion time (in extract_and_store_fact),
        # not at query time. Facts with importance < MIN_IMPORTANCE are never stored.
        from utils.memory import extract_and_store_fact
        
        guild_id = 1
        user_id = 300
        display_name = "ThresholdUser"
        
        # Use provider_name="openai" to avoid the gemini-specific path requiring a client
        import utils.providers
        original_generate = utils.providers.generate_text
        
        call_count = [0]
        def mock_generate_text(prompt, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return '{"content": "High importance fact", "importance": 0.9}'
            elif call_count[0] == 2:
                return '{"content": "Low importance fact", "importance": 0.1}'
            return 'null'
        
        # We need to monkey-patch at the module level where it's imported
        # The function is imported as `from utils.providers import generate_text` in memory.py
        utils.providers.generate_text = mock_generate_text
        
        try:
            # Extract and store 2 facts - one high importance, one low importance
            await extract_and_store_fact(
                message_content="Message 1",
                display_name=display_name,
                guild_id=guild_id,
                user_id=user_id,
                message_id=1,
                channel_id=1000,
                client=None,  # No client needed for non-gemini path
                model_name="test-model",
                provider_name="openai",
            )
            await extract_and_store_fact(
                message_content="Message 2",
                display_name=display_name,
                guild_id=guild_id,
                user_id=user_id,
                message_id=2,
                channel_id=1000,
                client=None,
                model_name="test-model",
                provider_name="openai",
            )
            
            # Check that only the high importance fact was stored
            from utils.memory import get_user_facts_prompt
            prompt = await get_user_facts_prompt(guild_id, user_id, display_name)
            self.assertIn("High importance fact", prompt)
            self.assertNotIn("Low importance fact", prompt)  # Below MIN_IMPORTANCE (0.3)
        finally:
            utils.providers.generate_text = original_generate

    async def test_inject_user_memory_alias(self):
        from utils.memory import inject_user_memory, get_user_facts_prompt
        guild_id = 1
        user_id = 400
        display_name = "AliasUser"

        async with aiosqlite.connect(self.temp_db.name) as db:
            await db.execute(
                "INSERT INTO user_facts (guild_id, user_id, content, importance, timestamp, message_id, channel_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (str(guild_id), str(user_id), "Test fact", 0.5, "2024-01-01T00:00:00", "msg1", "1000")
            )
            await db.commit()

        result = await inject_user_memory(guild_id, user_id, display_name)
        expected = await get_user_facts_prompt(guild_id, user_id, display_name)
        self.assertEqual(result, expected)


if __name__ == "__main__":
    unittest.main()
