# utils/modules.py: Cog module registry and config helpers.

from __future__ import annotations

CORE_EXTENSIONS = [
    "cogs.system.help",
    "cogs.tools.ping",
    "cogs.system.status",
    "cogs.system.system",  # Aggregate extension that loads split system command cogs.
]

OPTIONAL_MODULES = {
    "hello":      "cogs.fun.hello",
    "random":     "cogs.fun.random",
    "moderation": "cogs.moderation.core",
    "genai":      "cogs.ai.genai",  # Aggregate extension that loads split AI command cogs.
    "math":       "cogs.tools.math",
    "news":       "cogs.system.news",
    "ytdlp":      "cogs.media.ytdlp",
    "mvsep":      "cogs.media.mvsep",
    "warns":      "cogs.moderation.warns",
    "chroma":     "cogs.ai.chroma",
    # Granular system modules (can be enabled/disabled independently)
    "module":     "cogs.system.module",
    "model":      "cogs.system.model",
    "provider":   "cogs.system.provider",
    "config":     "cogs.system.config",
    "logging":    "cogs.system.logging",
    "core":       "cogs.system.core",
    "timezone":   "cogs.system.timezone",
}

DEFAULT_ENABLED_MODULES = {name: True for name in OPTIONAL_MODULES}


def normalized_module_name(name: str) -> str:
    return name.lower().strip()


def module_extension(name: str) -> str | None:
    return OPTIONAL_MODULES.get(normalized_module_name(name))


def load_enabled_modules(config: dict) -> dict[str, bool]:
    enabled = DEFAULT_ENABLED_MODULES.copy()
    saved = config.get("enabled_modules", {})
    if isinstance(saved, dict):
        for name, value in saved.items():
            key = normalized_module_name(str(name))
            if key in enabled:
                enabled[key] = bool(value)
    return enabled


def save_module_state(config: dict, name: str, enabled: bool) -> None:
    key = normalized_module_name(name)
    states = config.setdefault("enabled_modules", {})
    states[key] = enabled