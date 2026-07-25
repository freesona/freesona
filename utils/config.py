# utils/config.py: Config I/O and shared embed helpers.

import os
import json

CONFIG_PATH = os.getenv("CONFIG_FILE_PATH", "config.json")

DEFAULT_CONFIG = {
    "prefix": "~",
    "conversation_response_mode": "all",
    "provider": os.getenv("AI_PROVIDER", "gemini"),
    "provider_model": os.getenv("AI_PROVIDER_MODEL", ""),
    "chroma_collection": os.getenv("CHROMA_COLLECTION", "freesona"),
    "chroma_persist_directory": os.getenv("CHROMA_PERSIST_DIRECTORY", "./.chroma"),
    "debounce_seconds": 1.2,
    "autonomy_cooldown_seconds": 120,
    "autonomy_user_cooldown": 60,
    # MVSEP (music separation)
    "mvsep_poll_interval": 10,
    "mvsep_poll_timeout": 600,
    # YT-DLP (audio extraction)
    "ytdlp_subprocess_timeout": 300,
    "ytdlp_compress_target_mb": 9.5,
    # Generation (text splitting & rate limiting)
    "generation_split_min_length": 280,
    "generation_split_delay_base": 1.2,
    "generation_split_delay_per_char": 0.012,
    "generation_split_delay_max": 3.5,
    "generation_rate_limit": 5,
}

DEFAULT_MODEL_NAME = os.getenv("MODEL_NAME", "gemini-flash-lite-latest")
DEFAULT_MODEL_TEMPERATURE = float(os.getenv("MODEL_TEMPERATURE", "0.7"))
DEFAULT_KB_TOP_K = int(os.getenv("KB_TOP_K", "5"))

LAST_DEBUG: dict[int, str] = {}


def load_config() -> dict:
    config = DEFAULT_CONFIG.copy()
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    config.update(data)
        except Exception:
            pass
    return config


def save_config(data: dict):
    os.makedirs(
        os.path.dirname(CONFIG_PATH) if os.path.dirname(CONFIG_PATH) else ".",
        exist_ok=True
    )
    with open(CONFIG_PATH, "w") as f:
        json.dump(data, f, indent=2)


def get_model_name() -> str:
    model = load_config().get("model_name") or DEFAULT_MODEL_NAME
    return str(model).strip() or DEFAULT_MODEL_NAME


def get_provider_name() -> str:
    provider = load_config().get("provider") or os.getenv("AI_PROVIDER", "gemini")
    return str(provider).strip().lower() or "gemini"


def get_provider_model() -> str:
    model = load_config().get("provider_model") or os.getenv("AI_PROVIDER_MODEL") or get_model_name()
    return str(model).strip() or get_model_name()


def get_model_temperature() -> float:
    temp = load_config().get("model_temperature")
    if isinstance(temp, (int, float, str)):
        try:
            return float(temp)
        except (ValueError, TypeError):
            pass
    return DEFAULT_MODEL_TEMPERATURE


def get_kb_top_k() -> int:
    """Get the KB top-k value from config (default: 5)."""
    val = load_config().get("kb_top_k")
    if isinstance(val, (int, float, str)):
        try:
            return int(val)
        except (ValueError, TypeError):
            pass
    return DEFAULT_KB_TOP_K


def get_prompt_token_budget() -> int:
    """Get the prompt token budget from config (default: 8000)."""
    val = load_config().get("prompt_token_budget")
    if isinstance(val, (int, float, str)):
        try:
            return int(val)
        except (ValueError, TypeError):
            pass
    return 8000


def embed_footer(author_display: str, query: str, max_query_len: int = 80) -> str:
    """Returns a footer string: 'Asked by <name> • <truncated query>'"""
    truncated = query if len(query) <= max_query_len else query[:max_query_len - 1] + "…"
    return f"Asked by {author_display}  •  {truncated}"
