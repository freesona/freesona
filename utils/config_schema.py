# utils/config_schema.py: Shared configuration schema definitions for config commands.
# Moved from cogs/system/admin.py to be shared across config-related cogs.

from utils.config import DEFAULT_CONFIG

# Configuration categories for /config list command
CONFIG_CATEGORIES = {
    "General": [
        "prefix",
        "conversation_response_mode",
        "debounce_seconds",
    ],
    "AI Provider": [
        "provider",
        "provider_model",
        "model_temperature",
    ],
    "ChromaDB": [
        "chroma_collection",
        "chroma_persist_directory",
    ],
    "Autonomy": [
        "autonomy_cooldown_seconds",
        "autonomy_user_cooldown",
    ],
    "MVSEP": [
        "mvsep_poll_interval",
        "mvsep_poll_timeout",
    ],
    "YT-DLP": [
        "ytdlp_subprocess_timeout",
        "ytdlp_compress_target_mb",
    ],
    "Generation": [
        "generation_split_min_length",
        "generation_split_delay_base",
        "generation_split_delay_per_char",
        "generation_split_delay_max",
        "generation_rate_limit",
    ],
    "Logging": [
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
    ],
}

# Configuration descriptions for /config show command
CONFIG_DESCRIPTIONS = {
    "prefix": "Command prefix for text commands (default: ~)",
    "conversation_response_mode": "How bot responds in conversations: all, mention, reply, dm (default: all)",
    "provider": "AI provider to use: gemini, openai, anthropic, openrouter, etc. (default: gemini)",
    "provider_model": "Specific model name for the provider (default: provider default)",
    "model_temperature": "Temperature for AI generation 0.0-2.0 (default: 0.7)",
    "chroma_collection": "ChromaDB collection name for embeddings (default: freesona)",
    "chroma_persist_directory": "ChromaDB persistence directory (default: ./.chroma)",
    "debounce_seconds": "Message debounce time in seconds (default: 1.2)",
    "autonomy_cooldown_seconds": "Cooldown between autonomous actions in seconds (default: 120)",
    "autonomy_user_cooldown": "Cooldown per user for autonomous actions in seconds (default: 60)",
    "mvsep_poll_interval": "MVSEP API poll interval in seconds (default: 10)",
    "mvsep_poll_timeout": "MVSEP API poll timeout in seconds (default: 600)",
    "ytdlp_subprocess_timeout": "YT-DLP subprocess timeout in seconds (default: 300)",
    "ytdlp_compress_target_mb": "YT-DLP compression target size in MB (default: 9.5)",
    "generation_split_min_length": "Minimum message length to trigger splitting (default: 280)",
    "generation_split_delay_base": "Base delay between split messages in seconds (default: 1.2)",
    "generation_split_delay_per_char": "Additional delay per character for split messages (default: 0.012)",
    "generation_split_delay_max": "Maximum delay between split messages in seconds (default: 3.5)",
    "generation_rate_limit": "Max messages per minute for generation (default: 5)",
    "log_enabled": "Enable logging system (default: false)",
    "log_channel_id": "Discord channel ID for log output (default: 0)",
    "log_level": "Log level: DEBUG, INFO, WARNING, ERROR (default: INFO)",
    "log_file_path": "Log file path (default: logs/freesona.log)",
    "log_file_max_months": "Months to retain log files (default: 3)",
    "log_include_discord": "Send logs to Discord channel (default: true)",
    "log_section_general": "Log general bot events (default: true)",
    "log_section_config": "Log config changes (default: false)",
    "log_section_ai": "Log AI provider requests/responses (default: true)",
    "log_section_memory": "Log memory operations (default: false)",
    "log_section_media": "Log media operations (default: false)",
    "log_section_moderation": "Log moderation actions (default: false)",
    "log_section_security": "Log security events (default: true)",
    "log_section_webhook": "Log webhook events (default: false)",
}

# Configuration key order for /config view command (alphabetical within
# categories)
CONFIG_KEY_ORDER = [
    "prefix",
    "conversation_response_mode",
    "debounce_seconds",
    "provider",
    "provider_model",
    "model_temperature",
    "chroma_collection",
    "chroma_persist_directory",
    "autonomy_cooldown_seconds",
    "autonomy_user_cooldown",
    "mvsep_poll_interval",
    "mvsep_poll_timeout",
    "ytdlp_subprocess_timeout",
    "ytdlp_compress_target_mb",
    "generation_split_min_length",
    "generation_split_delay_base",
    "generation_split_delay_per_char",
    "generation_split_delay_max",
    "generation_rate_limit",
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
]


# Model choices for /model set command autocomplete
MODEL_CHOICES = {
    "gemini": [
        "gemini-2.5-pro",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-1.5-pro",
        "gemini-1.5-flash",
        "gemini-1.5-flash-8b",
        "gemini-flash-latest",
        "gemini-pro-latest",
    ],
    "openai": [
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4-turbo",
        "gpt-4",
        "gpt-3.5-turbo",
    ],
    "anthropic": [
        "claude-3-5-sonnet-20241022",
        "claude-3-5-haiku-20241022",
        "claude-3-opus-20240229",
        "claude-3-sonnet-20240229",
        "claude-3-haiku-20240307",
    ],
    "openrouter": [
        "anthropic/claude-3.5-sonnet",
        "anthropic/claude-3.5-haiku",
        "openai/gpt-4o",
        "openai/gpt-4o-mini",
        "google/gemini-2.5-pro",
        "google/gemini-2.5-flash",
        "meta-llama/llama-3.1-405b-instruct",
        "meta-llama/llama-3.1-70b-instruct",
        "mistralai/mistral-large",
    ],
    "nvidia": [
        "nvidia/nemotron-3-ultra",
        "nvidia/nemotron-3-ultra-256k",
        "nvidia/llama-3.1-nemotron-70b-instruct",
    ],
    "ollama": [
        "llama3.1:8b",
        "llama3.1:70b",
        "llama3.2:3b",
        "gemma2:9b",
        "mistral:7b",
        "qwen2.5:7b",
        "phi3:14b",
    ],
}

# Provider choices for /provider set command autocomplete
PROVIDER_CHOICES = [
    "gemini",
    "openai",
    "anthropic",
    "openrouter",
    "nvidia",
    "ollama",
    "deepinfra",
    "together",
    "groq",
    "fireworks",
    "perplexity",
    "cerebras",
    "sambanova",
    "xai",
    "deepseek",
    "moonshot",
    "zhipu",
    "baichuan",
    "minimax",
    "stepfun",
    "volcengine",
    "siliconflow",
    "modelslab",
    "infermatic",
    "hyperbolic",
    "novita",
    "runpod",
    "vast",
    "lambda",
    "together-legacy",
    "openai-compatible",
]


def get_model_choices(provider: str) -> list[str]:
    """Get model choices for a specific provider."""
    return MODEL_CHOICES.get(provider.lower(), [])


def get_provider_choices() -> list[str]:
    """Get list of available provider choices."""
    return PROVIDER_CHOICES


def get_config_default(key: str):
    """Get default value for a config key from DEFAULT_CONFIG."""
    return DEFAULT_CONFIG.get(key)


def is_valid_config_key(key: str) -> bool:
    """Check if a config key is valid (exists in DEFAULT_CONFIG or CONFIG_DESCRIPTIONS)."""
    return key in DEFAULT_CONFIG or key in CONFIG_DESCRIPTIONS


def get_config_category(key: str) -> str | None:
    """Get the category name for a config key."""
    for category, keys in CONFIG_CATEGORIES.items():
        if key in keys:
            return category
    return None


def get_config_description(key: str) -> str:
    """Get description for a config key."""
    return CONFIG_DESCRIPTIONS.get(key, "No description available.")
