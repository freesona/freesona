#!/usr/bin/env python3

import os

from providers.base import BaseProvider
from providers.gemini import GeminiProvider
from providers.nim import NimProvider
from providers.ollama import OllamaProvider
from providers.openai_compatible import OpenAICompatibleProvider


def get_provider(provider_name: str) -> BaseProvider:
    """Return an instance of a concrete provider based on ``provider_name``.

    Supported provider names include ``gemini``, ``openai``, ``ollama``, ``nim``,
    ``azure``, ``groq``, ``openrouter``, and ``custom``. The function raises a
    ``RuntimeError`` for unknown names.
    """

    if provider_name == "gemini":

        return GeminiProvider()

    elif provider_name == "openai":

        return OpenAICompatibleProvider(

            base_url="https://api.openai.com/v1/chat/completions",

            api_key_env="OPENAI_API_KEY",

            default_model="gpt-4o-mini",

        )

    elif provider_name == "ollama":

        return OllamaProvider()

    elif provider_name == "nim":

        return NimProvider()

    elif provider_name == "azure":

        return OpenAICompatibleProvider(

            base_url="https://api.azure.com/v1/chat/completions",  # placeholder, needs to be from env

            api_key_env="AZURE_AI_KEY",

            default_model="gpt-4o-mini",

        )

    elif provider_name == "groq":

        return OpenAICompatibleProvider(

            base_url="https://api.groq.com/openai/v1/chat/completions",

            api_key_env="GROQ_API_KEY",

            default_model="llama-3.3-70b-versatile",

            token_field="max_completion_tokens",

        )

    elif provider_name == "openrouter":

        return OpenAICompatibleProvider(

            base_url="https://openrouter.ai/api/v1/chat/completions",

            api_key_env="OPENROUTER_API_KEY",

            default_model="meta-llama/llama-3.3-70b-instruct:free",

            token_field="max_completion_tokens",

        )

    elif provider_name == "custom":

        base_url = os.getenv("CUSTOM_API_BASE_URL")

        if not base_url:

            raise RuntimeError("CUSTOM_API_BASE_URL missing.")

        return OpenAICompatibleProvider(

            base_url=base_url,

            api_key_env="CUSTOM_API_KEY",

            default_model="default",

            require_api_key=False,

        )

    raise RuntimeError(f"Unsupported provider '{provider_name}'.")

