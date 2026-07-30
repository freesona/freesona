# utils/providers.py: Python module.
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


# File size threshold for using File API (20MB inline limit)
FILE_API_THRESHOLD = 20 * 1024 * 1024  # 20MB


def _upload_to_file_api(client: Any, file_bytes: bytes, mime_type: str, display_name: str = "upload") -> str:
    """
    Upload a file to Gemini File API and return the file URI.
    
    Args:
        client: Gemini client
        file_bytes: File content as bytes
        mime_type: MIME type of the file
        display_name: Display name for the file
    
    Returns:
        File URI for use in Interactions API
    """
    import io
    from google.genai import types
    
    file_obj = types.File(
        display_name=display_name,
        mime_type=mime_type,
    )
    
    # Create file with content
    uploaded = client.files.upload(
        file=io.BytesIO(file_bytes),
        config=types.UploadFileConfig(
            display_name=display_name,
            mime_type=mime_type,
        ),
    )
    
    # Wait for processing
    import time
    while uploaded.state and uploaded.state.name == "PROCESSING":
        time.sleep(1)
        uploaded = client.files.get(name=uploaded.name)
    
    if uploaded.state and uploaded.state.name == "FAILED":
        raise RuntimeError(f"File upload failed: {uploaded.error}")
    
    return uploaded.uri


def _should_use_file_api(file_bytes: bytes, mime_type: str) -> bool:
    """Determine if a file should use File API instead of inline data."""
    # Use File API for files larger than threshold
    if len(file_bytes) > FILE_API_THRESHOLD:
        return True
    # Use File API for PDFs, audio, video (better handling)
    if mime_type == "application/pdf" or mime_type.startswith("audio/") or mime_type.startswith("video/"):
        return True
    return False


def _is_youtube_url(text: str) -> bool:
    """Check if text is a YouTube URL."""
    import re
    youtube_patterns = [
        r'(?:https?://)?(?:www\.)?youtube\.com/watch\?v=[\w-]+',
        r'(?:https?://)?(?:www\.)?youtu\.be/[\w-]+',
        r'(?:https?://)?(?:www\.)?youtube\.com/shorts/[\w-]+',
    ]
    return any(re.match(pattern, text.strip()) for pattern in youtube_patterns)


def _get_mime_category(mime_type: str) -> str:
    """Get the Interactions API part type for a MIME type."""
    if mime_type.startswith("image/"):
        return "image"
    elif mime_type == "application/pdf":
        return "document"
    elif mime_type.startswith("audio/"):
        return "audio"
    elif mime_type.startswith("video/"):
        return "video"
    else:
        return "file"


def _normalize_mime_type(mime_type: str) -> str:
    """Normalize MIME types to ones supported by Gemini API."""
    # Map unsupported MIME types to supported equivalents
    mime_mapping = {
        "video/quicktime": "video/mov",
        "video/x-quicktime": "video/mov",
    }
    return mime_mapping.get(mime_type.lower(), mime_type)


def build_interactions_input(
    user_prompt: str,
    attachments: list[tuple[bytes, str]] | None = None,
    *,
    previous_interaction_id: str | None = None,
    system_prompt: str | None = None,
    client: Any | None = None,
) -> dict[str, Any]:
    """
    Build the input for Gemini Interactions API.
    
    Args:
        user_prompt: The user's text message
        attachments: Optional list of (bytes, mime_type) tuples
        previous_interaction_id: Optional ID of previous interaction for multi-turn
        system_prompt: Optional system instruction (passed separately in generation config)
        client: Optional Gemini client for File API uploads
    
    Returns:
        Dict with 'input' (list of parts) and optionally 'previous_interaction_id'
    """
    input_parts: list[dict[str, Any]] = []
    
    # Add user text
    if user_prompt.strip():
        input_parts.append({"type": "text", "text": user_prompt})
    
    # Add attachments
    if attachments:
        for att_bytes, att_mime in attachments:
            # Check if it's a YouTube URL (passed as text)
            if att_mime == "text/youtube":
                url = att_bytes.decode("utf-8").strip()
                input_parts.append({
                    "type": "video",
                    "uri": url,
                })
                continue
            
            # Normalize MIME type to supported equivalent
            att_mime = _normalize_mime_type(att_mime)
            
            mime_category = _get_mime_category(att_mime)
            
            # Check if we should use File API
            use_file_api = client is not None and _should_use_file_api(att_bytes, att_mime)
            
            if use_file_api:
                try:
                    file_uri = _upload_to_file_api(client, att_bytes, att_mime)
                    input_parts.append({
                        "type": mime_category,
                        "uri": file_uri,
                        "mime_type": att_mime,
                    })
                except Exception as e:
                    logger.warning(f"File API upload failed, falling back to inline: {e}")
                    use_file_api = False
            
            if not use_file_api:
                # Inline data (base64)
                import base64
                b64 = base64.b64encode(att_bytes).decode("utf-8")
                input_parts.append({
                    "type": mime_category,
                    "data": b64,
                    "mime_type": att_mime,
                })
    
    result: dict[str, Any] = {"input": input_parts}
    if previous_interaction_id:
        result["previous_interaction_id"] = previous_interaction_id
    
    return result


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
    extra_payload: dict[str, Any] | None = None,
) -> str | tuple[str, Any]:
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

        # Build user text
        user_text = format_user_text(user_prompt, instruction_prefix, username, user_id)

        # Get previous interaction ID from extra_payload
        previous_interaction_id = None
        if extra_payload and "previous_interaction_id" in extra_payload:
            previous_interaction_id = extra_payload["previous_interaction_id"]

        # Build Interactions API input using the helper function
        # System instruction is a top-level parameter (not in generation_config)
        interactions_input = build_interactions_input(
            user_prompt=user_text,
            attachments=attachments,
            previous_interaction_id=previous_interaction_id,
            client=client,
        )

        # Create interaction
        interaction_kwargs = {
            "model": model_name,
            "input": interactions_input["input"],
            "generation_config": {
                "max_output_tokens": max_output_tokens,
                "temperature": temp,
            },
            "store": False,  # Stateless mode - Freesona manages conversation history
        }
        
        # System instruction is a top-level parameter, not inside generation_config
        if system_prompt:
            interaction_kwargs["system_instruction"] = system_prompt
        
        if previous_interaction_id:
            interaction_kwargs["previous_interaction_id"] = previous_interaction_id
        
        response = client.interactions.create(**interaction_kwargs)
        
        # Return tuple of (output_text, interaction_id) for conversation tracking
        output_text = getattr(response, "output_text", "") or ""
        interaction_id = getattr(response, "id", None)
        return output_text, interaction_id

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
        ), None

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
        return data.get("message", {}).get("content", ""), None

    if provider_name == "nim":
        api_key = os.getenv("NVIDIA_API_KEY") or os.getenv("NIM_API_KEY")
        if not api_key:
            raise RuntimeError("NVIDIA_API_KEY or NIM_API_KEY missing.")
        url = os.getenv("NVIDIA_NIM_BASE_URL") or os.getenv("NIM_BASE_URL") or "https://integrate.api.nvidia.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": OPENAI_COMPATIBLE_CONTENT_TYPE}
        
        nim_payload: dict[str, Any] = {}
        target_model = model_name or "meta/llama-3.1-8b-instruct"

        # Model-specific parameters for NVIDIA NIM
        if "diffusiongemma" in target_model.lower():
            max_output_tokens = max(max_output_tokens, 2048)
            nim_payload.update({
                "diffusion_sampler": "entropy_bound",
                "diffusion_entropy_bound": 0.1,
                "canvas_length": 256
            })
        elif "mistral-small-4" in target_model.lower():
            max_output_tokens = max(max_output_tokens, 2048)
            nim_payload["reasoning_effort"] = "none"  # Disable internal thinking loops for fast visual chat

        return post_chat_completion(
            url=url,
            headers=headers,
            model=target_model,
            messages=messages,
            max_output_tokens=max_output_tokens,
            temperature=temp,
            extra_payload=nim_payload,
        ), None

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
        ), None

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
        ), None

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
        ), None

    raise RuntimeError(f"Unsupported provider '{provider_name}'.")