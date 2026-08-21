# utils/providers.py: Python module.
import base64
import logging
import os
from typing import Any

import requests

from utils.config import get_model_name
from utils.config import get_provider_model as get_configured_provider_model
from utils.config import get_provider_name as get_configured_provider_name

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
    user_id: int | str | None = None,
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
        attachments: Optional list of (bytes, mime_type)
            tuples for multimodal input
        instruction_prefix: Optional prefix to prepend to user
            message (e.g., formatting instructions)
        username: Optional username to tag in the message
            (e.g., "[username]: ")
        user_id: Optional user ID to tag in the message

    Returns:
        List of message dicts in OpenAI-compatible format
    """
    messages: list[dict[str, Any]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    user_text = format_user_text(
        user_prompt, instruction_prefix, username, user_id
    )

    if not attachments:
        messages.append({"role": "user", "content": user_text})
    else:
        # Standard OpenAI / NVIDIA NIM Multimodal Vision message format
        content_parts: list[dict[str, Any]] = [
            {"type": "text", "text": user_text}
        ]

        # Add attachment parts
        for att_bytes, att_mime in attachments:
            b64 = base64.b64encode(att_bytes).decode("utf-8")
            if att_mime.startswith("image/"):
                content_parts.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{att_mime};base64,{b64}"},
                    }
                )
            else:
                # For non-image attachments (PDF, audio, video), use file
                # format
                filename = f"attachment.{att_mime.split('/')[-1]}"
                content_parts.append(
                    {
                        "type": "file",
                        "file": {
                            "filename": filename,
                            "file_data": f"data:{att_mime};base64,{b64}",
                        },
                    }
                )

        messages.append({"role": "user", "content": content_parts})

    return messages


def get_provider_config() -> dict[str, Any]:
    return {
        "provider": get_provider_name(),
        "model": get_provider_model() or get_model_name(),
    }


# File size threshold for using File API (20MB inline limit)
FILE_API_THRESHOLD = 20 * 1024 * 1024  # 20MB


def _upload_to_file_api(
    client: Any,
    file_bytes: bytes,
    mime_type: str,
    display_name: str = "upload",
) -> str:
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

    types.File(
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
    return bool(
        mime_type == "application/pdf"
        or mime_type.startswith(("audio/", "video/"))
    )


def _is_youtube_url(text: str) -> bool:
    """Check if text is a YouTube URL."""
    import re

    youtube_patterns = [
        r"(?:https?://)?(?:www\.)?youtube\.com/watch\?v=[\w-]+",
        r"(?:https?://)?(?:www\.)?youtu\.be/[\w-]+",
        r"(?:https?://)?(?:www\.)?youtube\.com/shorts/[\w-]+",
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
        attachments: Optional list of (bytes, mime_type)
            tuples
        previous_interaction_id: Optional ID of previous
            interaction for multi-turn
        system_prompt: Optional system instruction (passed
            separately in generation config)
        client: Optional Gemini client for File API uploads

    Returns:
        Dict with 'input' (list of parts) and optionally
        'previous_interaction_id'
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
                input_parts.append(
                    {
                        "type": "video",
                        "uri": url,
                    }
                )
                continue

            # Normalize MIME type to supported equivalent
            att_mime = _normalize_mime_type(att_mime)

            mime_category = _get_mime_category(att_mime)

            # Check if we should use File API
            use_file_api = client is not None and _should_use_file_api(
                att_bytes, att_mime
            )

            if use_file_api:
                try:
                    file_uri = _upload_to_file_api(client, att_bytes, att_mime)
                    input_parts.append(
                        {
                            "type": mime_category,
                            "uri": file_uri,
                            "mime_type": att_mime,
                        }
                    )
                except (
                    requests.RequestException,
                    OSError,
                    ValueError,
                    TypeError,
                ) as e:
                    logger.warning(
                        f"File API upload failed, falling back to inline: {e}"
                    )
                    use_file_api = False

            if not use_file_api:
                # Inline data (base64)
                import base64

                b64 = base64.b64encode(att_bytes).decode("utf-8")
                input_parts.append(
                    {
                        "type": mime_category,
                        "data": b64,
                        "mime_type": att_mime,
                    }
                )

    result: dict[str, Any] = {"input": input_parts}
    if previous_interaction_id:
        result["previous_interaction_id"] = previous_interaction_id

    return result


def normalize_provider_name(provider: str | None) -> str:
    provider_name = (
        provider or get_provider_name()
    ).strip().lower() or DEFAULT_PROVIDER
    aliases = {
        "nvidia": "nim",
        "nvidia-nim": "nim",
        "azure-foundry": "azure",
        "azure-ai-foundry": "azure",
        "azure-ai": "azure",
        "groqcloud": "groq",
        "open-router": "openrouter",
        "open_router": "openrouter",
        "openai-compatible": "custom",
        "openai_compatible": "custom",
        "custom-endpoint": "custom",
        "custom_endpoint": "custom",
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
        response = requests.post(
            url, headers=headers, json=payload, timeout=60
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]
    except requests.exceptions.HTTPError as e:
        status_code = (
            response.status_code if response is not None else "Unknown"
        )
        text = response.text if response is not None else str(e)
        logger.error(f"HTTPError from {url} [{status_code}]: {text}")
        raise
    except Exception as e:
        logger.error(f"Request error calling {url}: {e}")
        raise


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
    from providers.factory import get_provider

    provider_name = normalize_provider_name(provider)
    provider_impl = get_provider(provider_name)
    return provider_impl.generate_text(
        user_prompt,
        system_prompt=system_prompt,
        model=model,
        max_output_tokens=max_output_tokens,
        temperature=temperature,
        attachments=attachments,
        instruction_prefix=instruction_prefix,
        username=username,
        user_id=user_id,
        extra_payload=extra_payload
    )
