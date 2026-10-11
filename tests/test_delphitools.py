"""Tests for the delphitools Discord cog."""

import asyncio
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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
        file = kwargs.get("file")
        if file is not None:
            kwargs["uploaded_filename"] = file.filename
            kwargs["uploaded_bytes"] = file.fp.read()
            file.close()
        self.sent.append({"args": args, **kwargs})


@pytest.mark.anyio
async def test_run_capture_returns_exit_code_and_trimmed_stdout():
    process = MagicMock()
    process.communicate = AsyncMock(return_value=(b" result \n", b"ignored"))
    process.returncode = 3

    with patch(
        "cogs.conversion.delphitools.asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=process),
    ) as create_process:
        result = await _run_capture("dt", "encode", "--input", "abc", timeout=7)

    assert result == (3, "result")
    create_process.assert_awaited_once_with(
        "dt",
        "encode",
        "--input",
        "abc",
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
        await _run_capture("dt", "encode", "--input", "abc", timeout=1)

    process.kill.assert_called_once_with()
    assert process.communicate.await_count == 2


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
        "dt", "encode", "--type", "base64", "--input", "abc", timeout=300
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
        output_path = Path(command[3])
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
    assert command[3].endswith("output.webp")
    assert command[4:] == ("--resize", "640")
    assert call.kwargs == {"timeout": 300}
    assert len(ctx.sent) == 1
    assert "sample.png → output.webp" in ctx.sent[0]["content"]

    assert ctx.sent[0]["uploaded_filename"] == "output.webp"
    assert ctx.sent[0]["uploaded_bytes"] == b"converted-image"


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
