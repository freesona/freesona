#!/usr/bin/env python3
# tests/test_kb_interface.py: Unit tests for knowledge base interface.
import unittest

from utils.kb_interface import ChromaKnowledgeBase, FakeKnowledgeBase


class TestFakeKnowledgeBase(unittest.TestCase):
    """Tests for the in-memory fake knowledge base."""

    def test_query_returns_all_entries(self):
        kb = FakeKnowledgeBase(
            [
                {"document": "Entry 1", "metadata": {}, "distance": 0.1},
                {"document": "Entry 2", "metadata": {}, "distance": 0.2},
            ]
        )
        results = kb.query("test", limit=5)
        self.assertEqual(len(results), 2)

    def test_query_respects_limit(self):
        kb = FakeKnowledgeBase(
            [
                {"document": f"Entry {i}", "metadata": {}, "distance": 0.1}
                for i in range(5)
            ]
        )
        results = kb.query("test", limit=2)
        self.assertEqual(len(results), 2)

    def test_query_filters_by_persona(self):
        kb = FakeKnowledgeBase(
            [
                {
                    "document": "Persona A entry",
                    "metadata": {},
                    "persona": "persona-a",
                },
                {
                    "document": "Persona B entry",
                    "metadata": {},
                    "persona": "persona-b",
                },
            ]
        )
        results = kb.query("test", persona="persona-a")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["document"], "Persona A entry")

    def test_query_empty_returns_empty(self):
        kb = FakeKnowledgeBase()
        results = kb.query("test")
        self.assertEqual(results, [])


class TestChromaKnowledgeBase(unittest.TestCase):
    """Tests for the ChromaDB knowledge base adapter."""

    def test_constructor_stores_collection_name(self):
        kb = ChromaKnowledgeBase(collection_name="my-collection")
        self.assertEqual(kb._collection_name, "my-collection")

    def test_constructor_defaults_to_none(self):
        kb = ChromaKnowledgeBase()
        self.assertIsNone(kb._collection_name)
