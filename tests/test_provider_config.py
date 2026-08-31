#!/usr/bin/env python3

# tests/test_provider_config.py: Python module.

import importlib
import os
import tempfile
import unittest


class ProviderConfigTests(unittest.TestCase):

    def setUp(self):

        self.tmpdir = tempfile.TemporaryDirectory()

        self.addCleanup(self.tmpdir.cleanup)

        self.config_path = os.path.join(self.tmpdir.name, "config.json")



        self.old_config_path = os.environ.get("CONFIG_FILE_PATH")

        os.environ["CONFIG_FILE_PATH"] = self.config_path



        def restore_env():

            if self.old_config_path is None:

                os.environ.pop("CONFIG_FILE_PATH", None)

            else:

                os.environ["CONFIG_FILE_PATH"] = self.old_config_path



        self.addCleanup(restore_env)



        import utils.config as config_module



        self.config_module = importlib.reload(config_module)



    def test_provider_defaults_to_gemini(self):

        self.assertEqual(self.config_module.get_provider_name(), "gemini")



    def test_provider_can_be_overridden(self):

        self.config_module.save_config({"provider": "openai"})

        self.assertEqual(self.config_module.get_provider_name(), "openai")



    def test_model_name_defaults(self):

        self.assertEqual(

            self.config_module.get_model_name(), "gemini-flash-lite-latest"

        )



    def test_model_name_can_be_overridden(self):

        self.config_module.save_config({"model_name": "custom-model"})

        self.assertEqual(self.config_module.get_model_name(), "custom-model")



    def test_embed_footer(self):

        footer = self.config_module.embed_footer("Alice", "Hello World")

        self.assertEqual(footer, "Asked by Alice  •  Hello World")



        # Test truncation

        long_query = "a" * 100

        footer_truncated = self.config_module.embed_footer(

            "Alice", long_query, max_query_len=20

        )

        self.assertTrue(footer_truncated.endswith("…"))

        self.assertEqual(

            len(footer_truncated), len("Asked by Alice  •  ") + 20

        )





if __name__ == "__main__":

    unittest.main()

