#!/usr/bin/env python3
# tests/test_memory_interface.py: Unit tests for memory interface.
import unittest

from utils.memory_interface import FakeMemoryStore, SQLiteMemoryStore


class TestFakeMemoryStore(unittest.IsolatedAsyncioTestCase):
    """Tests for the in-memory fake memory store."""

    async def asyncSetUp(self):
        self.store = FakeMemoryStore()

    async def test_store_and_get_facts(self):
        await self.store.store_fact(
            guild_id=1,
            user_id=100,
            content="User likes cats",
            importance=0.8,
            timestamp="2026-01-01T00:00:00Z",
            message_id="1",
            channel_id="2",
        )
        await self.store.store_fact(
            guild_id=1,
            user_id=100,
            content="User dislikes dogs",
            importance=0.5,
            timestamp="2026-01-02T00:00:00Z",
            message_id="2",
            channel_id="2",
        )
        facts = await self.store.get_facts(guild_id=1, user_id=100)
        self.assertEqual(len(facts), 2)
        self.assertEqual(facts[0]["content"], "User likes cats")
        self.assertEqual(facts[1]["content"], "User dislikes dogs")

    async def test_get_facts_respects_limit(self):
        for i in range(5):
            await self.store.store_fact(
                guild_id=1,
                user_id=100,
                content=f"Fact {i}",
                importance=float(i) / 10.0,
                timestamp="2026-01-01T00:00:00Z",
                message_id=str(i),
                channel_id="2",
            )
        facts = await self.store.get_facts(guild_id=1, user_id=100, limit=2)
        self.assertEqual(len(facts), 2)
        self.assertEqual(facts[0]["content"], "Fact 4")

    async def test_get_facts_isolated_by_user(self):
        await self.store.store_fact(
            guild_id=1,
            user_id=100,
            content="User A fact",
            importance=0.9,
            timestamp="2026-01-01T00:00:00Z",
            message_id="1",
            channel_id="2",
        )
        await self.store.store_fact(
            guild_id=1,
            user_id=200,
            content="User B fact",
            importance=0.9,
            timestamp="2026-01-01T00:00:00Z",
            message_id="2",
            channel_id="2",
        )
        facts = await self.store.get_facts(guild_id=1, user_id=100)
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0]["content"], "User A fact")

    async def test_clear_facts_specific_user(self):
        await self.store.store_fact(
            guild_id=1,
            user_id=100,
            content="User A fact",
            importance=0.9,
            timestamp="2026-01-01T00:00:00Z",
            message_id="1",
            channel_id="2",
        )
        await self.store.store_fact(
            guild_id=1,
            user_id=200,
            content="User B fact",
            importance=0.9,
            timestamp="2026-01-01T00:00:00Z",
            message_id="2",
            channel_id="2",
        )
        deleted = await self.store.clear_facts(guild_id=1, user_id=100)
        self.assertEqual(deleted, 1)
        facts = await self.store.get_facts(guild_id=1, user_id=100)
        self.assertEqual(len(facts), 0)
        facts = await self.store.get_facts(guild_id=1, user_id=200)
        self.assertEqual(len(facts), 1)

    async def test_clear_facts_all_users(self):
        await self.store.store_fact(
            guild_id=1,
            user_id=100,
            content="User A fact",
            importance=0.9,
            timestamp="2026-01-01T00:00:00Z",
            message_id="1",
            channel_id="2",
        )
        await self.store.store_fact(
            guild_id=1,
            user_id=200,
            content="User B fact",
            importance=0.9,
            timestamp="2026-01-01T00:00:00Z",
            message_id="2",
            channel_id="2",
        )
        deleted = await self.store.clear_facts(guild_id=1)
        self.assertEqual(deleted, 2)
        facts = await self.store.get_facts(guild_id=1, user_id=100)
        self.assertEqual(len(facts), 0)


class TestSQLiteMemoryStore(unittest.TestCase):
    """Tests for the SQLite memory store adapter."""

    def test_constructor_stores_db_path(self):
        store = SQLiteMemoryStore(db_path="./test.db")
        self.assertEqual(store._db_path, "./test.db")

    def test_constructor_defaults_to_memory_db(self):
        store = SQLiteMemoryStore()
        self.assertEqual(store._db_path, "./memory.db")
