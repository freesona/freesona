#!/usr/bin/env python3
# utils/memory_interface.py: Long-term memory interface and SQLite adapter.
# Keeps SQLite types out of the generation and listener layers.


from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class MemoryStore(Protocol):
    """Interface for long-term user fact storage.

    Implementations may be backed by SQLite or a fake for tests.
    """

    async def store_fact(
        self,
        *,
        guild_id: int,
        user_id: int,
        content: str,
        importance: float,
        timestamp: str,
        message_id: str,
        channel_id: str,
    ) -> None:
        """Store a user fact."""

        ...

    async def get_facts(
        self,
        *,
        guild_id: int,
        user_id: int,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Retrieve user facts ordered by importance descending."""

        ...

    async def clear_facts(
        self,
        *,
        guild_id: int,
        user_id: int | None = None,
    ) -> int:
        """Clear user facts. Returns number of facts deleted."""

        ...


class SQLiteMemoryStore:
    """SQLite-backed memory store implementation."""

    def __init__(self, db_path: str = "./memory.db") -> None:
        self._db_path = db_path

    async def store_fact(
        self,
        *,
        guild_id: int,
        user_id: int,
        content: str,
        importance: float,
        timestamp: str,
        message_id: str,
        channel_id: str,
    ) -> None:
        import aiosqlite

        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                (
                    "INSERT OR IGNORE INTO user_facts "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)"
                ),
                (
                    str(guild_id),
                    str(user_id),
                    content,
                    importance,
                    timestamp,
                    str(message_id),
                    str(channel_id),
                ),
            )
            await db.execute(
                """
                DELETE FROM user_facts
                WHERE guild_id = ? AND user_id = ? AND message_id NOT IN (
                    SELECT message_id FROM user_facts
                    WHERE guild_id = ? AND user_id = ?
                    ORDER BY importance DESC LIMIT ?
                )
                """,
                (
                    str(guild_id),
                    str(user_id),
                    str(guild_id),
                    str(user_id),
                    20,
                ),
            )
            await db.commit()

    async def get_facts(
        self,
        *,
        guild_id: int,
        user_id: int,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        import aiosqlite

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT content, importance FROM user_facts "
                "WHERE guild_id = ? AND user_id = ? "
                "ORDER BY importance DESC LIMIT ?",
                (str(guild_id), str(user_id), limit),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def clear_facts(
        self,
        *,
        guild_id: int,
        user_id: int | None = None,
    ) -> int:
        import aiosqlite

        async with aiosqlite.connect(self._db_path) as db:
            if user_id is not None:
                cursor = await db.execute(
                    "DELETE FROM user_facts WHERE guild_id = ? AND user_id = ?",
                    (str(guild_id), str(user_id)),
                )
            else:
                cursor = await db.execute(
                    "DELETE FROM user_facts WHERE guild_id = ?",
                    (str(guild_id),),
                )
            await db.commit()
            return cursor.rowcount


class FakeMemoryStore:
    """In-memory fake memory store for testing."""

    def __init__(self) -> None:
        self._facts: list[dict[str, Any]] = []

    async def store_fact(
        self,
        *,
        guild_id: int,
        user_id: int,
        content: str,
        importance: float,
        timestamp: str,
        message_id: str,
        channel_id: str,
    ) -> None:
        self._facts.append(
            {
                "guild_id": guild_id,
                "user_id": user_id,
                "content": content,
                "importance": importance,
                "timestamp": timestamp,
                "message_id": message_id,
                "channel_id": channel_id,
            }
        )

    async def get_facts(
        self,
        *,
        guild_id: int,
        user_id: int,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        facts = [
            f
            for f in self._facts
            if f["guild_id"] == guild_id and f["user_id"] == user_id
        ]
        facts.sort(key=lambda f: f["importance"], reverse=True)
        return facts[:limit]

    async def clear_facts(
        self,
        *,
        guild_id: int,
        user_id: int | None = None,
    ) -> int:
        if user_id is not None:
            before = len(self._facts)
            self._facts = [
                f
                for f in self._facts
                if not (f["guild_id"] == guild_id and f["user_id"] == user_id)
            ]
        else:
            before = len(self._facts)
            self._facts = [
                f for f in self._facts if f["guild_id"] != guild_id
            ]
        return before - len(self._facts)
