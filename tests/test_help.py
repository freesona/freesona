"""Tests for the interactive help menu."""

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cogs.system.help import HelpCog


class MockContext:
    def __init__(self) -> None:
        self.message = None
        self.sent: list[dict[str, Any]] = []

    async def send(self, **kwargs: Any) -> None:
        self.sent.append(kwargs)


@pytest.mark.anyio
async def test_help_menu_lists_delphitools_commands_in_conversion_category():
    conversion_cog = SimpleNamespace(help_category="Conversion")
    command = SimpleNamespace(
        name="barcodegen",
        help="Generate a barcode from text",
        hidden=False,
        cog=conversion_cog,
    )
    bot = SimpleNamespace(
        command_prefix="~",
        commands=[command],
        user=None,
    )
    cog = HelpCog(cast(Any, bot))
    ctx = MockContext()

    await cast(Any, cog.help_cmd.callback)(cog, ctx)

    view = ctx.sent[0]["view"]
    conversion_help = view.categories["Conversion"]
    assert "`barcodegen` - Generate a barcode from text" in conversion_help
    assert (
        "**Delphitools CLI** (`dt`, `delphi`, `delphitools`)"
        in conversion_help
    )
    assert "`preflight`, `zine`, `impose`" in conversion_help
    assert "`qr`, `barcode`, `meta`" in conversion_help
    assert any(
        button.label == "Conversion" for button in view.children
    )
