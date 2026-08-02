import asyncio
import importlib
import sys
import unittest
from unittest.mock import MagicMock, patch


class TimezoneCompatTests(unittest.TestCase):
    def test_timezone_autocomplete_imports_without_pytz(self):
        with patch.dict(sys.modules, {"pytz": None}):
            import cogs.system.timezone as timezone_module

            importlib.reload(timezone_module)

            choices = asyncio.run(
                timezone_module.timezone_autocomplete(MagicMock(), "America")
            )

        self.assertTrue(choices)
        self.assertTrue(any(choice.value.startswith("America/") for choice in choices))


if __name__ == "__main__":
    unittest.main()
