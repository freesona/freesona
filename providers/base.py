from abc import ABC, abstractmethod
from typing import Any


class BaseProvider(ABC):
    @abstractmethod
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
        """Generate text using the provider."""
