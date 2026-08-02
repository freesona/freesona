from typing import Any
from providers.openai_compatible import OpenAICompatibleProvider

class NimProvider(OpenAICompatibleProvider):
    def __init__(self):
        super().__init__(
            base_url="https://integrate.api.nvidia.com/v1/chat/completions",
            api_key_env="NVIDIA_API_KEY", # or NIM_API_KEY
            default_model="meta/llama-3.1-8b-instruct"
        )
        # Handle NIM-specific key variants
        import os
        self.api_key = os.getenv("NVIDIA_API_KEY") or os.getenv("NIM_API_KEY")
        if not self.api_key:
            raise RuntimeError("NVIDIA_API_KEY or NIM_API_KEY missing.")
            
        base_url = (
            os.getenv("NVIDIA_NIM_BASE_URL")
            or os.getenv("NIM_BASE_URL")
            or "https://integrate.api.nvidia.com/v1/chat/completions"
        )
        self.base_url = base_url

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
        nim_payload: dict[str, Any] = extra_payload or {}
        target_model = model or self.default_model

        # Model-specific parameters for NVIDIA NIM
        if "diffusiongemma" in target_model.lower():
            max_output_tokens = max(max_output_tokens, 2048)
            nim_payload.update(
                {
                    "diffusion_sampler": "entropy_bound",
                    "diffusion_entropy_bound": 0.1,
                    "canvas_length": 256,
                }
            )
        elif "mistral-small-4" in target_model.lower():
            max_output_tokens = max(max_output_tokens, 2048)
            # Disable internal thinking loops for fast visual chat
            nim_payload["reasoning_effort"] = "none"
            
        return super().generate_text(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            model=target_model,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            attachments=attachments,
            instruction_prefix=instruction_prefix,
            username=username,
            user_id=user_id,
            extra_payload=nim_payload
        )
