# utils/logging_utils.py: Logging utilities with file rotation and optional Discord channel output.

import calendar
import logging
import logging.handlers
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import asyncio
import discord
from discord import Client
from discord.ext import commands

from utils.config import load_config, CONFIG_PATH


# Track background tasks for Discord log handler to avoid silent exception loss
_background_tasks: set[asyncio.Task] = set()

# Global bot instance for logging reconfiguration
_bot_instance: Optional[Client] = None

# Track handlers added by this module (using id() to avoid attribute issues)
_our_handler_ids: set[int] = set()


# Logger name prefixes mapped to config section keys
LOG_SECTIONS = {
    "general": "log_section_general",
    "config": "log_section_config",
    "ai": "log_section_ai",
    "memory": "log_section_memory",
    "media": "log_section_media",
    "moderation": "log_section_moderation",
    "security": "log_section_security",
    "webhook": "log_section_webhook",
}

# Mapping of logger name prefixes to section keys
# Sorted by prefix length (longest first) for longest-prefix matching
LOGGER_SECTION_MAP = {
    # Config changes (more specific)
    "utils.config": "config",
    "cogs.system.admin": "config",
    # AI providers and generation (more specific)
    "utils.providers": "ai",
    "utils.generation": "ai",
    "utils.prompt_builder": "ai",
    "utils.prompt_builder_providers": "ai",
    "cogs.ai": "ai",
    # Memory systems (more specific)
    "utils.memory": "memory",
    "utils.conversation": "memory",
    "utils.character_memory": "memory",
    "utils.canon": "memory",
    "utils.chroma": "memory",
    # Media (more specific)
    "cogs.media": "media",
    "utils.search": "media",
    # Moderation (more specific)
    "cogs.moderation": "moderation",
    # Security (more specific)
    "utils.security": "security",
    # Webhooks (more specific)
    "fastapi_server": "webhook",
    # General bot events (least specific - catch-all)
    "main": "general",
    "cogs": "general",
    "utils": "general",
}


class SectionFilter(logging.Filter):
    """Filter log records based on enabled log sections."""

    def __init__(self):
        super().__init__()
        self._enabled_sections: set[str] = set()
        self._load_sections()

    def _load_sections(self):
        """Load enabled sections from config."""
        config = load_config()
        self._enabled_sections = {
            section for section, key in LOG_SECTIONS.items()
            if config.get(key, False)
        }

    def filter(self, record: logging.LogRecord) -> bool:
        """Return True if the record should be logged."""
        # Always allow CRITICAL and ERROR level logs
        if record.levelno >= logging.ERROR:
            return True

        # Find which section this logger belongs to (longest prefix match)
        logger_name = record.name
        section = "general"  # default
        longest_match = ""
        for prefix, sec in LOGGER_SECTION_MAP.items():
            if logger_name.startswith(prefix) and len(prefix) > len(longest_match):
                section = sec
                longest_match = prefix

        # Check if section is enabled
        return section in self._enabled_sections

    def refresh(self):
        """Reload section config from disk."""
        self._load_sections()


# Global section filter instance
_section_filter: Optional["SectionFilter"] = None


def get_section_filter() -> SectionFilter:
    """Get or create the global section filter."""
    global _section_filter
    if _section_filter is None:
        _section_filter = SectionFilter()
    return _section_filter


def refresh_section_filter():
    """Refresh the section filter with latest config."""
    global _section_filter
    if _section_filter is not None:
        _section_filter.refresh()


class MonthlyRotatingFileHandler(logging.handlers.BaseRotatingHandler):
    """Rotating file handler that creates a new file every N months."""

    def __init__(
        self,
        filename: str,
        months: int = 3,
        encoding: str = "utf-8",
        delay: bool = False,
    ):
        self.months = months
        self.base_filename = Path(filename)
        self.base_filename.parent.mkdir(parents=True, exist_ok=True)
        self.current_filename = self._compute_filename()
        super().__init__(self.current_filename, "a", encoding, delay)

    def _compute_filename(self) -> Path:
        """Compute the filename for the current rotation period."""
        now = datetime.now()
        # Calculate the start of the current rotation period
        period_start_month = ((now.month - 1) // self.months) * self.months + 1
        period_start = datetime(now.year, period_start_month, 1)
        # Calculate period end accurately using calendar.monthrange
        period_end_month = period_start_month + self.months - 1
        period_end_year = now.year
        if period_end_month > 12:
            period_end_month -= 12
            period_end_year += 1
        _, last_day = calendar.monthrange(period_end_year, period_end_month)
        period_end = datetime(period_end_year, period_end_month, last_day)
        suffix = period_start.strftime("%Y-%m") + "_to_" + period_end.strftime("%Y-%m")
        stem = self.base_filename.stem
        return self.base_filename.parent / f"{stem}_{suffix}{self.base_filename.suffix}"

    def shouldRollover(self, record: logging.LogRecord) -> bool:
        """Check if we should rollover to a new file."""
        new_filename = self._compute_filename()
        return new_filename != self.current_filename

    def doRollover(self):
        """Perform the rollover."""
        if self.stream:
            self.stream.close()
            self.stream = None
        self.current_filename = self._compute_filename()
        self.baseFilename = str(self.current_filename)
        if not self.delay:
            self.stream = self._open()


class DiscordLogHandler(logging.Handler):
    """Logging handler that sends log records to a Discord channel."""

    def __init__(self, bot: Client, channel_id: int, level: int = logging.INFO):
        super().__init__(level)
        self.bot = bot
        self.channel_id = channel_id
        self._channel: Optional[discord.abc.Messageable] = None
        self.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))

    async def _get_channel(self) -> Optional[discord.abc.Messageable]:
        """Get the Discord channel, caching it."""
        if self._channel is None:
            channel = self.bot.get_channel(self.channel_id)
            if channel is None:
                try:
                    channel = await self.bot.fetch_channel(self.channel_id)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    channel = None
            # Only cache if it's a messageable channel
            if channel is not None and hasattr(channel, "send"):
                self._channel = channel  # type: ignore[assignment]
        return self._channel

    def _log_task_done(self, task: asyncio.Task) -> None:
        """Callback to handle task completion and log any exceptions."""
        _background_tasks.discard(task)
        try:
            task.result()
        except asyncio.CancelledError:
            pass
        except (discord.NotFound, discord.Forbidden, discord.HTTPException) as e:
            logging.getLogger(__name__).warning(
                "Discord log handler failed to send message: %s", e
            )
        except Exception as e:
            logging.getLogger(__name__).error(
                "Unexpected error in Discord log handler: %s", e, exc_info=True
            )

    def emit(self, record: logging.LogRecord):
        """Emit a log record to Discord (async)."""
        if not self.bot.is_ready():
            return
        channel = self.bot.get_channel(self.channel_id)
        if channel is None or not hasattr(channel, "send"):
            return
        try:
            msg = self.format(record)
            # Truncate to Discord's 2000 char limit
            if len(msg) > 1900:
                msg = msg[:1900] + "... [truncated]"
            # Use create_task to avoid blocking, track the task
            task = self.bot.loop.create_task(channel.send(f"```\n{msg}\n```"))  # type: ignore[attr-defined]
            _background_tasks.add(task)
            task.add_done_callback(self._log_task_done)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException) as e:
            logging.getLogger(__name__).warning(
                "Discord log handler failed to queue message: %s", e
            )
        except Exception as e:
            logging.getLogger(__name__).error(
                "Unexpected error in Discord log handler: %s", e, exc_info=True
            )


def setup_logging(bot: Optional[Client] = None) -> logging.Logger:
    """Configure application logging based on config.json settings.

    Args:
        bot: Optional bot/client instance for Discord channel logging.

    Returns:
        The root logger instance.
    """
    global _bot_instance
    if bot is not None:
        _bot_instance = bot
    elif _bot_instance is not None:
        bot = _bot_instance

    config = load_config()

    log_enabled = config.get("log_enabled", False)
    log_level = config.get("log_level", "INFO")
    log_file_path = config.get("log_file_path", "logs/freesona.log")
    log_file_max_months = config.get("log_file_max_months", 3)
    log_channel_id = config.get("log_channel_id", 0)
    log_include_discord = config.get("log_include_discord", True)

    if not log_enabled:
        # Disable all logging except critical
        logging.getLogger().setLevel(logging.CRITICAL + 1)
        return logging.getLogger()

    # Set root logger level
    level = getattr(logging, log_level.upper(), logging.INFO)
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove only handlers added by this module (tracked by id)
    for handler in root_logger.handlers[:]:
        if id(handler) in _our_handler_ids:
            root_logger.removeHandler(handler)
            _our_handler_ids.discard(id(handler))

    # Get section filter
    section_filter = get_section_filter()

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_formatter = logging.Formatter("%(asctime)s:%(levelname)s:%(name)s: %(message)s")
    console_handler.setFormatter(console_formatter)
    console_handler.addFilter(section_filter)
    _our_handler_ids.add(id(console_handler))
    root_logger.addHandler(console_handler)

    # File handler with monthly rotation
    try:
        file_handler = MonthlyRotatingFileHandler(log_file_path, months=log_file_max_months)
        file_handler.setLevel(level)
        file_formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        file_handler.setFormatter(file_formatter)
        file_handler.addFilter(section_filter)
        _our_handler_ids.add(id(file_handler))
        root_logger.addHandler(file_handler)
    except Exception as e:
        # Log to console if file handler fails
        root_logger.error(f"Failed to setup file logging: {e}")

    # Discord channel handler (optional)
    if log_include_discord and bot and log_channel_id:
        discord_handler = DiscordLogHandler(bot, log_channel_id, level)
        discord_handler.addFilter(section_filter)
        _our_handler_ids.add(id(discord_handler))
        root_logger.addHandler(discord_handler)

    return root_logger


async def send_log_message(bot: Client, message: str, level: str = "INFO"):
    """Send a log message to the configured Discord log channel.

    Args:
        bot: The bot instance.
        message: The message to log.
        level: Log level (INFO, WARNING, ERROR, etc.)
    """
    config = load_config()
    log_channel_id = config.get("log_channel_id", 0)
    log_enabled = config.get("log_enabled", False)
    log_include_discord = config.get("log_include_discord", True)

    if not log_enabled or not log_include_discord or not log_channel_id:
        return

    channel = bot.get_channel(log_channel_id)
    if channel is None:
        try:
            channel = await bot.fetch_channel(log_channel_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException) as e:
            logging.getLogger(__name__).warning(
                "Failed to fetch log channel %s: %s", log_channel_id, e
            )
            return

    if channel and hasattr(channel, "send"):
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            formatted = f"[{timestamp}] [{level}] {message}"
            if len(formatted) > 1900:
                formatted = formatted[:1900] + "... [truncated]"
            await channel.send(f"```\n{formatted}\n```")  # type: ignore[attr-defined]
        except (discord.NotFound, discord.Forbidden, discord.HTTPException) as e:
            logging.getLogger(__name__).warning(
                "Failed to send log message to channel %s: %s", log_channel_id, e
            )
        except Exception as e:
            logging.getLogger(__name__).error(
                "Unexpected error sending log message: %s", e, exc_info=True
            )


def get_log_config() -> dict:
    """Get current logging configuration."""
    config = load_config()
    return {
        "enabled": config.get("log_enabled", False),
        "channel_id": config.get("log_channel_id", 0),
        "level": config.get("log_level", "INFO"),
        "file_path": config.get("log_file_path", "logs/freesona.log"),
        "file_max_months": config.get("log_file_max_months", 3),
        "include_discord": config.get("log_include_discord", True),
        # Section configs
        "section_general": config.get("log_section_general", True),
        "section_config": config.get("log_section_config", False),
        "section_ai": config.get("log_section_ai", True),
        "section_memory": config.get("log_section_memory", False),
        "section_media": config.get("log_section_media", False),
        "section_moderation": config.get("log_section_moderation", False),
        "section_security": config.get("log_section_security", True),
        "section_webhook": config.get("log_section_webhook", False),
    }


def set_log_config(**kwargs):
    """Update logging configuration."""
    config = load_config()
    valid_keys = {
        "log_enabled",
        "log_channel_id",
        "log_level",
        "log_file_path",
        "log_file_max_months",
        "log_include_discord",
        "log_section_general",
        "log_section_config",
        "log_section_ai",
        "log_section_memory",
        "log_section_media",
        "log_section_moderation",
        "log_section_security",
        "log_section_webhook",
    }
    for key, value in kwargs.items():
        if key in valid_keys:
            config[key] = value
    # Save to config.json
    import json
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)
    # Reconfigure logging using stored bot instance
    refresh_section_filter()
    setup_logging()