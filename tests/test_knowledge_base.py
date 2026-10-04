"""Tests for structured Knowledge Base contracts and persistence."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from utils.knowledge_base import (
    KnowledgeBaseService,
    canonicalize_entry,
    stable_entry_id,
    validate_entry,
)


def entry(**overrides):
    """Return a valid sample entry."""
    value = {
        "persona": "Chisato",
        "source": "Episode 06",
        "source_type": "anime",
        "entry_type": "dialogue",
        "topics": ["Combat", "friendship"],
        "content": "  A useful fact.  ",
    }
    value.update(overrides)
    return value


class TestKnowledgeBase(unittest.IsolatedAsyncioTestCase):
    """Verify validation, deterministic identity, and durable ingestion."""

    async def asyncSetUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.service = KnowledgeBaseService(
            str(Path(self.tempdir.name) / "knowledge.db"),
            indexer=lambda *args, **kwargs: "indexed",
        )
        await self.service.initialize()

    async def asyncTearDown(self):
        self.tempdir.cleanup()

    def test_canonicalization_is_deterministic(self):
        first = canonicalize_entry(entry())
        second = canonicalize_entry(entry(topics=["friendship", "combat"]))
        self.assertEqual(first, second)
        self.assertEqual(stable_entry_id(first), stable_entry_id(second))

    def test_invalid_entries_are_rejected(self):
        with self.assertRaises(ValueError):
            validate_entry(entry(entry_type="unknown"))
        with self.assertRaises(ValueError):
            validate_entry(entry(content=""))

    async def test_ingestion_is_idempotent_and_survives_index_failure(self):
        service = KnowledgeBaseService(
            self.service.database_path,
            indexer=lambda *args, **kwargs: (_ for _ in ()).throw(
                RuntimeError("offline")
            ),
        )
        first = await service.ingest(entry())
        second = await service.ingest(entry())
        self.assertEqual(first.id, second.id)
        self.assertEqual(len(await service.list_entries()), 1)

    async def test_optional_metadata_is_persisted(self):
        ingested = await self.service.ingest(entry(scene="Cafe", tags=["important"]))
        stored = await self.service.list_entries()
        self.assertEqual(stored, [ingested])
        self.assertEqual(ingested.metadata, {"scene": "Cafe", "tags": ["important"]})

    async def test_delete_removes_sqlite_record_when_chroma_delete_fails(self):
        ingested = await self.service.ingest(entry())

        with patch(
            "utils.chroma.delete_knowledge", side_effect=RuntimeError("offline")
        ):
            deleted = await self.service.delete_entry(ingested.id)

        self.assertTrue(deleted)
        self.assertEqual(await self.service.list_entries(), [])
