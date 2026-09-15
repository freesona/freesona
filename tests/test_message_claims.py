"""Tests for durable message-processing leases."""

import asyncio
import tempfile
import unittest
from pathlib import Path

from utils.message_claims import MessageClaimRepository


class TestMessageClaimRepository(unittest.IsolatedAsyncioTestCase):
    """Verify ownership, expiry, completion, and release semantics."""

    async def asyncSetUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.database = str(Path(self.tempdir.name) / "claims.db")
        self.repository = MessageClaimRepository(self.database, lease_seconds=0.05)
        await self.repository.initialize()

    async def asyncTearDown(self) -> None:
        self.tempdir.cleanup()

    async def test_only_one_concurrent_owner(self) -> None:
        results = await asyncio.gather(
            self.repository.acquire("message", "one"),
            self.repository.acquire("message", "two"),
        )
        self.assertEqual(sum(result is not None for result in results), 1)

    async def test_expired_claim_can_be_reclaimed(self) -> None:
        first = await self.repository.acquire("message", "one")
        self.assertIsNotNone(first)
        await asyncio.sleep(0.06)
        second = await self.repository.acquire("message", "two")
        self.assertIsNotNone(second)
        self.assertEqual(second.owner, "two")

    async def test_completion_and_release_require_owner(self) -> None:
        claim = await self.repository.acquire("message", "one")
        self.assertIsNotNone(claim)
        self.assertFalse(await self.repository.complete("message", "two"))
        self.assertTrue(await self.repository.complete("message", "one"))
        self.assertIsNone(await self.repository.acquire("message", "two"))

        released = await self.repository.acquire("other", "one")
        self.assertIsNotNone(released)
        self.assertTrue(await self.repository.release("other", "one"))
        self.assertIsNotNone(await self.repository.acquire("other", "two"))

    async def test_completed_claim_cannot_be_released_or_reclaimed(self) -> None:
        claim = await self.repository.acquire("message", "one")
        self.assertIsNotNone(claim)
        self.assertTrue(await self.repository.complete("message", "one"))
        self.assertFalse(await self.repository.release("message", "one"))
        await asyncio.sleep(0.06)
        self.assertIsNone(await self.repository.acquire("message", "two"))

    async def test_cleanup_removes_completed_and_expired_active_claims(self) -> None:
        completed = await self.repository.acquire("completed", "one")
        active = await self.repository.acquire("active", "one")
        self.assertIsNotNone(completed)
        self.assertIsNotNone(active)
        self.assertTrue(await self.repository.complete("completed", "one"))
        await asyncio.sleep(0.06)
        self.assertEqual(await self.repository.cleanup(), 2)
        self.assertIsNotNone(await self.repository.acquire("completed", "two"))
        self.assertIsNotNone(await self.repository.acquire("active", "two"))