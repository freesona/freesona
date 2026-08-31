#!/usr/bin/env python3

# tests/test_modules.py: Python module.

import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Add workspace directory to path to allow importing utils

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))





class ModulesTests(unittest.TestCase):

    def setUp(self):

        self.tmpdir = tempfile.TemporaryDirectory()

        self.addCleanup(self.tmpdir.cleanup)

        self.config_path = os.path.join(self.tmpdir.name, "config.json")



        # Save original CONFIG_FILE_PATH

        self.old_config_path = os.environ.get("CONFIG_FILE_PATH")

        os.environ["CONFIG_FILE_PATH"] = self.config_path



        def restore_env():

            if self.old_config_path is None:

                os.environ.pop("CONFIG_FILE_PATH", None)

            else:

                os.environ["CONFIG_FILE_PATH"] = self.old_config_path



        self.addCleanup(restore_env)



        import utils.config as config_module
        import utils.modules as modules_module



        self.config_module = importlib.reload(config_module)

        self.modules_module = importlib.reload(modules_module)



    def test_normalized_module_name(self):

        self.assertEqual(

            self.modules_module.normalized_module_name("  MATH  "), "math"

        )



    def test_module_extension(self):

        self.assertEqual(

            self.modules_module.module_extension("math"), "cogs.tools.math"

        )

        self.assertIsNone(self.modules_module.module_extension("nonexistent"))



    def test_load_enabled_modules_default(self):

        enabled = self.modules_module.load_enabled_modules({})

        self.assertTrue(enabled["math"])

        self.assertTrue(enabled["genai"])



    def test_save_and_load_module_state(self):

        config = {}

        self.modules_module.save_module_state(config, "math", False)

        self.modules_module.save_module_state(config, "genai", True)



        enabled = self.modules_module.load_enabled_modules(config)

        self.assertFalse(enabled["math"])

        self.assertTrue(enabled["genai"])





if __name__ == "__main__":

    unittest.main()

