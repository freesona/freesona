import os
import requests
from typing import Any
from providers.base import BaseProvider
from utils.providers import build_messages, post_chat_completion

class OpenAICompatibleProvider(BaseProvider):
    def __init__(self, base_url: str, api_key_env: str, default_model: str, token_field: str = "max_tokens"):
        self.base_url = os.getenv(f"{api_key_env.replace('_API_KEY', '')}_BASE_URL", base_url)
        self.api_key = os.getenv(api_key_env)
        self.default_model = default_model
        self.token_field = token_field
        if not self.api_key:
            raise RuntimeError(f"{api_key_env} missing.")

    def generate_text(
        self,
        user_prompt: str,
        *,
        system_prompt: str = "",
        model: str | None = None,
        max_output_tokens: int = 1024,
        temperature: float | None = None,
        attachments: list[tuple[bytes, str]] | None = None,
        instruction_prefix: str = "",
        username: str = "",
        user_id: int | str | None = None,
        extra_payload: dict[str, Any] | None = None,
    ) -> str | tuple[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        # Add special headers for OpenRouter
        if "openrouter" in self.base_url:
            site_url = os.getenv("OPENROUTER_SITE_URL")
            site_name = os.getenv("OPENROUTER_SITE_NAME")
            if site_url:
                headers["HTTP-Referer"] = site_url
            if site_name:
                headers["X-Title"] = site_name
        # Add special headers for Azure
        elif "azure" in self.base_url:
            headers = {
                "api-key": self.api_key,
                "Content-Type": "application/json",
            }
        
        messages = build_messages(
            system_prompt,
            user_prompt,
            attachments,
            instruction_prefix=instruction_prefix,
            username=username,
            user_id=user_id,
        )
        
        return post_chat_completion(
            url=self.base_url,
            headers=headers,
            model=model or self.default_model,
            messages=messages,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            token_field=self.token_field,
            extra_payload=extra_payload,
        ), None
