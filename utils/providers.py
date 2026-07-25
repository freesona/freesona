import os
import logging
from typing import Any

import requests
import base64

from utils.config import get_model_name, get_provider_model as get_configured_provider_model, get_provider_name as get_configured_provider_name, get_model_temperature

logger = logging.getLogger("FreesonaBot")

DEFAULT_PROVIDER = os.getenv("AI_PROVIDER", "gemini")
OPENAI_COMPATIBLE_CONTENT_TYPE = "application/json"


def get_provider_name() -> str:
    return get_configured_provider_name()


def get_provider_model() -> str:
    return get_configured_provider_model()


def format_user_text(
    user_prompt: str, 
    instruction_prefix: str = "", 
    username: str = "", 
    user_id: int | str | None = None
) -> str:
    """Helper to format the user message with prefix, username, and ID tags."""
    if user_id and username:
        name_tag = f"[{username} (ID: {user_id})]: "
    elif user_id:
        name_tag = f"[ID: {user_id}]: "
    elif username:
        name_tag = f"[{username}]: "
    else:
        name_tag = ""

    if instruction_prefix:
        return f"{instruction_prefix}\n\n{name_tag}{user_prompt}".strip()
    return f"{name_tag}{user_prompt}".strip()


def build_messages(
    system_prompt: str,
    user_prompt: str,
    attachments: list[tuple[bytes, str]] | None = None,
    *,
    instruction_prefix: str = "",
    username: str = "",
    user_id: int | str | None = None,
) -> list[dict[str, Any]]:
    """
    Build the message list for the provider API.
    
    Args:
        system_prompt: The system instruction/prompt
        user_prompt: The user's message content
        attachments: Optional list of (bytes, mime_type) tuples for multimodal input
        instruction_prefix: Optional prefix to prepend to user message (e.g., formatting instructions)
        username: Optional username to tag in the message (e.g., "[username]: ")
        user_id: Optional user ID to tag in the message
    
    Returns:
        List of message dicts in OpenAI-compatible format
    """
    messages: list[dict[str, Any]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    user_text = format_user_text(user_prompt, instruction_prefix, username, user_id)

    if not attachments:
        messages.append({"role": "user", "content": user_text})
    else:
        # Standard OpenAI / NVIDIA NIM Multimodal Vision message format
        content_parts: list[dict[str, Any]] = [{
            "type": "text",
            "text": user_text
        }]

        # Add attachment parts
        for att_bytes, att_mime in attachments:
            b64 = base64.b64encode(att_bytes).decode("utf-8")
            if att_mime.startswith("image/"):
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{att_mime};base64,{b64}"}
                })
            else:
                # For non-image attachments (PDF, audio, video), use file format
                content_parts.append({
                    "type": "file",
                    "file": {
                        "filename": f"attachment.{att_mime.split('/')[-1]}",
                        "file_data": f"data:{att_mime};base64,{b64}"
                    }
                })

        messages.append({"role": "user", "content": content_parts})

    return messages


def get_provider_config() -> dict[str, Any]:
    return {
        "provider": get_provider_name(),
        "model": get_provider_model() or get_model_name(),
    }


def normalize_provider_name(provider: str | None) -> str:
    provider_name = (provider or get_provider_name()).strip().lower() or DEFAULT_PROVIDER
    aliases = {
        "nvidia": "nim",
        "nvidia-nim": "nim",
        "azure-foundry": "azure",
        "azure-ai-foundry": "azure",
        "azure-ai": "azure",
        "groqcloud": "groq",
        "open-router": "openrouter",
        "open_router": "openrouter",
    }
    return aliases.get(provider_name, provider_name)


def post_chat_completion(
    *,
    url: str,
    headers: dict[str, str],
    model: str,
    messages: list[dict[str, Any]],
    max_output_tokens: int,
    token_field: str = "max_tokens",
    extra_payload: dict[str, Any] | None = None,
    temperature: float | None = None,
) -> str:
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        token_field: max_output_tokens,
    }
    if temperature is not None:
        payload["temperature"] = temperature
    if extra_payload:
        payload.update(extra_payload)

    response = None
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]
    except requests.exceptions.HTTPError as e:
        status_code = response.status_code if response is not None else "Unknown"
        text = response.text if response is not None else str(e)
        logger.error(f"HTTPError from {url} [{status_code}]: {text}")
        raise e
    except Exception as e:
        logger.error(f"Request error calling {url}: {e}")
        raise e


def generate_text(
    user_prompt: str,
    *,
    system_prompt: str = "",
    provider: str | None = None,
    model: str | None = None,
    max_output_tokens: int = 1024,
    temperature: float | None = None,
    attachments: list[tuple[bytes, str]] | None = None,
    instruction_prefix: str = "",
    username: str = "",
    user_id: int | str | None = None,
) -> str:
    provider_name = normalize_provider_name(provider)
    model_name = (model or get_provider_model() or get_model_name()).strip() or get_model_name()
    temp = get_model_temperature() if temperature is None else temperature
    messages = build_messages(
        system_prompt, 
        user_prompt, 
        attachments,
        instruction_prefix=instruction_prefix,
        username=username,
        user_id=user_id,
    )

    if provider_name == "gemini":
        from google import genai
        from google.genai import types

        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("GOOGLE_API_KEY missing.")
        client = genai.Client(api_key=api_key)

        # Build generation config - only include system_instruction if provided
        generation_config_kwargs: dict[str, Any] = {
            "max_output_tokens": max_output_tokens,
            "temperature": temp,
        }
        if system_prompt:
            generation_config_kwargs["system_instruction"] = system_prompt
        generation_config = types.GenerateContentConfig(**generation_config_kwargs)

        # Build contents as a list of Parts for proper Gemini API format
        user_text = format_user_text(user_prompt, instruction_prefix, username, user_id)
        contents = [types.Part.from_text(text=user_text)]
        if attachments:
            for att_bytes, att_mime in attachments:
                # Use inline_data (via from_bytes) for all MIME types when sending bytes directly
                contents.append(types.Part.from_bytes(data=att_bytes, mime_type=att_mime)) # type: ignore

        response = client.models.generate_content(
            model=model_name,
            contents=contents,
            config=generation_config,
        )
        return getattr(response, "text", "") or ""

    if provider_name == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY missing.")
        url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1/chat/completions")
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": OPENAI_COMPATIBLE_CONTENT_TYPE}
        return post_chat_completion(
            url=url,
            headers=headers,
            model=model_name or "gpt-4o-mini",
            messages=messages,
            max_output_tokens=max_output_tokens,
            temperature=temp,
        )

    if provider_name == "ollama":
        url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/api/chat")
        payload = {
            "model": model_name or "llama3.1",
            "messages": messages,
            "stream": False,
            "options": {"temperature": temp},
        }
        response = requests.post(url, json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()
        return data.get("message", {}).get("content", "")

    if provider_name == "nim":
        api_key = os.getenv("NVIDIA_API_KEY") or os.getenv("NIM_API_KEY")
        if not api_key:
            raise RuntimeError("NVIDIA_API_KEY or NIM_API_KEY missing.")
        url = os.getenv("NVIDIA_NIM_BASE_URL") or os.getenv("NIM_BASE_URL") or "https://integrate.api.nvidia.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": OPENAI_COMPATIBLE_CONTENT_TYPE}
        
        extra_payload: dict[str, Any] = {}
        target_model = model_name or "meta/llama-3.1-8b-instruct"

        # Model-specific parameters for NVIDIA NIM
        if "diffusiongemma" in target_model.lower():
            max_output_tokens = max(max_output_tokens, 2048)
            extra_payload.update({
                "diffusion_sampler": "entropy_bound",
                "diffusion_entropy_bound": 0.1,
                "canvas_length": 256
            })
        elif "mistral-small-4" in target_model.lower():
            max_output_tokens = max(max_output_tokens, 2048)
            extra_payload["reasoning_effort"] = "none"  # Disable internal thinking loops for fast visual chat

        return post_chat_completion(
            url=url,
            headers=headers,
            model=target_model,
            messages=messages,
            max_output_tokens=max_output_tokens,
            temperature=temp,
            extra_payload=extra_payload,
        )

    if provider_name == "azure":
        api_key = os.getenv("AZURE_AI_KEY")
        if not api_key:
            raise RuntimeError("AZURE_AI_KEY missing.")
        url = os.getenv("AZURE_AI_BASE_URL")
        if not url:
            raise RuntimeError("AZURE_AI_BASE_URL missing — set it to your Azure AI Foundry endpoint.")
        headers = {"api-key": api_key, "Content-Type": OPENAI_COMPATIBLE_CONTENT_TYPE}
        return post_chat_completion(
            url=url,
            headers=headers,
            model=model_name or "gpt-4o-mini",
            messages=messages,
            max_output_tokens=max_output_tokens,
            temperature=temp,
        )

    if provider_name == "groq":
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY missing.")
        url = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1/chat/completions")
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": OPENAI_COMPATIBLE_CONTENT_TYPE}
        return post_chat_completion(
            url=url,
            headers=headers,
            model=model_name or "llama-3.3-70b-versatile",
            messages=messages,
            max_output_tokens=max_output_tokens,
            temperature=temp,
            token_field="max_completion_tokens",
        )

    if provider_name == "openrouter":
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY missing.")
        url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1/chat/completions")
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": OPENAI_COMPATIBLE_CONTENT_TYPE}
        site_url = os.getenv("OPENROUTER_SITE_URL")
        site_name = os.getenv("OPENROUTER_SITE_NAME")
        if site_url:
            headers["HTTP-Referer"] = site_url
        if site_name:
            headers["X-Title"] = site_name
        return post_chat_completion(
            url=url,
            headers=headers,
            model=model_name or "meta-llama/llama-3.3-70b-instruct:free",
            messages=messages,
            max_output_tokens=max_output_tokens,
            temperature=temp,
            token_field="max_completion_tokens",
        )

    raise RuntimeError(f"Unsupported provider '{provider_name}'.")
