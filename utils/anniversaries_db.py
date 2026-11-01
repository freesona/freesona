# utils/anniversaries_db.py: Generic anniversary tracking DB for Freesona.
# Stores user-claimed anniversary entries with optional calendar sync support.
# Compatible with cogs/fun/albums.py and any future anniversary-type features.

from __future__ import annotations

import calendar
import logging
import os
import re
from collections.abc import Sequence
from datetime import date, datetime, timezone
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)

DB_PATH = os.environ.get("ANNIVERSARIES_FILE_PATH", "anniversaries.db")

VALID_TYPES = ("music", "game", "film", "series", "episode", "general")

# Used only to backfill the `type` column for rows created before it existed.
_YEAR_RE = re.compile(r"\d{4}(?:[–\-]\d{0,4})?")
_PLATFORM_RE = re.compile(
    r"(PC|Mac|macOS|Linux|iOS|Android|Web|Nintendo|PlayStation|PS\d?|PSP|Vita|Xbox|"
    r"Wii|Switch|Steam|SEGA|Sega|Atari|Commodore|Neo Geo|Dreamcast|GameCube|"
    r"Game Boy|"
    r"Apple|Classic Macintosh|Genesis|NES|SNES|3DO|Jaguar)\b.*",
    re.IGNORECASE,
)


_LOOSE_DATE_RE = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")


def normalize_iso_date(value: str | None) -> str | None:
    """Return a zero-padded date for loose input, or None if it is not valid.

    Older versions saved dates as typed (e.g. "2008-6-6"), which breaks
    month/day matching and calendar sync.
    """
    match = _LOOSE_DATE_RE.fullmatch((value or "").strip())
    if not match:
        return None
    year, month, day = (int(g) for g in match.groups())
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def infer_type_from_subtitle(subtitle: str | None) -> str:
    """Guess a legacy entry type from its subtitle."""
    s = (subtitle or "").strip()
    if _YEAR_RE.fullmatch(s):
        return "film"
    if _PLATFORM_RE.fullmatch(s):
        return "game"
    return "music"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _fetch_all(sql: str, params: Sequence[Any] = ()) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(sql, params) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def _fetch_one(sql: str, params: Sequence[Any] = ()) -> dict | None:
    rows = await _fetch_all(sql, params)
    return rows[0] if rows else None


def _escape_like(text: str) -> str:
    """Escape LIKE wildcards so user input is matched literally."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


async def init_db() -> None:
    """Create the anniversaries table if needed and migrate older databases."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS anniversaries (
                id                TEXT PRIMARY KEY,
                guild_id          INTEGER NOT NULL,
                user_id           INTEGER NOT NULL,
                title             TEXT NOT NULL,
                subtitle          TEXT NOT NULL,
                anniversary_date  TEXT NOT NULL,
                thumbnail_url     TEXT,
                reference_url     TEXT,
                calendar_event_id TEXT,
                claimed_at        TEXT NOT NULL,
                type              TEXT NOT NULL DEFAULT 'music',
                is_custom         INTEGER NOT NULL DEFAULT 0
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS bot_state (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id            INTEGER PRIMARY KEY,
                reminder_channel_id INTEGER,
                digest_enabled      INTEGER NOT NULL DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id     INTEGER PRIMARY KEY,
                dm_enabled  INTEGER NOT NULL DEFAULT 1,
                notice_days INTEGER NOT NULL DEFAULT 1
            )
        """)

        # Migration: databases created before the `type` column existed.
        async with db.execute("PRAGMA table_info(anniversaries)") as cur:
            columns = {row[1] for row in await cur.fetchall()}
        if "type" not in columns:
            await db.execute(
                "ALTER TABLE anniversaries "
                "ADD COLUMN type TEXT NOT NULL DEFAULT 'music'"
            )
            async with db.execute(
                "SELECT id, subtitle FROM anniversaries"
            ) as cur:
                legacy = await cur.fetchall()
            for entry_id, subtitle in legacy:
                guessed = infer_type_from_subtitle(subtitle)
                if guessed != "music":
                    await db.execute(
                        "UPDATE anniversaries SET type = ? WHERE id = ?",
                        (guessed, entry_id),
                    )

        # Migration: flag for user-created (non-API) claims.
        if "is_custom" not in columns:
            await db.execute(
                "ALTER TABLE anniversaries "
                "ADD COLUMN is_custom INTEGER NOT NULL DEFAULT 0"
            )

        # Migration: rewrite dates stored as typed ("2008-6-6") to
        # YYYY-MM-DD. Only rows that don't already match are touched.
        async with db.execute(
            "SELECT id, anniversary_date FROM anniversaries "
            "WHERE anniversary_date NOT GLOB "
            "'[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'"
        ) as cur:
            bad_dates = await cur.fetchall()
        fixed_count = 0
        for entry_id, raw in bad_dates:
            fixed = normalize_iso_date(raw)
            if fixed:
                await db.execute(
                    "UPDATE anniversaries SET anniversary_date = ? "
                    "WHERE id = ?",
                    (fixed, entry_id),
                )
                fixed_count += 1
            else:
                logger.warning(
                    "Claim %s has an unrecognised date %r; fix it by hand",
                    entry_id,
                    raw,
                )
        if fixed_count:
            logger.info(
                "Normalized %d claim date(s) to YYYY-MM-DD", fixed_count
            )

        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_anniv_guild_user "
            "ON anniversaries (guild_id, user_id)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_anniv_guild_md "
            "ON anniversaries (guild_id, substr(anniversary_date, 6, 5))"
        )
        await db.commit()


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------


class DuplicateClaimError(Exception):
    """Raised when an anniversary is already claimed in a guild."""

    def __init__(self, existing_entry: dict | None = None):
        self.existing_entry = existing_entry
        super().__init__(
            "This anniversary has already been claimed in this server."
        )


async def insert_entry(data: dict) -> None:
    """
    Insert a new anniversary entry.
    Expected keys: id, guild_id, user_id, title, subtitle,
                   anniversary_date (YYYY-MM-DD), thumbnail_url,
                   reference_url, calendar_event_id, type, is_custom
    `type` is one of "music", "game", "film" and defaults to "music" so older
    callers (e.g. albums.py) keep working. `is_custom` marks claims entered
    by hand
    because the media wasn't in any search database (defaults to False).
    """
    entry_type = data.get("type") or "music"
    if entry_type not in VALID_TYPES:
        raise ValueError(f"Invalid anniversary type: {entry_type!r}")
    anniversary_date = normalize_iso_date(data["anniversary_date"])
    if anniversary_date is None:
        raise ValueError(
            f"Invalid anniversary date: {data['anniversary_date']!r}"
        )

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO anniversaries
                (id, guild_id, user_id, title, subtitle, anniversary_date,
                 thumbnail_url, reference_url, calendar_event_id, claimed_at,
                 type, is_custom)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                data["id"],
                data["guild_id"],
                data["user_id"],
                data["title"],
                data["subtitle"],
                anniversary_date,
                data.get("thumbnail_url"),
                data.get("reference_url"),
                data.get("calendar_event_id"),
                datetime.now(timezone.utc).isoformat(),
                entry_type,
                1 if data.get("is_custom") else 0,
            ),
        )
        await db.commit()


async def update_calendar_event_id(
    entry_id: str, calendar_event_id: str
) -> None:
    """Update the calendar event ID after successful calendar sync."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE anniversaries SET calendar_event_id = ? WHERE id = ?",
            (calendar_event_id, entry_id),
        )
        await db.commit()


async def update_thumbnail(
    entry_id: str, thumbnail_url: str, reference_url: str | None
) -> None:
    """Update thumbnail and reference URL for an entry."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE anniversaries SET thumbnail_url = ?, reference_url = ? "
            "WHERE id = ?",
            (thumbnail_url, reference_url, entry_id),
        )
        await db.commit()


async def delete_entry(entry_id: str) -> dict | None:
    """Delete an entry by ID. Returns the deleted row or None if not found."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM anniversaries WHERE id = ?", (entry_id,)
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        entry = dict(row)
        await db.execute("DELETE FROM anniversaries WHERE id = ?", (entry_id,))
        await db.commit()
    return entry


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


async def get_user_entries(guild_id: int, user_id: int) -> list[dict]:
    """Get all anniversary entries claimed by a user in a guild."""
    return await _fetch_all(
        "SELECT * FROM anniversaries WHERE guild_id = ? AND user_id = ? "
        "ORDER BY claimed_at DESC",
        (guild_id, user_id),
    )


async def get_todays_entries(guild_id: int, today: date) -> list[dict]:
    """
    Get all entries whose anniversary falls on `today`'s MM-DD.
    Feb 29 anniversaries are celebrated on Mar 1 in non-leap years.
    """
    month_days = [today.strftime("%m-%d")]
    if today.month == 3 and today.day == 1 and not calendar.isleap(today.year):
        month_days.append("02-29")

    placeholders = ", ".join("?" for _ in month_days)
    return await _fetch_all(
        f"""SELECT * FROM anniversaries
            WHERE guild_id = ?
            AND substr(anniversary_date, 6, 5) IN ({placeholders})""",
        (guild_id, *month_days),
    )


async def get_entries_on_date(guild_id: int, month_day: str) -> list[dict]:
    """
    Get all entries with an anniversary on a specific MM-DD.
    month_day format: 'MM-DD'
    """
    return await _fetch_all(
        """SELECT * FROM anniversaries
           WHERE guild_id = ?
           AND substr(anniversary_date, 6, 5) = ?
           ORDER BY anniversary_date ASC""",
        (guild_id, month_day),
    )


async def check_duplicate(
    guild_id: int,
    title: str,
    subtitle: str | None = None,
    entry_type: str | None = None,
    exclude_id: str | None = None,
) -> dict | None:
    """
    Check whether an entry is already claimed in a guild (case-insensitive).
    `subtitle` and `entry_type` are optional filters. Pass None to ignore them.
    Games can be deduplicated by title alone because their subtitle can vary.
    """
    sql = (
        "SELECT * FROM anniversaries WHERE guild_id = ? "
        "AND LOWER(title) = LOWER(?)"
    )
    params: list = [guild_id, title]
    if subtitle is not None:
        sql += " AND LOWER(subtitle) = LOWER(?)"
        params.append(subtitle)
    if entry_type is not None:
        sql += " AND type = ?"
        params.append(entry_type)
    if exclude_id is not None:
        sql += " AND id != ?"
        params.append(exclude_id)
    sql += " LIMIT 1"
    return await _fetch_one(sql, params)


async def get_entries_missing_calendar(
    guild_id: int | None = None,
) -> list[dict]:
    """Get all entries with no real calendar event (for sync operations).
    Includes local placeholder IDs ("local-…", see utils/zoho.py). These
    were never created in Zoho and need to be retried after configuration.
    """
    sql = (
        "SELECT * FROM anniversaries "
        "WHERE (calendar_event_id IS NULL OR calendar_event_id LIKE 'local-%')"
    )
    params: list = []
    if guild_id is not None:
        sql += " AND guild_id = ?"
        params.append(guild_id)
    return await _fetch_all(sql, params)


async def get_entries_missing_thumbnail(
    guild_id: int | None = None,
) -> list[dict]:
    """Get all entries with no thumbnail_url (for cover sync operations)."""
    sql = (
        "SELECT * FROM anniversaries "
        "WHERE (thumbnail_url IS NULL OR thumbnail_url = '')"
    )
    params: list = []
    if guild_id is not None:
        sql += " AND guild_id = ?"
        params.append(guild_id)
    return await _fetch_all(sql, params)


async def search_entries(
    guild_id: int, query: str | None, user_id: int | None
) -> list[dict]:
    """Search by title/subtitle and/or user. Query wildcards are literal."""
    sql = "SELECT * FROM anniversaries WHERE guild_id = ?"
    params: list = [guild_id]
    if user_id is not None:
        sql += " AND user_id = ?"
        params.append(user_id)
    if query:
        pattern = f"%{_escape_like(query)}%"
        sql += " AND (title LIKE ? ESCAPE '\\' OR subtitle LIKE ? ESCAPE '\\')"
        params.extend([pattern, pattern])
    sql += " ORDER BY claimed_at DESC"
    return await _fetch_all(sql, params)


# ---------------------------------------------------------------------------
# Single entries, listing, stats
# ---------------------------------------------------------------------------

_ENTRY_FIELDS = {
    "title",
    "subtitle",
    "anniversary_date",
    "user_id",
    "thumbnail_url",
    "reference_url",
    "calendar_event_id",
}


async def get_entry(entry_id: str) -> dict | None:
    """Get one entry by ID."""
    return await _fetch_one(
        "SELECT * FROM anniversaries WHERE id = ?", (entry_id,)
    )


async def get_entry_by_id(entry_id: str) -> dict | None:
    """Retrieve a single anniversary entry by its ID."""
    return await get_entry(entry_id)


async def get_all_entries(guild_id: int) -> list[dict]:
    """Every entry in a guild (used for /upcoming and the weekly digest)."""
    return await _fetch_all(
        "SELECT * FROM anniversaries WHERE guild_id = ? "
        "ORDER BY anniversary_date ASC",
        (guild_id,),
    )


async def update_entry(entry_id: str, fields: dict[str, Any]) -> dict | None:
    """Update whitelisted fields and return the entry, if it exists.

    Dates are normalized to YYYY-MM-DD; invalid dates raise ValueError.
    """
    unknown = set(fields) - _ENTRY_FIELDS
    if unknown:
        raise ValueError(f"Cannot update fields: {sorted(unknown)}")
    values = dict(fields)
    if "anniversary_date" in values:
        normalized = normalize_iso_date(values["anniversary_date"])
        if normalized is None:
            raise ValueError(
                f"Invalid anniversary date: {values['anniversary_date']!r}"
            )
        values["anniversary_date"] = normalized
    if values:
        assignments = ", ".join(f"{column} = ?" for column in values)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                f"UPDATE anniversaries SET {assignments} WHERE id = ?",  # noqa: S608 (whitelisted columns)
                (*values.values(), entry_id),
            )
            await db.commit()
    return await get_entry(entry_id)


async def get_stats(guild_id: int) -> dict:
    """Totals, per-type counts and the top claimers for a guild."""
    by_type = {
        r["type"]: r["n"]
        for r in await _fetch_all(
            "SELECT type, COUNT(*) AS n FROM anniversaries "
            "WHERE guild_id = ? GROUP BY type",
            (guild_id,),
        )
    }
    top = await _fetch_all(
        "SELECT user_id, COUNT(*) AS n FROM anniversaries WHERE guild_id = ? "
        "GROUP BY user_id ORDER BY n DESC, user_id ASC LIMIT 5",
        (guild_id,),
    )
    totals = await _fetch_one(
        "SELECT COUNT(*) AS total, COALESCE(SUM(is_custom), 0) AS custom, "
        "COUNT(DISTINCT user_id) AS claimers "
        "FROM anniversaries WHERE guild_id = ?",
        (guild_id,),
    ) or {"total": 0, "custom": 0, "claimers": 0}
    return {**totals, "by_type": by_type, "top": top}


# ---------------------------------------------------------------------------
# Bot state, per-server and per-user settings
# ---------------------------------------------------------------------------

_GUILD_FIELDS = {"reminder_channel_id", "digest_enabled"}
_USER_FIELDS = {"dm_enabled", "notice_days"}


async def get_state(key: str) -> str | None:
    """Read persistent bot state, such as the last reminder run time."""
    row = await _fetch_one("SELECT value FROM bot_state WHERE key = ?", (key,))
    return row["value"] if row else None


async def set_state(key: str, value: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO bot_state (key, value) VALUES (?, ?)",
            (key, value),
        )
        await db.commit()


async def _set_fields(
    table: str,
    id_column: str,
    allowed: set[str],
    row_id: int,
    fields: dict[str, Any],
) -> None:
    unknown = set(fields) - allowed
    if unknown:
        raise ValueError(f"Unknown {table} fields: {sorted(unknown)}")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"INSERT OR IGNORE INTO {table} ({id_column}) VALUES (?)",
            (row_id,),
        )  # noqa: S608
        if fields:
            assignments = ", ".join(f"{column} = ?" for column in fields)
            await db.execute(
                f"UPDATE {table} SET {assignments} WHERE {id_column} = ?",  # noqa: S608 (whitelisted)
                (*fields.values(), row_id),
            )
        await db.commit()


async def get_guild_settings(guild_id: int) -> dict:
    row = await _fetch_one(
        "SELECT * FROM guild_settings WHERE guild_id = ?", (guild_id,)
    )
    return row or {
        "guild_id": guild_id,
        "reminder_channel_id": None,
        "digest_enabled": 0,
    }


async def get_all_guild_settings() -> dict[int, dict]:
    return {
        r["guild_id"]: r
        for r in await _fetch_all("SELECT * FROM guild_settings")
    }


async def set_guild_setting(guild_id: int, **fields: Any) -> None:
    await _set_fields(
        "guild_settings", "guild_id", _GUILD_FIELDS, guild_id, fields
    )


async def get_user_settings(user_id: int) -> dict:
    row = await _fetch_one(
        "SELECT * FROM user_settings WHERE user_id = ?", (user_id,)
    )
    return row or {"user_id": user_id, "dm_enabled": 1, "notice_days": 1}


async def get_all_user_settings() -> dict[int, dict]:
    return {
        r["user_id"]: r
        for r in await _fetch_all("SELECT * FROM user_settings")
    }


async def set_user_setting(user_id: int, **fields: Any) -> None:
    await _set_fields(
        "user_settings", "user_id", _USER_FIELDS, user_id, fields
    )
