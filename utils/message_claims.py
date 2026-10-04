"""Durable SQLite leases for coordinating message processing instances."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import aiosqlite


@dataclass(frozen=True)
class MessageClaim:
    """A lease held by an instance while processing a message."""

    claim_key: str
    owner: str
    claimed_at: float
    expires_at: float


class MessageClaimRepository:
    """Store and atomically coordinate message-processing leases in SQLite."""

    def __init__(self, database_path: str, lease_seconds: float = 300.0) -> None:
        """Create a repository for ``database_path`` with the given lease length."""
        self.database_path = database_path
        self.lease_seconds = lease_seconds

    async def initialize(self) -> None:
        """Create the claim table when it does not already exist."""
        parent = Path(self.database_path).parent
        if str(parent) != ".":
            parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.database_path) as db:
            await db.execute(
                """CREATE TABLE IF NOT EXISTS message_claims (
                    claim_key TEXT PRIMARY KEY,
                    owner TEXT NOT NULL,
                    claimed_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    completed_at REAL
                )"""
            )
            await db.commit()

    async def acquire(self, claim_key: str, owner: str) -> MessageClaim | None:
        """Atomically acquire a free or expired lease, or return ``None``."""
        now = time.time()
        expires_at = now + self.lease_seconds
        async with aiosqlite.connect(self.database_path) as db:
            await db.execute("BEGIN IMMEDIATE")
            cursor = await db.execute(
                """INSERT INTO message_claims
                    (claim_key, owner, claimed_at, expires_at, completed_at)
                    VALUES (?, ?, ?, ?, NULL)
                    ON CONFLICT(claim_key) DO UPDATE SET
                        owner = excluded.owner,
                        claimed_at = excluded.claimed_at,
                        expires_at = excluded.expires_at,
                        completed_at = NULL
                    WHERE message_claims.expires_at <= ?
                      AND message_claims.completed_at IS NULL""",
                (claim_key, owner, now, expires_at, now),
            )
            changed = cursor.rowcount
            await db.commit()
            if changed != 1:
                return None
        return MessageClaim(claim_key, owner, now, expires_at)

    async def complete(self, claim_key: str, owner: str) -> bool:
        """Mark an active lease complete when it is owned by ``owner``."""
        async with aiosqlite.connect(self.database_path) as db:
            cursor = await db.execute(
                """UPDATE message_claims SET completed_at = ?
                   WHERE claim_key = ? AND owner = ? AND completed_at IS NULL""",
                (time.time(), claim_key, owner),
            )
            await db.commit()
            return cursor.rowcount == 1

    async def release(self, claim_key: str, owner: str) -> bool:
        """Release an active lease when it is owned by ``owner``."""
        async with aiosqlite.connect(self.database_path) as db:
            cursor = await db.execute(
                """DELETE FROM message_claims
                   WHERE claim_key = ? AND owner = ? AND completed_at IS NULL""",
                (claim_key, owner),
            )
            await db.commit()
            return cursor.rowcount == 1

    async def cleanup(self, before: float | None = None) -> int:
        """Delete completed and expired claims, returning the number removed."""
        cutoff = time.time() if before is None else before
        async with aiosqlite.connect(self.database_path) as db:
            cursor = await db.execute(
                """DELETE FROM message_claims
                   WHERE (completed_at IS NOT NULL AND completed_at <= ?)
                      OR (completed_at IS NULL AND expires_at <= ?)""",
                (cutoff, cutoff),
            )
            await db.commit()
            return cursor.rowcount
