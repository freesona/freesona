"""Tests for anniversary database migration and persistence."""

import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import aiosqlite

from utils import anniversaries_db


class TestAnniversariesDatabase(unittest.IsolatedAsyncioTestCase):
    """Verify legacy compatibility and the expanded database behavior."""

    async def asyncSetUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.database = str(Path(self.tempdir.name) / "anniversaries.db")
        self.db_path_patcher = patch.object(
            anniversaries_db, "DB_PATH", self.database
        )
        self.db_path_patcher.start()

    async def asyncTearDown(self) -> None:
        self.db_path_patcher.stop()
        self.tempdir.cleanup()

    async def test_migrates_legacy_schema_and_normalizes_dates(self):
        async with aiosqlite.connect(self.database) as db:
            await db.execute("""
                CREATE TABLE anniversaries (
                    id TEXT PRIMARY KEY,
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    subtitle TEXT NOT NULL,
                    anniversary_date TEXT NOT NULL,
                    thumbnail_url TEXT,
                    reference_url TEXT,
                    calendar_event_id TEXT,
                    claimed_at TEXT NOT NULL
                )
            """)
            await db.execute(
                "INSERT INTO anniversaries "
                "(id, guild_id, user_id, title, subtitle, "
                "anniversary_date, claimed_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("legacy", 1, 2, "Old film", "2008", "2008-6-6", "2020-01-01"),
            )
            await db.commit()

        await anniversaries_db.init_db()

        entry = await anniversaries_db.get_entry_by_id("legacy")
        assert entry is not None
        self.assertEqual(entry["anniversary_date"], "2008-06-06")
        self.assertEqual(entry["type"], "film")
        self.assertEqual(entry["is_custom"], 0)

    async def test_insert_search_update_settings_and_stats(self):
        await anniversaries_db.init_db()
        await anniversaries_db.insert_entry(
            {
                "id": "game-1",
                "guild_id": 1,
                "user_id": 2,
                "title": "100% Game",
                "subtitle": "PC",
                "anniversary_date": "2010-2-3",
                "type": "game",
                "is_custom": True,
            }
        )

        found = await anniversaries_db.check_duplicate(
            1, "100% game", entry_type="game"
        )
        assert found is not None
        self.assertEqual(found["id"], "game-1")
        self.assertEqual(
            [
                entry["id"]
                for entry in await anniversaries_db.search_entries(
                    1, "100%", None
                )
            ],
            ["game-1"],
        )
        self.assertEqual(
            await anniversaries_db.search_entries(1, "100x", None), []
        )

        updated = await anniversaries_db.update_entry(
            "game-1", {"anniversary_date": "2010-02-4"}
        )
        assert updated is not None
        self.assertEqual(updated["anniversary_date"], "2010-02-04")
        self.assertEqual(
            await anniversaries_db.get_entry_by_id("game-1"), updated
        )
        with self.assertRaises(ValueError):
            await anniversaries_db.update_entry("game-1", {"guild_id": 3})

        await anniversaries_db.set_guild_setting(1, digest_enabled=1)
        await anniversaries_db.set_user_setting(2, notice_days=3)
        self.assertEqual(
            (await anniversaries_db.get_guild_settings(1))["digest_enabled"],
            1,
        )
        self.assertEqual(
            (await anniversaries_db.get_user_settings(2))["notice_days"],
            3,
        )
        stats = await anniversaries_db.get_stats(1)
        self.assertEqual(stats["total"], 1)
        self.assertEqual(stats["custom"], 1)
        self.assertEqual(stats["by_type"], {"game": 1})

    async def test_leap_day_is_returned_on_march_first_in_non_leap_year(self):
        await anniversaries_db.init_db()
        await anniversaries_db.insert_entry(
            {
                "id": "leap-day",
                "guild_id": 1,
                "user_id": 2,
                "title": "Leap Day",
                "subtitle": "Special",
                "anniversary_date": "2000-02-29",
            }
        )

        entries = await anniversaries_db.get_todays_entries(
            1, date(2025, 3, 1)
        )
        self.assertEqual([entry["id"] for entry in entries], ["leap-day"])
