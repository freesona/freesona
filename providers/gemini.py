#!/usr/bin/env python3

import os
from typing import Any

try:

    from google import genai

except ImportError:

    genai = None  # type: ignore



from providers.base import BaseProvider
from utils.providers import build_interactions_input, format_user_text


class GeminiProvider(BaseProvider):

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

        api_key = os.getenv("GOOGLE_API_KEY")

        if not api_key:

            raise RuntimeError("GOOGLE_API_KEY missing.")

        if genai is None:

            raise RuntimeError("Google Gemini SDK not installed.")

        client = genai.Client(api_key=api_key)



        # Build user text

        user_text = format_user_text(

            user_prompt, instruction_prefix, username, user_id

        )



        # Get previous interaction ID from extra_payload

        previous_interaction_id = None

        if extra_payload and "previous_interaction_id" in extra_payload:

            previous_interaction_id = extra_payload["previous_interaction_id"]



        # Build Interactions API input using the helper function

        interactions_input = build_interactions_input(

            user_prompt=user_text,

            attachments=attachments,

            previous_interaction_id=previous_interaction_id,

            client=client,

        )



        # Create interaction

        interaction_kwargs = {

            "model": model or "gemini-1.5-flash",

            "input": interactions_input["input"],

            "generation_config": {

                "max_output_tokens": max_output_tokens,

                "temperature": temperature,

            },

            # Stateless mode - Freesona manages

            # conversation history

            "store": False,

        }



        # System instruction is a top-level parameter, not inside

        # generation_config

        if system_prompt:

            interaction_kwargs["system_instruction"] = system_prompt



        if previous_interaction_id:

            interaction_kwargs["previous_interaction_id"] = (

                previous_interaction_id

            )



        response = client.interactions.create(**interaction_kwargs)



        # Return tuple of (output_text, interaction_id) for conversation

        # tracking

        output_text = getattr(response, "output_text", "") or ""

        interaction_id = getattr(response, "id", None)

        return output_text, interaction_id

