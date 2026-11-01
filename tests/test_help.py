"""Tests for the interactive help menu."""

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cogs.conversion.delphitools import Delphitools
from cogs.system.help import HelpCog


class MockContext:
    def __init__(self) -> None:
        self.message = None
        self.sent: list[dict[str, Any]] = []

    async def send(self, *args: Any, **kwargs: Any) -> None:
        self.sent.append({"args": args, **kwargs})


@pytest.mark.anyio
async def test_help_menu_lists_delphitools_commands_in_tools_category():
    tools_cog = SimpleNamespace(help_category="Tools")
    command = SimpleNamespace(
        name="barcodegen",
        help="Generate a barcode from text",
        hidden=False,
        cog=tools_cog,
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
    tools_help = view.categories["Tools"]
    assert tools_help == "`barcodegen` - Generate a barcode from text"
    assert any(button.label == "Tools" for button in view.children)


@pytest.mark.anyio
async def test_help_does_not_list_delphitools_cli_utilities_as_commands():
    bot = SimpleNamespace(
        command_prefix="~",
        get_command=lambda _: None,
        tree=SimpleNamespace(walk_commands=lambda: []),
    )
    cog = HelpCog(cast(Any, bot))

    for name in ("agent", "install-man"):
        ctx = MockContext()
        await cast(Any, cog.help_cmd.callback)(cog, ctx, command_name=name)

        assert ctx.sent == [{"args": (f"No command named `{name}` found.",)}]


@pytest.mark.anyio
async def test_command_help_shows_signature_and_prefix_aware_example():
    command = SimpleNamespace(
        name="hash",
        help=(
            "Create a one-way digest. Example: `{prefix}hash hello sha256`."
        ),
        usage=None,
        signature="<data> <algorithm>",
        aliases=[],
        hidden=False,
    )
    bot = SimpleNamespace(
        command_prefix="!",
        get_command=lambda _: command,
        tree=SimpleNamespace(walk_commands=lambda: []),
    )
    cog = HelpCog(cast(Any, bot))
    ctx = MockContext()

    await cast(Any, cog.help_cmd.callback)(cog, ctx, command_name="hash")

    embed = ctx.sent[0]["embed"]
    assert embed.description == (
        "Create a one-way digest. Example: `!hash hello sha256`."
    )
    assert [(field.name, field.value) for field in embed.fields] == [
        ("Usage", "`!hash <data> <algorithm>`")
    ]


@pytest.mark.anyio
async def test_all_delphitools_commands_have_usage_and_examples():
    delphitools = Delphitools(bot=MagicMock())
    commands = {
        command.name: command for command in delphitools.get_commands()
    }
    bot = SimpleNamespace(
        command_prefix="~",
        get_command=commands.get,
        tree=SimpleNamespace(walk_commands=lambda: []),
    )
    cog = HelpCog(cast(Any, bot))

    for name in commands:
        ctx = MockContext()
        await cast(Any, cog.help_cmd.callback)(cog, ctx, command_name=name)

        embed = ctx.sent[0]["embed"]
        assert "Example:" in embed.description
        usage_fields = [
            field for field in embed.fields if field.name == "Usage"
        ]
        assert len(usage_fields) == 1
        assert usage_fields[0].value.startswith(f"`~{name} ")
