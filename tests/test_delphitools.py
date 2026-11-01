"""Tests for the delphitools Discord cog."""

import asyncio
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord import app_commands
from discord.ext import commands as discord_commands

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cogs.conversion.delphitools import Delphitools, _run_capture


class MockContext:
    def __init__(self, message: Any = None) -> None:
        self.message = message
        self.sent: list[dict[str, Any]] = []

    @asynccontextmanager
    async def typing(self):
        yield

    async def send(self, *args: Any, **kwargs: Any) -> None:
        files = kwargs.get("files", [])
        if "file" in kwargs:
            files = [kwargs["file"], *files]
        if files:
            kwargs["uploaded_files"] = [
                (file.filename, file.fp.read()) for file in files
            ]
            if len(files) == 1:
                kwargs["uploaded_filename"] = files[0].filename
                kwargs["uploaded_bytes"] = kwargs["uploaded_files"][0][1]
            for file in files:
                file.close()
        self.sent.append({"args": args, **kwargs})


@pytest.mark.anyio
async def test_run_capture_returns_exit_code_and_trimmed_stdout():
    process = MagicMock()
    process.communicate = AsyncMock(return_value=(b" result \n", b"warning"))
    process.returncode = 0

    with patch(
        "cogs.conversion.delphitools.asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=process),
    ) as create_process:
        result = await _run_capture("dt", "encode", "base64", "abc", timeout=7)

    assert result == (0, "result")
    create_process.assert_awaited_once_with(
        "dt",
        "encode",
        "base64",
        "abc",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )


@pytest.mark.anyio
async def test_run_capture_returns_stderr_for_failed_command():
    process = MagicMock()
    process.communicate = AsyncMock(
        return_value=(b"", b"invalid barcode format\n")
    )
    process.returncode = 1

    with patch(
        "cogs.conversion.delphitools.asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=process),
    ):
        result = await _run_capture("dt", "barcode", "hello", timeout=7)

    assert result == (1, "invalid barcode format")


@pytest.mark.anyio
async def test_run_capture_can_preserve_report_output_with_failure_status():
    process = MagicMock()
    process.communicate = AsyncMock(
        return_value=(b"preflight report", b"error: warning found")
    )
    process.returncode = 3

    with patch(
        "cogs.conversion.delphitools.asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=process),
    ):
        result = await _run_capture(
            "dt",
            "preflight",
            "input.pdf",
            timeout=7,
            include_stdout_on_failure=True,
        )

    assert result == (3, "preflight report\nerror: warning found")


@pytest.mark.anyio
async def test_run_capture_uses_configured_delphitools_executable(monkeypatch):
    process = MagicMock()
    process.communicate = AsyncMock(return_value=(b"result", b""))
    process.returncode = 0
    monkeypatch.setenv("DELPHITOOLS_EXECUTABLE", "/opt/delphitools/dt")

    with patch(
        "cogs.conversion.delphitools.asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=process),
    ) as create_process:
        await _run_capture("dt", "barcode", "hello", timeout=7)

    create_process.assert_awaited_once_with(
        "/opt/delphitools/dt",
        "barcode",
        "hello",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )


@pytest.mark.anyio
async def test_run_capture_kills_process_and_raises_on_timeout():
    process = MagicMock()
    process.communicate = AsyncMock(
        side_effect=[asyncio.TimeoutError, (b"", b"")]
    )
    process.returncode = -9

    with (
        patch(
            "cogs.conversion.delphitools.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=process),
        ),
        pytest.raises(asyncio.TimeoutError),
    ):
        await _run_capture("dt", "encode", "base64", "abc", timeout=1)

    process.kill.assert_called_once_with()
    assert process.communicate.await_count == 2


@pytest.mark.anyio
async def test_barcodegen_reports_missing_delphitools_cli():
    cog = Delphitools(bot=MagicMock())
    ctx = MockContext()

    with patch(
        "cogs.conversion.delphitools.asyncio.create_subprocess_exec",
        new=AsyncMock(
            side_effect=FileNotFoundError(2, "No such file or directory", "dt")
        ),
    ):
        await cast(Any, cog.barcodegen.callback)(cog, ctx, "hello", "code128")

    assert ctx.sent == [
        {
            "args": (
                "❌ **Barcode generation failed.** Cannot start the "
                "Delphitools CLI. Set `DELPHITOOLS_EXECUTABLE` to its "
                "executable path or add it to the bot process PATH.",
            )
        }
    ]


@pytest.mark.anyio
async def test_barcodegen_uses_delphitools_cli_arguments():
    cog = Delphitools(bot=MagicMock())
    ctx = MockContext()

    async def run_cli(*command: str, timeout: int) -> tuple[int, str]:
        Path(command[-1]).write_bytes(b"barcode-image")
        return 0, ""

    with patch(
        "cogs.conversion.delphitools._run_capture", side_effect=run_cli
    ) as run_capture:
        await cast(Any, cog.barcodegen.callback)(
            cog, ctx, "12345678", "code128"
        )

    call = run_capture.await_args
    assert call is not None
    assert call.args[:5] == (
        "dt",
        "barcode",
        "12345678",
        "--format",
        "code128",
    )
    assert call.args[5] == "--output"
    assert call.args[6].endswith("barcode.code128.png")
    assert call.kwargs == {"timeout": 300}
    assert ctx.sent[0]["uploaded_bytes"] == b"barcode-image"


@pytest.mark.anyio
async def test_encode_reports_cli_result():
    cog = Delphitools(bot=MagicMock())
    ctx = MockContext()

    with patch(
        "cogs.conversion.delphitools._run_capture",
        new=AsyncMock(return_value=(0, "YWJj")),
    ) as run_capture:
        await cast(Any, cog.encode.callback)(cog, ctx, "abc", "base64")

    run_capture.assert_awaited_once_with(
        "dt", "encode", "base64", "abc", timeout=300
    )
    assert ctx.sent == [{"args": ("✅ **Encoded:** YWJj",)}]


@pytest.mark.anyio
async def test_imgconvert_sends_generated_image():
    cog = Delphitools(bot=MagicMock())
    attachment = MagicMock(
        filename="sample.png",
        content_type="image/png",
    )
    ctx = MockContext(message=MagicMock())

    async def run_cli(*command: str, timeout: int) -> tuple[int, str]:
        input_path = Path(command[2])
        output_path = Path(command[command.index("--output") + 1])
        assert input_path.read_bytes() == b"image-data"
        output_path.write_bytes(b"converted-image")
        return 0, ""

    with (
        patch(
            "cogs.conversion.delphitools.extract_attachments",
            new=AsyncMock(return_value=[(b"image-data", "image/png")]),
        ),
        patch(
            "cogs.conversion.delphitools._run_capture", side_effect=run_cli
        ) as run_capture,
    ):
        await cast(Any, cog.imgconvert.callback)(
            cog, ctx, "webp", attachment, 640, None
        )

    call = run_capture.await_args
    assert call is not None
    command = call.args
    assert command[:2] == ("dt", "convert")
    assert command[2].endswith("input.png")
    assert command[3:5] == ("--to", "webp")
    assert command[5] == "--output"
    assert command[6].endswith("output.webp")
    assert command[7:] == ("--resize", "640x")
    assert call.kwargs == {"timeout": 300}
    assert len(ctx.sent) == 1
    assert "sample.png → output.webp" in ctx.sent[0]["content"]

    assert ctx.sent[0]["uploaded_filename"] == "output.webp"
    assert ctx.sent[0]["uploaded_bytes"] == b"converted-image"


@pytest.mark.anyio
async def test_palette_uses_supported_cli_arguments():
    cog = Delphitools(bot=MagicMock())
    ctx = MockContext()

    async def run_cli(*command: str, timeout: int) -> tuple[int, str]:
        output_path = Path(command[command.index("--output") + 1])
        output_path.write_bytes(b"palette-image")
        return 0, ""

    with patch(
        "cogs.conversion.delphitools._run_capture", side_effect=run_cli
    ) as run_capture:
        await cast(Any, cog.palette.callback)(cog, ctx, "analogous", 7, "png")

    call = run_capture.await_args
    assert call is not None
    command = call.args
    assert command[:2] == ("dt", "palette")
    assert command[2:7] == (
        "--size",
        "7",
        "--format",
        "png",
        "--output",
    )
    assert command[7].endswith("palette.png")
    assert command[8:] == ("--strategy", "analogous")
    assert call.kwargs == {"timeout": 300}
    assert ctx.sent[0]["uploaded_bytes"] == b"palette-image"


@pytest.mark.anyio
async def test_qrgen_uses_supported_cli_arguments():
    cog = Delphitools(bot=MagicMock())
    ctx = MockContext()

    async def run_cli(*command: str, timeout: int) -> tuple[int, str]:
        output_path = Path(command[command.index("--output") + 1])
        output_path.write_bytes(b"qr-image")
        return 0, ""

    with patch(
        "cogs.conversion.delphitools._run_capture", side_effect=run_cli
    ) as run_capture:
        await cast(Any, cog.qrgen.callback)(cog, ctx, "https://example.com")

    call = run_capture.await_args
    assert call is not None
    assert call.args[:3] == (
        "dt",
        "qr",
        "https://example.com",
    )
    assert call.args[3] == "--output"
    assert call.args[4].endswith("qr.png")
    assert call.kwargs == {"timeout": 300}
    assert ctx.sent[0]["uploaded_bytes"] == b"qr-image"


@pytest.mark.anyio
async def test_unitconvert_combines_value_with_source_unit():
    cog = Delphitools(bot=MagicMock())
    ctx = MockContext()

    with patch(
        "cogs.conversion.delphitools._run_capture",
        new=AsyncMock(return_value=(0, "6.21371192")),
    ) as run_capture:
        await cast(Any, cog.unitconvert.callback)(cog, ctx, 10.0, "km", "mi")

    run_capture.assert_awaited_once_with(
        "dt", "unit", "10 km", "mi", timeout=300
    )


@pytest.mark.anyio
async def test_regex_passes_pattern_and_text_as_separate_cli_arguments():
    cog = Delphitools(bot=MagicMock())
    ctx = MockContext()

    with patch(
        "cogs.conversion.delphitools._run_capture",
        new=AsyncMock(return_value=(0, "Match 1: 'hello'")),
    ) as run_capture:
        await cast(Any, cog.regex.callback)(
            cog, ctx, r"\w+", "hello && do-not-run", "i"
        )

    run_capture.assert_awaited_once_with(
        "dt",
        "regex",
        r"\w+",
        "hello && do-not-run",
        "--flags",
        "i",
        timeout=300,
    )
    assert "Match 1" in ctx.sent[0]["args"][0]


@pytest.mark.anyio
async def test_completions_returns_shell_script_as_downloadable_file():
    cog = Delphitools(bot=MagicMock())
    ctx = MockContext()

    with patch(
        "cogs.conversion.delphitools._run_capture",
        new=AsyncMock(return_value=(0, "complete -W 'help convert' dt")),
    ) as run_capture:
        await cast(Any, cog.completions.callback)(cog, ctx, "bash")

    run_capture.assert_awaited_once_with(
        "dt", "completions", "bash", timeout=300
    )
    assert ctx.sent[0]["content"].startswith(
        "✅ **Shell completion script generated.**"
    )
    assert ctx.sent[0]["uploaded_files"] == [
        (
            "delphitools-completions.bash",
            b"complete -W 'help convert' dt",
        )
    ]


@pytest.mark.anyio
async def test_convert_uses_output_file_and_supported_resize_flags():
    cog = Delphitools(bot=MagicMock())
    attachment = MagicMock(filename="sample.png", content_type="image/png")
    ctx = MockContext(message=MagicMock())

    async def run_cli(*command: str, timeout: int) -> tuple[int, str]:
        output_path = Path(command[command.index("--output") + 1])
        output_path.write_bytes(b"jpeg-data")
        return 0, ""

    with (
        patch(
            "cogs.conversion.delphitools.extract_attachments",
            new=AsyncMock(return_value=[(b"image-data", "image/png")]),
        ),
        patch(
            "cogs.conversion.delphitools._run_capture", side_effect=run_cli
        ) as run_capture,
    ):
        await cast(Any, cog.convert.callback)(
            cog, ctx, "jpeg", attachment, "800x", 70
        )

    assert run_capture.await_args is not None
    command = run_capture.await_args.args
    assert command[:2] == ("dt", "convert")
    assert command[2].endswith("input_0.png")
    assert command[3:9] == (
        "--to",
        "jpeg",
        "--quality",
        "70",
        "--resize",
        "800x",
    )
    assert command[9] == "--output"
    assert command[10].endswith("result.jpeg")
    assert ctx.sent[0]["uploaded_files"] == [("result.jpeg", b"jpeg-data")]


@pytest.mark.anyio
async def test_preflight_sends_cli_analysis_for_attached_pdf():
    cog = Delphitools(bot=MagicMock())
    attachment = MagicMock(
        filename="sample.pdf", content_type="application/pdf"
    )
    ctx = MockContext(message=MagicMock())

    with (
        patch(
            "cogs.conversion.delphitools.extract_attachments",
            new=AsyncMock(return_value=[(b"pdf-data", "application/pdf")]),
        ),
        patch(
            "cogs.conversion.delphitools._run_capture",
            new=AsyncMock(
                return_value=(3, "PDF report\nWarnings (1): no BleedBox")
            ),
        ) as run_capture,
    ):
        await cast(Any, cog.preflight.callback)(cog, ctx, attachment)

    assert run_capture.await_args is not None
    command = run_capture.await_args.args
    assert command[:2] == ("dt", "preflight")
    assert command[2].endswith("input_0.pdf")
    assert "--output" not in command
    assert "PDF report" in ctx.sent[0]["args"][0]
    assert "Warnings (1)" in ctx.sent[0]["args"][0]
    assert "failed" not in ctx.sent[0]["args"][0]


@pytest.mark.anyio
async def test_split_sends_each_generated_tile():
    cog = Delphitools(bot=MagicMock())
    attachment = MagicMock(filename="sample.png", content_type="image/png")
    ctx = MockContext(message=MagicMock())

    async def run_cli(*command: str, timeout: int) -> tuple[int, str]:
        output_dir = Path(command[command.index("--output") + 1])
        (output_dir / "tile-1.png").write_bytes(b"tile-one")
        (output_dir / "tile-2.png").write_bytes(b"tile-two")
        return 0, ""

    with (
        patch(
            "cogs.conversion.delphitools.extract_attachments",
            new=AsyncMock(return_value=[(b"image-data", "image/png")]),
        ),
        patch(
            "cogs.conversion.delphitools._run_capture", side_effect=run_cli
        ) as run_capture,
    ):
        await cast(Any, cog.split.callback)(cog, ctx, attachment, 1, 2)

    assert run_capture.await_args is not None
    command = run_capture.await_args.args
    assert command[:2] == ("dt", "split")
    assert command[3:7] == ("--rows", "1", "--cols", "2")
    assert command[7] == "--output"
    assert ctx.sent[0]["uploaded_files"] == [
        ("tile-1.png", b"tile-one"),
        ("tile-2.png", b"tile-two"),
    ]


@pytest.mark.anyio
async def test_decode_uses_cli_positional_arguments():
    cog = Delphitools(bot=MagicMock())
    ctx = MockContext()

    with patch(
        "cogs.conversion.delphitools._run_capture",
        new=AsyncMock(return_value=(0, "hello")),
    ) as run_capture:
        await cast(Any, cog.decode.callback)(cog, ctx, "aGVsbG8=", "base64")

    run_capture.assert_awaited_once_with(
        "dt", "decode", "base64", "aGVsbG8=", timeout=300
    )


@pytest.mark.anyio
async def test_hash_uses_cli_positional_arguments():
    cog = Delphitools(bot=MagicMock())
    ctx = MockContext()

    with patch(
        "cogs.conversion.delphitools._run_capture",
        new=AsyncMock(return_value=(0, "digest")),
    ) as run_capture:
        await cast(Any, cog.hash.callback)(cog, ctx, "hello", "sha256")

    run_capture.assert_awaited_once_with(
        "dt", "hash", "sha256", "hello", timeout=300
    )


@pytest.mark.anyio
async def test_watermark_uses_two_images_and_supported_cli_options():
    cog = Delphitools(bot=MagicMock())
    base_image = MagicMock(
        filename="base.png",
        content_type="image/png",
    )
    mark_image = MagicMock(
        filename="mark.png",
        content_type="image/png",
    )
    ctx = MockContext(message=MagicMock(attachments=[]))

    async def run_cli(*command: str, timeout: int) -> tuple[int, str]:
        output_path = Path(command[command.index("--output") + 1])
        output_path.write_bytes(b"watermarked-image")
        return 0, ""

    with (
        patch(
            "cogs.conversion.delphitools.extract_attachments",
            new=AsyncMock(
                return_value=[
                    (b"base-image", "image/png"),
                    (b"mark-image", "image/png"),
                ]
            ),
        ) as extract,
        patch(
            "cogs.conversion.delphitools._run_capture", side_effect=run_cli
        ) as run_capture,
    ):
        await cast(Any, cog.watermark.callback)(
            cog, ctx, base_image, mark_image, 0.5, "center"
        )

    call = run_capture.await_args
    assert call is not None
    command = call.args
    assert command[:2] == ("dt", "watermark")
    assert command[2].endswith("input.png")
    assert command[3] == "--mark"
    assert command[4].endswith("mark.png")
    assert command[5] == "--output"
    assert command[6].endswith("watermarked_base.png")
    assert command[7:] == (
        "--opacity",
        "0.5",
        "--position",
        "center",
        "--scale",
        "0.2",
    )
    assert call.kwargs == {"timeout": 300}
    assert ctx.sent[0]["uploaded_bytes"] == b"watermarked-image"
    extract.assert_awaited_once_with(ctx.message, base_image, mark_image)


@pytest.mark.anyio
async def test_colorblind_all_runs_four_simulations_and_sends_all_images():
    cog = Delphitools(bot=MagicMock())
    simulation_types = (
        "protanopia",
        "deuteranopia",
        "tritanopia",
        "achromatopsia",
    )
    commands: list[tuple[str, ...]] = []

    async def run_cli(*command: str, timeout: int) -> tuple[int, str]:
        assert command[:2] == ("dt", "colorblind")
        assert command[2].endswith("input.png")
        assert command[3] == "--output"
        simulation_type = command[-1]
        assert command[4].endswith(f"colorblind_{simulation_type}_sample.png")
        assert command[5:] == ("--cb-type", simulation_type)
        assert simulation_type in simulation_types
        commands.append(command)
        Path(command[4]).write_bytes(b"simulated-image")
        return 0, ""

    with patch(
        "cogs.conversion.delphitools._run_capture", side_effect=run_cli
    ) as run_capture:
        attachment = MagicMock(
            filename="sample.png",
            content_type="image/png",
        )
        ctx = MockContext(message=MagicMock())

        with patch(
            "cogs.conversion.delphitools.extract_attachments",
            new=AsyncMock(return_value=[(b"image-data", "image/png")]),
        ) as extract:
            await cast(Any, cog.colorblind.callback)(
                cog, ctx, "all", attachment
            )

        extract.assert_awaited_once_with(ctx.message, attachment)
        assert len(ctx.sent) == 1
        assert ctx.sent[0]["content"].startswith(
            "✅ **All simulations done in "
        )
        assert ctx.sent[0]["uploaded_files"] == [
            (
                f"colorblind_{simulation_type}_sample.png",
                b"simulated-image",
            )
            for simulation_type in simulation_types
        ]

    assert len(commands) == len(simulation_types)
    assert [command[-1] for command in commands] == list(simulation_types)
    assert all(command[5] == "--cb-type" for command in commands)
    assert all(
        call.kwargs == {"timeout": 300} for call in run_capture.await_args_list
    )


def test_discord_choices_only_include_cli_supported_values():
    commands = {
        command.name: command
        for command in Delphitools(bot=MagicMock()).get_commands()
    }

    def choices(command_name: str, parameter_name: str) -> set[str]:
        app_command = cast(Any, commands[command_name]).app_command
        parameter = next(
            parameter
            for parameter in app_command.parameters
            if parameter.name == parameter_name
        )
        return {choice.value for choice in parameter.choices}

    assert choices("palette", "format") == {"png"}
    assert choices("palette", "strategy") == {
        "analogous",
        "complementary",
        "triadic",
        "monochromatic",
        "true-random",
        "random-cohesive",
    }
    assert choices("barcodegen", "type") == {"code128", "ean13"}
    assert choices("colorblind", "type") == {
        "protanopia",
        "deuteranopia",
        "tritanopia",
        "achromatopsia",
        "all",
    }
    assert choices("encode", "encoding") == {"base64", "url"}
    assert choices("decode", "encoding") == {"base64", "url"}


@pytest.mark.anyio
async def test_delphitools_slash_commands_fit_in_one_tools_group():
    bot = discord_commands.Bot(
        command_prefix="~", intents=discord.Intents.none()
    )
    cog = Delphitools(bot)

    try:
        await bot.add_cog(cog)

        root_commands = bot.tree.get_commands()
        assert [command.name for command in root_commands] == ["tools"]
        assert isinstance(root_commands[0], app_commands.Group)
        slash_commands = root_commands[0].commands
        assert len(slash_commands) == 25
        assert {command.name for command in slash_commands} == {
            "barcodegen",
            "base",
            "colorblind",
            "colour",
            "contrast",
            "convert",
            "crop",
            "decode",
            "encode",
            "favicon",
            "font-info",
            "glyph",
            "harmony",
            "hash",
            "imgconvert",
            "palette",
            "paper",
            "preflight",
            "qrgen",
            "regex",
            "split",
            "time",
            "unit",
            "unitconvert",
            "watermark",
        }

        prefix_only = {
            command.name
            for command in cog.get_commands()
            if getattr(command, "app_command", None) is None
        }
        assert prefix_only == {
            "clip",
            "completions",
            "impose",
            "line-height",
            "matte",
            "meta",
            "noise",
            "px2rem",
            "rem2px",
            "rmbg",
            "scroll",
            "shavian",
            "svgo",
            "trace",
            "typo",
            "wc",
            "zine",
        }
    finally:
        await bot.close()


def test_all_delphitools_commands_have_three_second_user_cooldowns():
    commands = Delphitools(bot=MagicMock()).get_commands()
    command_names = {command.name for command in commands}

    assert command_names == {
        "barcodegen",
        "base",
        "clip",
        "colorblind",
        "colour",
        "completions",
        "contrast",
        "convert",
        "crop",
        "decode",
        "encode",
        "favicon",
        "font-info",
        "glyph",
        "harmony",
        "hash",
        "imgconvert",
        "impose",
        "line-height",
        "matte",
        "meta",
        "noise",
        "palette",
        "paper",
        "preflight",
        "px2rem",
        "qrgen",
        "regex",
        "rem2px",
        "rmbg",
        "scroll",
        "shavian",
        "split",
        "svgo",
        "time",
        "trace",
        "typo",
        "unit",
        "unitconvert",
        "watermark",
        "wc",
        "zine",
    }

    for command in commands:
        buckets = command._buckets
        assert buckets is not None
        cooldown = buckets._cooldown
        assert cooldown is not None
        assert cooldown.per == 3
        assert cooldown.rate == 1
        assert buckets.type == discord_commands.BucketType.user


@pytest.mark.anyio
async def test_encode_reports_cli_failure_details():
    cog = Delphitools(bot=MagicMock())
    ctx = MockContext()

    with patch(
        "cogs.conversion.delphitools._run_capture",
        new=AsyncMock(return_value=(2, "unsupported encoding")),
    ):
        await cast(Any, cog.encode.callback)(cog, ctx, "abc", "base64")

    assert len(ctx.sent) == 2
    assert "exited with code 2" in ctx.sent[0]["args"][0]
    assert ctx.sent[1]["args"] == ("Error details: `unsupported encoding`",)


@pytest.mark.anyio
async def test_encode_reports_subprocess_timeout():
    cog = Delphitools(bot=MagicMock())
    ctx = MockContext()

    with patch(
        "cogs.conversion.delphitools._run_capture",
        new=AsyncMock(side_effect=asyncio.TimeoutError),
    ):
        await cast(Any, cog.encode.callback)(cog, ctx, "abc", "base64")

    assert ctx.sent == [{"args": ("❌ **Encode timed out.**",)}]
