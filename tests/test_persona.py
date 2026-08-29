# tests/test_persona.py: Unit tests for persona module

import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from utils.persona import CURRENT_PERSONA, LEGACY_DETECTED, PERSONA_DATA

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class TestReloadPersona(unittest.TestCase):
    """Tests for reload_persona function."""

    def setUp(self):
        # Save original state
        self.original_persona_data = PERSONA_DATA.copy()
        self.original_current_persona = CURRENT_PERSONA
        self.original_legacy_detected = LEGACY_DETECTED
        self.original_env = os.environ.get("AI_PERSONA_JSON_FILE")

    def tearDown(self):
        # Restore original state
        import utils.persona as persona_module

        persona_module.PERSONA_DATA = self.original_persona_data
        persona_module.CURRENT_PERSONA = self.original_current_persona
        persona_module.LEGACY_DETECTED = self.original_legacy_detected

        if self.original_env is None:
            os.environ.pop("AI_PERSONA_JSON_FILE", None)
        else:
            os.environ["AI_PERSONA_JSON_FILE"] = self.original_env

    def test_reload_persona_from_json(self):
        """reload_persona should load from persona.json when it exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            persona_path = Path(tmpdir) / "persona.json"
            with open(persona_path, "w") as f:
                f.write(
                    '{"core_personality": "Test persona", "background": "", '
                    '"beliefs": "", "language": "", '
                    '"system_instructions": "", "temperature": ""}'
                )

            with patch.dict(
                os.environ, {"AI_PERSONA_JSON_FILE": str(persona_path)}
            ):
                import utils.persona as persona_module

                importlib.reload(persona_module)

                persona, legacy = persona_module.reload_persona()

                self.assertIn("Test persona", persona)
                self.assertFalse(legacy)

    def test_reload_persona_from_legacy(self):
        """reload_persona should load from persona.txt when
        persona.json doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            legacy_path = Path(tmpdir) / "persona.txt"
            with open(legacy_path, "w") as f:
                f.write("Legacy persona content")

            # Ensure persona.json doesn't exist
            json_path = Path(tmpdir) / "persona.json"
            if json_path.exists():
                json_path.unlink()

            with patch.dict(
                os.environ,
                {
                    "AI_PERSONA_JSON_FILE": str(json_path),
                    "AI_PERSONA_FILE": str(legacy_path),
                },
            ):
                import utils.persona as persona_module

                importlib.reload(persona_module)

                persona, legacy = persona_module.reload_persona()

                self.assertEqual(persona, "Legacy persona content")
                self.assertTrue(legacy)

    def test_reload_persona_default_when_no_files(self):
        """reload_persona should use default when neither file exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "persona.json"
            legacy_path = Path(tmpdir) / "persona.txt"

            # Ensure neither file exists
            if json_path.exists():
                json_path.unlink()
            if legacy_path.exists():
                legacy_path.unlink()

            with patch.dict(
                os.environ,
                {
                    "AI_PERSONA_JSON_FILE": str(json_path),
                    "AI_PERSONA_FILE": str(legacy_path),
                    "AI_PERSONA": "Default from env",
                },
            ):
                import utils.persona as persona_module

                importlib.reload(persona_module)

                persona, legacy = persona_module.reload_persona()

                self.assertEqual(persona, "Default from env")
                self.assertFalse(legacy)

    def test_reload_persona_updates_globals(self):
        """reload_persona should update global PERSONA_DATA,
        CURRENT_PERSONA, LEGACY_DETECTED."""
        with tempfile.TemporaryDirectory() as tmpdir:
            persona_path = Path(tmpdir) / "persona.json"
            with open(persona_path, "w") as f:
                f.write(
                    '{"core_personality": "Updated persona", '
                    '"background": "", "beliefs": "", "language": "", '
                    '"system_instructions": "", "temperature": ""}'
                )

            with patch.dict(
                os.environ, {"AI_PERSONA_JSON_FILE": str(persona_path)}
            ):
                import utils.persona as persona_module

                importlib.reload(persona_module)

                persona, legacy = persona_module.reload_persona()

                # Check globals were updated
                self.assertEqual(persona_module.CURRENT_PERSONA, persona)
                self.assertEqual(persona_module.LEGACY_DETECTED, legacy)
                self.assertEqual(
                    persona_module.PERSONA_DATA["core_personality"],
                    "Updated persona",
                )


# Need to import importlib

if __name__ == "__main__":
    unittest.main()
