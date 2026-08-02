# utils/modules.py: Cog module registry and config helpers.

from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)

CORE_EXTENSIONS = [
    "cogs.system.help",
    "cogs.tools.ping",
    "cogs.system.status",
    # Aggregate extension that loads split system command cogs.
    "cogs.system.system",
]

BUILTIN_OPTIONAL_MODULES = {
    "hello": "cogs.fun.hello",
    "random": "cogs.fun.random",
    "moderation": "cogs.moderation.core",
    # Aggregate extension that loads split AI command cogs.
    "genai": "cogs.ai.genai",
    "math": "cogs.tools.math",
    "news": "cogs.system.news",
    "ytdlp": "cogs.media.ytdlp",
    "mvsep": "cogs.media.mvsep",
    "warns": "cogs.moderation.warns",
    "chroma": "cogs.ai.chroma",
    # Granular system modules are loaded by cogs.system.system (CORE_EXTENSIONS).
    # Keep the keys so /module list still shows them, but they map to the
    # aggregate loader so they aren't double-loaded.
    "module": "cogs.system.system",
    "model": "cogs.system.system",
    "provider": "cogs.system.system",
    "config": "cogs.system.system",
    "logging": "cogs.system.system",
    "core": "cogs.system.system",
}


def _load_local_modules():
    path = "modules.local.json"
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r") as f:
            data = json.load(f)
            if isinstance(data, dict):
                valid = {}
                for k, v in data.items():
                    if isinstance(k, str) and isinstance(v, str):
                        valid[k] = v
                    else:
                        logger.warning(f"Invalid entry in modules.local.json: {k}: {v}")
                return valid
            else:
                logger.warning("modules.local.json is not a JSON object")
                return {}
    except Exception as e:
        logger.exception(f"Failed to load modules.local.json: {e}")
        return {}


OPTIONAL_MODULES = BUILTIN_OPTIONAL_MODULES.copy()
OPTIONAL_MODULES.update(_load_local_modules())

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
