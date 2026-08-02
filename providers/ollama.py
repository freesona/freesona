import os
import requests
from typing import Any
from providers.base import BaseProvider
from utils.providers import build_messages

class OllamaProvider(BaseProvider):
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
        url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/api/chat")
        messages = build_messages(
            system_prompt,
            user_prompt,
            attachments,
            instruction_prefix=instruction_prefix,
            username=username,
            user_id=user_id,
        )
        payload = {
            "model": model or "llama3.1",
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        response = requests.post(url, json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()
        return data.get("message", {}).get("content", ""), None
