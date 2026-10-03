#!/usr/bin/env python3

import os
import unittest
from unittest.mock import MagicMock, patch

from cogs.system.provider import provider_autocomplete
from providers.factory import get_provider
from providers.openai_compatible import OpenAICompatibleProvider
from utils.config_schema import PROVIDER_CHOICES
from utils.providers import normalize_provider_name
from utils.views.config_views import CONFIG_ALLOWED_VALUES


class CustomEndpointProviderTests(unittest.TestCase):

    def test_custom_endpoint_requires_url(self):

        with (

            patch.dict(os.environ, {}, clear=True),

            self.assertRaisesRegex(RuntimeError, "CUSTOM_API_BASE_URL"),

        ):

            get_provider("custom")



    def test_custom_endpoint_allows_anonymous_access(self):

        with patch.dict(

            os.environ,

            {"CUSTOM_API_BASE_URL": "http://localhost:8000/v1/chat/completions"},

            clear=True,

        ):

            provider = get_provider("custom")



        assert isinstance(provider, OpenAICompatibleProvider)

        self.assertIsNone(provider.api_key)



    def test_custom_endpoint_sends_openai_compatible_request(self):

        mock_response = MagicMock()

        mock_response.json.return_value = {

            "choices": [{"message": {"content": "Hello from custom."}}]

        }



        with patch.dict(

            os.environ,

            {

                "CUSTOM_API_BASE_URL": "https://example.test/v1/chat/completions",

                "CUSTOM_API_KEY": "test-key",

            },

            clear=True,

        ):

            provider = get_provider("custom")

            with patch(

                "utils.providers.requests.post",

                return_value=mock_response,

            ) as post:

                text, metadata = provider.generate_text(

                    "Hello",

                    system_prompt="Be brief.",

                    model="test-model",

                    max_output_tokens=25,

                    temperature=0.2,

                )



        self.assertEqual(text, "Hello from custom.")

        self.assertIsNone(metadata)

        post.assert_called_once_with(

            "https://example.test/v1/chat/completions",

            headers={

                "Content-Type": "application/json",

                "Authorization": "Bearer test-key",

            },

            json={

                "model": "test-model",

                "messages": [

                    {"role": "system", "content": "Be brief."},

                    {"role": "user", "content": "Hello"},

                ],

                "max_tokens": 25,

                "temperature": 0.2,

            },

            timeout=60,

        )



    def test_custom_endpoint_omits_authorization_when_no_key_is_set(self):

        mock_response = MagicMock()

        mock_response.json.return_value = {

            "choices": [{"message": {"content": "Hello."}}]

        }



        with patch.dict(

            os.environ,

            {"CUSTOM_API_BASE_URL": "http://localhost:8000/v1/chat/completions"},

            clear=True,

        ):

            provider = get_provider("custom")

            with patch(

                "utils.providers.requests.post",

                return_value=mock_response,

            ) as post:

                provider.generate_text("Hello", model="local-model")



        self.assertNotIn("Authorization", post.call_args.kwargs["headers"])



    def test_custom_is_exposed_as_a_provider_choice(self):

        self.assertIn("custom", PROVIDER_CHOICES)

        self.assertIn("custom", CONFIG_ALLOWED_VALUES["provider"])

        self.assertEqual(normalize_provider_name("openai-compatible"), "custom")





class ProviderCommandTests(unittest.IsolatedAsyncioTestCase):

    async def test_custom_is_offered_by_discord_provider_autocomplete(self):

        choices = await provider_autocomplete(MagicMock(), "cust")



        self.assertEqual([(choice.name, choice.value) for choice in choices], [("custom", "custom")])

