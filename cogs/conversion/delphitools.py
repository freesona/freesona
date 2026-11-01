#!/usr/bin/env python3

# cogs/conversion/delphitools.py: Delphitools CLI integration for file
# conversion


import asyncio
import io
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Callable

import discord
from discord import app_commands
from discord.ext import commands

from utils.config import load_config
from utils.discord_adapter import extract_attachments

log = logging.getLogger(__name__)

COLORBLIND_SIMULATIONS = (
    "protanopia",
    "deuteranopia",
    "tritanopia",
    "achromatopsia",
)

# The subprocess timeout and output-size limit come from config.json.


def _get_subprocess_timeout() -> int:
    return int(load_config().get("delphitools_subprocess_timeout", 300))


def _get_limit_bytes() -> int:

    return int(
        load_config().get("delphitools_limit_bytes", 10 * 1024 * 1024)
    )  # 10 MB default


def _get_delphitools_executable() -> str:
    return os.getenv("DELPHITOOLS_EXECUTABLE", "dt").strip() or "dt"


async def _run(*cmd: str, timeout: int | None = None) -> int:
    """Run a subprocess and return its exit code.

    Raises TimeoutError on timeout.
    """

    if timeout is None:
        timeout = _get_subprocess_timeout()

    if cmd and cmd[0] == "dt":
        cmd = (_get_delphitools_executable(), *cmd[1:])

    proc = await asyncio.create_subprocess_exec(*cmd)

    try:
        await asyncio.wait_for(proc.wait(), timeout=timeout)

    except asyncio.TimeoutError:
        proc.kill()

        # raise

    return_code = proc.returncode

    if return_code is None:
        raise RuntimeError("Subprocess finished without an exit code.")

    return return_code


async def _run_capture(
    *cmd: str,
    timeout: int | None = None,
    include_stdout_on_failure: bool = False,
) -> tuple[int, str]:
    """Run a subprocess and return its exit code and relevant output.

    On failure, return stderr when available so callers can report diagnostics.
    """

    if timeout is None:
        timeout = _get_subprocess_timeout()

    if cmd and cmd[0] == "dt":
        cmd = (_get_delphitools_executable(), *cmd[1:])

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as e:
        raise RuntimeError(
            "Cannot start the Delphitools CLI. Set "
            "`DELPHITOOLS_EXECUTABLE` to its executable path or add it to the "
            "bot process PATH."
        ) from e

    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )

    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        raise

    return_code = proc.returncode

    if return_code is None:
        raise RuntimeError("Subprocess finished without an exit code.")

    if return_code != 0 and stderr:
        output = (
            stdout + b"\n" + stderr
            if include_stdout_on_failure and stdout
            else stderr
        )
    else:
        output = stdout
    return return_code, output.decode().strip()


class Delphitools(
    commands.GroupCog,
    group_name="tools",
    group_description="Delphitools utilities",
):
    LIMIT_BYTES = 10 * 1024 * 1024  # 10 MB Discord upload limit

    help_category = "Tools"

    def __init__(self, bot: commands.Bot) -> None:

        self.bot = bot

    async def _run_text_cli(
        self, ctx: commands.Context, label: str, *args: str
    ) -> None:
        try:
            exit_code, output = await _run_capture(
                "dt", *args, timeout=_get_subprocess_timeout()
            )
        except asyncio.TimeoutError:
            await ctx.send(f"❌ **{label} timed out.**")
            return
        except Exception as e:
            log.exception("Error running Delphitools %s command", label)
            await ctx.send(f"❌ **{label} failed.** {e!s}")
            return

        if exit_code:
            await ctx.send(
                f"❌ **{label} failed.** delphitools exited with code "
                f"{exit_code}."
            )
            if output:
                await self._send_cli_output(
                    ctx, "Error details", output, success=False
                )
            return

        await self._send_cli_output(ctx, f"{label} result", output)

    async def _send_cli_output(
        self,
        ctx: commands.Context,
        label: str,
        output: str,
        *,
        success: bool = True,
    ) -> None:
        marker = "✅ " if success else ""
        content = f"{marker}**{label}**"
        if output:
            content = f"{content}\n{output}"

        if len(content) <= 1900:
            await ctx.send(
                content,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return

        await ctx.send(
            content=f"✅ **{label}** (full output attached)",
            file=discord.File(
                io.BytesIO(output.encode("utf-8")),
                filename=f"{label.lower().replace(' ', '-')}.txt",
            ),
            allowed_mentions=discord.AllowedMentions.none(),
        )

    async def _run_file_cli(
        self,
        ctx: commands.Context,
        label: str,
        command: str,
        attachments: list[discord.Attachment],
        build_args: Callable[[list[Path]], list[str]],
        *,
        output_files: bool = True,
        output_directory: bool = False,
        output_extension: str | None = None,
        success_exit_codes: tuple[int, ...] = (0,),
        include_stdout_on_failure: bool = False,
        minimum_files: int = 1,
        maximum_outputs: int = 10,
    ) -> None:
        selected_attachments = attachments or list(
            getattr(ctx.message, "attachments", [])
        )
        if len(selected_attachments) < minimum_files:
            await ctx.send(
                f"Attach at least {minimum_files} file"
                f"{'s' if minimum_files != 1 else ''}."
            )
            return

        async with ctx.typing():
            try:
                payloads = await extract_attachments(
                    ctx.message, *selected_attachments
                )
                if len(payloads) < minimum_files:
                    await ctx.send("Failed to read the attached file(s).")
                    return

                with tempfile.TemporaryDirectory() as tmp_dir:
                    tmp_path = Path(tmp_dir)
                    input_paths: list[Path] = []
                    for index, (attachment, (data, _mime)) in enumerate(
                        zip(
                            selected_attachments,
                            payloads,
                            strict=False,
                        )
                    ):
                        if len(data) > self.LIMIT_BYTES:
                            await ctx.send(
                                f"❌ **{label} failed.** "
                                f"{attachment.filename} exceeds the "
                                "10 MB input limit."
                            )
                            return
                        suffix = Path(attachment.filename).suffix[:16]
                        input_path = tmp_path / f"input_{index}{suffix}"
                        await asyncio.to_thread(input_path.write_bytes, data)
                        input_paths.append(input_path)

                    output_path = (
                        tmp_path / "output"
                        if output_directory
                        else tmp_path
                        / f"result{output_extension or input_paths[0].suffix}"
                    )
                    args = [
                        "dt",
                        command,
                        *build_args(input_paths),
                    ]
                    if output_files:
                        if output_directory:
                            output_path.mkdir()
                        args.extend(["--output", str(output_path)])

                    if include_stdout_on_failure:
                        exit_code, output = await _run_capture(
                            *args,
                            timeout=_get_subprocess_timeout(),
                            include_stdout_on_failure=True,
                        )
                    else:
                        exit_code, output = await _run_capture(
                            *args, timeout=_get_subprocess_timeout()
                        )
                    if exit_code not in success_exit_codes:
                        await ctx.send(
                            f"❌ **{label} failed.** delphitools exited "
                            f"with code {exit_code}."
                        )
                        if output:
                            await self._send_cli_output(
                                ctx, "Error details", output, success=False
                            )
                        return

                    if not output_files:
                        await self._send_cli_output(
                            ctx,
                            f"{label} result",
                            output,
                            success=exit_code == 0,
                        )
                        return

                    results = (
                        sorted(
                            path
                            for path in output_path.rglob("*")
                            if path.is_file()
                        )
                        if output_directory
                        else [output_path]
                        if output_path.is_file()
                        else []
                    )
                    if not results:
                        await ctx.send(
                            f"❌ **{label} failed.** No output files were "
                            "generated."
                        )
                        return
                    if len(results) > maximum_outputs:
                        await ctx.send(
                            f"❌ **{label} failed.** The operation produced "
                            f"{len(results)} files; the limit is "
                            f"{maximum_outputs}."
                        )
                        return
                    oversized = [
                        path.name
                        for path in results
                        if path.stat().st_size > self.LIMIT_BYTES
                    ]
                    if oversized:
                        await ctx.send(
                            f"❌ **{label} failed.** Output exceeds the "
                            f"10 MB upload limit: {', '.join(oversized)}"
                        )
                        return

                    await ctx.send(
                        content=f"✅ **{label} completed.**",
                        files=[discord.File(str(path)) for path in results],
                    )
            except asyncio.TimeoutError:
                await ctx.send(f"❌ **{label} timed out.**")
            except Exception as e:
                log.exception("Error running Delphitools %s command", label)
                await ctx.send(f"❌ **{label} failed.** {e!s}")

    # ------------------------------------------------------------------

    # Internal helpers

    # ------------------------------------------------------------------

    # ------------------------------------------------------------------

    # Commands

    # ------------------------------------------------------------------

    @commands.hybrid_command(
        name="colour",
        description="Convert a colour between common colour formats.",
        help=(
            "Convert a colour such as `#ff6600` to one or more formats. "
            "Example: `colour #ff6600 hex,rgb,oklch`."
        ),
        usage="<colour> [formats]",
    )
    @app_commands.describe(
        colour="Hex, RGB, HSL, OKLCH, OKLAB, or CSS colour name",
        formats="Optional comma-separated output formats",
    )
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def colour(
        self,
        ctx: commands.Context,
        colour: str,
        formats: str | None = None,
    ) -> None:
        args = ["colour", colour]
        if formats:
            args.extend(
                part.strip() for part in formats.split(",") if part.strip()
            )
        await self._run_text_cli(ctx, "Colour", *args)

    @commands.hybrid_command(
        name="contrast",
        description="Check the WCAG contrast ratio between two colours.",
        help=(
            "Check a foreground/background colour pair for WCAG AA and AAA. "
            "Example: `contrast #ffffff #222222`."
        ),
        usage="<foreground> <background>",
    )
    @app_commands.describe(
        foreground="Foreground text colour",
        background="Background colour",
    )
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def contrast(
        self, ctx: commands.Context, foreground: str, background: str
    ) -> None:
        await self._run_text_cli(
            ctx, "Contrast", "contrast", foreground, background
        )

    @commands.hybrid_command(
        name="harmony",
        description="Generate a colour harmony from a base colour.",
        help=(
            "Generate related colours from a base colour. "
            "Example: `harmony #ff6600 complementary`."
        ),
        usage="<colour> [harmony_type]",
    )
    @app_commands.describe(
        colour="Base colour",
        harmony_type="Optional harmony strategy, such as complementary",
    )
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def harmony(
        self,
        ctx: commands.Context,
        colour: str,
        harmony_type: str | None = None,
    ) -> None:
        args = ["harmony", colour]
        if harmony_type:
            args.append(harmony_type)
        await self._run_text_cli(ctx, "Harmony", *args)

    @commands.hybrid_command(
        name="regex",
        description="Test a regular expression against text.",
        help=(
            "Test a Rust-compatible regular expression against text. "
            "Flags are letters: `g` all matches, `i` ignore case, "
            "`m` multiline, `s` dot-all, `x` extended. "
            'Example: `regex "\\\\d{3}-\\\\d{4}" '
            '"phone: 555-1234"`.'
        ),
        usage="<pattern> <text> [flags]",
    )
    @app_commands.describe(
        pattern="Rust regex pattern",
        text="Text to test",
        flags="Optional flags: g, i, m, s, x",
    )
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def regex(
        self,
        ctx: commands.Context,
        pattern: str,
        text: str,
        flags: str | None = None,
    ) -> None:
        args = ["regex", pattern]
        args.append(text)
        if flags:
            args.extend(["--flags", flags])
        await self._run_text_cli(ctx, "Regex", *args)

    @commands.hybrid_command(
        name="base",
        description=(
            "Convert a number between decimal, hexadecimal, octal, and binary."
        ),
        help=(
            "Convert a number between bases. Example: `base 255 hex`."
        ),
        usage="<value> [targets] [from_base]",
    )
    @app_commands.describe(
        value="Number to convert",
        targets="Optional comma-separated targets: dec, hex, oct, bin",
        from_base="Optional source base: auto, dec, hex, oct, bin",
    )
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def base(
        self,
        ctx: commands.Context,
        value: str,
        targets: str | None = None,
        from_base: str = "auto",
    ) -> None:
        args = ["base", value]
        if targets:
            args.extend(
                part.strip() for part in targets.split(",") if part.strip()
            )
        if from_base != "auto":
            args.extend(["--from", from_base])
        await self._run_text_cli(ctx, "Base conversion", *args)

    @commands.hybrid_command(
        name="time",
        description="Convert a timestamp or perform date arithmetic.",
        help=(
            "Convert a timestamp or date, optionally changing timezone or "
            "adding/subtracting a duration. Example: "
            "`time 2026-01-01 UTC 30d`."
        ),
        usage="[input] [timezone] [add] [subtract] [formats]",
    )
    @app_commands.describe(
        input="Date or Unix timestamp (defaults to now)",
        timezone="IANA timezone, for example America/New_York",
        add="Duration to add, for example 30d or 5h",
        subtract="Duration to subtract",
        formats="Optional comma-separated outputs: iso, unix, human, etc.",
    )
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def time(
        self,
        ctx: commands.Context,
        input: str | None = None,
        timezone: str | None = None,
        add: str | None = None,
        subtract: str | None = None,
        formats: str | None = None,
    ) -> None:
        args = ["time"]
        if input is not None:
            args.append(input)
        if timezone:
            args.extend(["--tz", timezone])
        if add:
            args.extend(["--add", add])
        if subtract:
            args.extend(["--sub", subtract])
        if formats:
            args.extend(["--to", formats])
        await self._run_text_cli(ctx, "Time", *args)

    @commands.hybrid_command(
        with_app_command=False,
        name="wc",
        description="Count words, characters, sentences, and reading time.",
        help=(
            "Count words, characters, sentences, and estimated reading time. "
            'Example: `wc "The quick brown fox."`.'
        ),
        usage="<text>",
    )
    @app_commands.describe(text="Text to analyse")
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def wc(self, ctx: commands.Context, text: str) -> None:
        await self._run_text_cli(ctx, "Text statistics", "wc", text)

    @commands.hybrid_command(
        name="paper",
        description="Look up standard paper dimensions.",
        help=(
            "Look up a paper size such as A4 or Letter. "
            "Example: `paper A4`."
        ),
        usage="[name] [unit] [series] [pixels] [dpi]",
    )
    @app_commands.describe(
        name="Paper size, for example A4 or Letter",
        unit="Output unit (default: mm)",
        series="Optional paper series",
        pixels="Show pixel dimensions",
        dpi="DPI used for pixel dimensions",
    )
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def paper(
        self,
        ctx: commands.Context,
        name: str | None = None,
        unit: str = "mm",
        series: str | None = None,
        pixels: bool = False,
        dpi: int = 72,
    ) -> None:
        args = ["paper"]
        if name:
            args.append(name)
        if unit != "mm":
            args.extend(["--unit", unit])
        if series:
            args.extend(["--series", series])
        if pixels:
            args.append("--pixels")
        if dpi != 72:
            args.extend(["--dpi", str(dpi)])
        await self._run_text_cli(ctx, "Paper size", *args)

    @commands.hybrid_command(
        name="glyph",
        description="Look up Unicode characters by codepoint or name.",
        help=(
            "Look up a Unicode codepoint, search character names, or list a "
            "range. Example: `glyph U+2603`."
        ),
        usage="[input] [search] [range] [limit]",
    )
    @app_commands.describe(
        input="Character or codepoint such as U+2603",
        search="Search Unicode character names",
        range="Named Unicode range, such as arrows or greek",
        limit="Maximum number of search results",
    )
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def glyph(
        self,
        ctx: commands.Context,
        input: str | None = None,
        search: str | None = None,
        range: str | None = None,
        limit: int = 50,
    ) -> None:
        if not input and not search and not range:
            await ctx.send("Provide a codepoint, a name search, or a range.")
            return
        args = ["glyph"]
        if input:
            args.append(input)
        if search:
            args.extend(["--search", search])
        if range:
            args.extend(["--range", range])
        if limit != 50:
            args.extend(["--limit", str(limit)])
        await self._run_text_cli(ctx, "Glyph lookup", *args)

    @commands.hybrid_command(
        with_app_command=False,
        name="px2rem",
        description="Convert CSS pixels to rem.",
        help=(
            "Convert a pixel value to rem, using a 16px base by default. "
            "Example: `px2rem 24 16`."
        ),
        usage="<value> [base]",
    )
    @app_commands.describe(
        value="Pixel value", base="Root font size in pixels"
    )
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def px2rem(
        self, ctx: commands.Context, value: str, base: float = 16.0
    ) -> None:
        args = ["px2rem", value]
        if base != 16:
            args.extend(["--base", str(base)])
        await self._run_text_cli(ctx, "px to rem", *args)

    @commands.hybrid_command(
        with_app_command=False,
        name="rem2px",
        description="Convert CSS rem to pixels.",
        help=(
            "Convert a rem value to pixels, using a 16px base by default. "
            "Example: `rem2px 1.5 16`."
        ),
        usage="<value> [base]",
    )
    @app_commands.describe(value="Rem value", base="Root font size in pixels")
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def rem2px(
        self, ctx: commands.Context, value: str, base: float = 16.0
    ) -> None:
        args = ["rem2px", value]
        if base != 16:
            args.extend(["--base", str(base)])
        await self._run_text_cli(ctx, "rem to px", *args)

    @commands.hybrid_command(
        with_app_command=False,
        name="line-height",
        description="Compute line-height values for a font size.",
        help=(
            "Calculate line-height suggestions for a font size. "
            "Example: `line-height 16`."
        ),
        usage="[font_size] [name]",
    )
    @app_commands.describe(
        font_size="Font size in pixels",
        name="Optional type scale or font name",
    )
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def line_height(
        self,
        ctx: commands.Context,
        font_size: str | None = None,
        name: str | None = None,
    ) -> None:
        args = ["line-height"]
        if font_size:
            args.append(font_size)
        if name:
            args.append(name)
        await self._run_text_cli(ctx, "Line height", *args)

    @commands.hybrid_command(
        with_app_command=False,
        name="typo",
        description="Convert typographic measurements.",
        help=(
            "Convert values between pt, px, mm, em, rem, pc, in, and cm. "
            "Example: `typo 12pt px,mm`."
        ),
        usage="<value> [targets] [base]",
    )
    @app_commands.describe(
        value="Value with a unit, such as 12pt",
        targets="Optional comma-separated target units",
        base="Base font size for em/rem calculations",
    )
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def typo(
        self,
        ctx: commands.Context,
        value: str,
        targets: str | None = None,
        base: float = 16.0,
    ) -> None:
        args = ["typo", value]
        if targets:
            args.extend(
                part.strip() for part in targets.split(",") if part.strip()
            )
        if base != 16:
            args.extend(["--base", str(base)])
        await self._run_text_cli(ctx, "Typography conversion", *args)

    @commands.hybrid_command(
        with_app_command=False,
        name="shavian",
        description="Transliterate English text to the Shavian alphabet.",
        help=(
            "Convert English text to the Shavian alphabet. "
            'Example: `shavian "Hello world"`.'
        ),
        usage="<text> [gloss]",
    )
    @app_commands.describe(
        text="English text", gloss="Include Latin and IPA gloss"
    )
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def shavian(
        self, ctx: commands.Context, text: str, gloss: bool = False
    ) -> None:
        args = ["shavian", text]
        if gloss:
            args.append("--gloss")
        await self._run_text_cli(ctx, "Shavian transliteration", *args)

    @commands.hybrid_command(
        with_app_command=False,
        name="meta",
        description="Generate HTML social-sharing meta tags.",
        help=(
            "Generate HTML title, description, and social-sharing tags. "
            'Example: `meta "My page" "A page description"`.'
        ),
        usage="<title> <description> [url] [image]",
    )
    @app_commands.describe(
        title="Page title",
        description="Page description",
        url="Canonical page URL",
        image="Social preview image URL",
    )
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def meta(
        self,
        ctx: commands.Context,
        title: str,
        description: str,
        url: str | None = None,
        image: str | None = None,
    ) -> None:
        args = ["meta", "--title", title, "--description", description]
        if url:
            args.extend(["--url", url])
        if image:
            args.extend(["--image", image])
        await self._run_text_cli(ctx, "Meta tags", *args)

    @commands.hybrid_command(
        with_app_command=False,
        name="completions",
        description="Generate a shell completion script for Delphitools.",
        help=(
            "Generate a completion script you can download and install in "
            "your local shell. Example: `completions powershell`."
        ),
        usage="<shell>",
    )
    @app_commands.describe(shell="Shell to generate completions for")
    @app_commands.choices(
        shell=[
            app_commands.Choice(name="Bash", value="bash"),
            app_commands.Choice(name="Elvish", value="elvish"),
            app_commands.Choice(name="Fish", value="fish"),
            app_commands.Choice(name="PowerShell", value="powershell"),
            app_commands.Choice(name="Zsh", value="zsh"),
        ]
    )
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def completions(self, ctx: commands.Context, shell: str) -> None:
        try:
            exit_code, output = await _run_capture(
                "dt", "completions", shell, timeout=_get_subprocess_timeout()
            )
        except asyncio.TimeoutError:
            await ctx.send("❌ **Shell completions timed out.**")
            return
        except Exception as e:
            log.exception("Error generating Delphitools shell completions")
            await ctx.send(f"❌ **Shell completions failed.** {e!s}")
            return

        if exit_code:
            await ctx.send(
                "❌ **Shell completions failed.** delphitools exited with "
                f"code {exit_code}."
            )
            if output:
                await self._send_cli_output(
                    ctx, "Error details", output, success=False
                )
            return
        if not output:
            await ctx.send(
                "❌ **Shell completions failed.** No script output."
            )
            return
        if len(output.encode("utf-8")) > self.LIMIT_BYTES:
            await ctx.send(
                "❌ **Shell completions failed.** The script exceeds the "
                "10 MB upload limit."
            )
            return

        extension = {
            "bash": "bash",
            "elvish": "elv",
            "fish": "fish",
            "powershell": "ps1",
            "zsh": "zsh",
        }[shell]
        await ctx.send(
            content=(
                "✅ **Shell completion script generated.** "
                "Download it and install it in your local shell."
            ),
            file=discord.File(
                io.BytesIO(output.encode("utf-8")),
                filename=f"delphitools-completions.{extension}",
            ),
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @commands.hybrid_command(
        name="crop",
        description="Crop an image to an aspect ratio.",
        help=(
            "Crop an attached image to an aspect ratio such as 1:1 or 16:9. "
            "Example: `crop 1:1` with an image attached."
        ),
        usage="<ratio> [position] (attach image)",
    )
    @app_commands.describe(
        attachment="Image to crop",
        ratio="Aspect ratio, such as 1:1 or 4:5",
        position="Crop position",
    )
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def crop(
        self,
        ctx: commands.Context,
        attachment: discord.Attachment | None = None,
        ratio: str = "1:1",
        position: str = "center",
    ) -> None:
        await self._run_file_cli(
            ctx,
            "Crop",
            "crop",
            [attachment] if attachment else [],
            lambda paths: [
                *map(str, paths),
                "--ratio",
                ratio,
                "--position",
                position,
            ],
        )

    @commands.hybrid_command(
        with_app_command=False,
        name="matte",
        description="Place an image on a square or aspect-ratio matte.",
        help=(
            "Fit an image onto a matte using blur, solid colour, or gradient. "
            "Example: `matte 1:1 blur` with an image attached."
        ),
        usage="[ratio] [mode] [colour] (attach image)",
    )
    @app_commands.describe(
        attachment="Image to place on the matte",
        ratio="Target aspect ratio",
        mode="Matte fill mode: solid, blur, or gradient",
        colour="Matte colour when mode is solid",
    )
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def matte(
        self,
        ctx: commands.Context,
        attachment: discord.Attachment | None = None,
        ratio: str = "1:1",
        mode: str = "blur",
        colour: str = "#ffffff",
    ) -> None:
        await self._run_file_cli(
            ctx,
            "Matte",
            "matte",
            [attachment] if attachment else [],
            lambda paths: [
                *map(str, paths),
                "--ratio",
                ratio,
                "--mode",
                mode,
                "--colour",
                colour,
            ],
            output_directory=True,
        )

    @commands.hybrid_command(
        with_app_command=False,
        name="scroll",
        description="Split a wide image into social carousel tiles.",
        help=(
            "Split a wide image into carousel tiles. "
            "Example: `scroll 4:5` with an image attached."
        ),
        usage="[ratio] [fill] [colour] (attach image)",
    )
    @app_commands.describe(
        attachment="Wide image to split",
        ratio="Tile aspect ratio (default: 4:5)",
        fill="Letterbox fill: blur or colour",
        colour="Letterbox colour",
    )
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def scroll(
        self,
        ctx: commands.Context,
        attachment: discord.Attachment | None = None,
        ratio: str = "4:5",
        fill: str = "blur",
        colour: str = "#ffffff",
    ) -> None:
        await self._run_file_cli(
            ctx,
            "Carousel split",
            "scroll",
            [attachment] if attachment else [],
            lambda paths: [
                *map(str, paths),
                "--ratio",
                ratio,
                "--fill",
                fill,
                "--colour",
                colour,
            ],
        )

    @commands.hybrid_command(
        name="favicon",
        description="Generate favicon files from an image.",
        help=(
            "Generate standard favicon sizes from an attached image. "
            "Example: `favicon` with an image attached. Use slash "
            "options to select sizes or include favicon.ico."
        ),
        usage="[sizes] [ico] (attach image)",
    )
    @app_commands.describe(
        attachment="Source image",
        sizes="Comma-separated output sizes (default: 16,32,48,180,512)",
        ico="Also create a multi-size favicon.ico",
    )
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def favicon(
        self,
        ctx: commands.Context,
        attachment: discord.Attachment | None = None,
        sizes: str = "16,32,48,180,512",
        ico: bool = False,
    ) -> None:
        def build(paths: list[Path]) -> list[str]:
            args = [str(paths[0]), "--sizes", sizes]
            if ico:
                args.append("--ico")
            return args

        await self._run_file_cli(
            ctx,
            "Favicon generation",
            "favicon",
            [attachment] if attachment else [],
            build,
            output_directory=True,
            maximum_outputs=10,
        )

    @commands.hybrid_command(
        with_app_command=False,
        name="svgo",
        description="Optimise an attached SVG file.",
        help=(
            "Optimise an SVG file and return the optimised result. "
            "Example: `svgo` with an SVG attached."
        ),
        usage="(attach SVG file)",
    )
    @app_commands.describe(attachment="SVG file to optimise")
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def svgo(
        self,
        ctx: commands.Context,
        attachment: discord.Attachment | None = None,
    ) -> None:
        await self._run_file_cli(
            ctx,
            "SVG optimisation",
            "svgo",
            [attachment] if attachment else [],
            lambda paths: list(map(str, paths)),
            output_extension=".svg",
        )

    @commands.hybrid_command(
        name="split",
        description="Split an image into a grid of tiles.",
        help=(
            "Split an image into a grid of up to 10 tiles. "
            "Example: `split 2 2` with an image attached."
        ),
        usage="<rows> <columns> (attach image)",
    )
    @app_commands.describe(
        attachment="Image to split",
        rows="Number of tile rows",
        columns="Number of tile columns",
    )
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def split(
        self,
        ctx: commands.Context,
        attachment: discord.Attachment | None = None,
        rows: int = 1,
        columns: int = 1,
    ) -> None:
        if rows < 1 or columns < 1 or rows * columns > 10:
            await ctx.send("The grid must produce between 1 and 10 tiles.")
            return
        await self._run_file_cli(
            ctx,
            "Image split",
            "split",
            [attachment] if attachment else [],
            lambda paths: [
                str(paths[0]),
                "--rows",
                str(rows),
                "--cols",
                str(columns),
            ],
            output_directory=True,
            maximum_outputs=10,
        )

    @commands.hybrid_command(
        name="convert",
        description="Convert an attached image and optionally resize it.",
        help=(
            "Convert an attached image to a different format, with optional "
            "resize. JPEG quality is configurable; WebP output is lossless. "
            "Example: `convert webp 800x` with an image attached."
        ),
        usage="<format> [resize] [quality] (attach image)",
    )
    @app_commands.describe(
        attachment="Image to convert",
        format="Target image format",
        resize='Optional resize, such as "800x600", "800x", or "50%"',
        quality="JPEG quality from 1 to 100 (WebP is lossless)",
    )
    @app_commands.choices(
        format=[
            app_commands.Choice(name="PNG", value="png"),
            app_commands.Choice(name="JPEG", value="jpeg"),
            app_commands.Choice(name="WebP", value="webp"),
            app_commands.Choice(name="GIF", value="gif"),
            app_commands.Choice(name="TIFF", value="tiff"),
            app_commands.Choice(name="BMP", value="bmp"),
            app_commands.Choice(name="ICO", value="ico"),
        ]
    )
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def convert(
        self,
        ctx: commands.Context,
        format: str,
        attachment: discord.Attachment | None = None,
        resize: str | None = None,
        quality: int = 85,
    ) -> None:
        if not 1 <= quality <= 100:
            await ctx.send("Quality must be between 1 and 100.")
            return
        if quality != 85 and format not in {"jpeg", "jpg"}:
            await ctx.send(
                "Quality can only be customized for JPEG; WebP is lossless."
            )
            return

        def build(paths: list[Path]) -> list[str]:
            args = [str(paths[0]), "--to", format]
            if format in {"jpeg", "jpg"}:
                args.extend(["--quality", str(quality)])
            if resize:
                args.extend(["--resize", resize])
            return args

        await self._run_file_cli(
            ctx,
            "Image conversion",
            "convert",
            [attachment] if attachment else [],
            build,
            output_extension=f".{format}",
        )

    @commands.hybrid_command(
        with_app_command=False,
        name="noise",
        description="Add a colour-noise overlay to an image.",
        help=(
            "Add a subtle grain/noise overlay to an image. "
            "Example: `noise 0.15 1.0` with an image attached."
        ),
        usage="[opacity] [scale] [seed] (attach image)",
    )
    @app_commands.describe(
        attachment="Image to modify",
        opacity="Noise opacity between 0 and 1",
        scale="Noise scale (1.0 is approximately 1px grain)",
        seed="Optional seed for reproducible output",
    )
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def noise(
        self,
        ctx: commands.Context,
        attachment: discord.Attachment | None = None,
        opacity: float = 0.15,
        scale: float = 1.0,
        seed: int | None = None,
    ) -> None:
        if not 0 <= opacity <= 1 or scale <= 0:
            await ctx.send("Opacity must be 0–1 and scale must be positive.")
            return

        def build(paths: list[Path]) -> list[str]:
            args = [
                str(paths[0]),
                "--opacity",
                str(opacity),
                "--scale",
                str(scale),
            ]
            if seed is not None:
                args.extend(["--seed", str(seed)])
            return args

        await self._run_file_cli(
            ctx,
            "Noise overlay",
            "noise",
            [attachment] if attachment else [],
            build,
            output_extension=".png",
        )

    @commands.hybrid_command(
        with_app_command=False,
        name="rmbg",
        description="Remove the background from an attached image.",
        help=(
            "Remove an image background. The first use downloads a roughly "
            "170 MB model to the bot host. "
            "Example: `rmbg` with an image attached."
        ),
        usage="(attach image; first run downloads a model)",
    )
    @app_commands.describe(attachment="Image to remove the background from")
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def rmbg(
        self,
        ctx: commands.Context,
        attachment: discord.Attachment | None = None,
    ) -> None:
        await self._run_file_cli(
            ctx,
            "Background removal",
            "rmbg",
            [attachment] if attachment else [],
            lambda paths: [*map(str, paths), "--approve"],
            output_extension=".png",
        )

    @commands.hybrid_command(
        with_app_command=False,
        name="trace",
        description="Trace a raster image into an SVG.",
        help=(
            "Convert a raster image to a vector SVG. "
            "Example: `trace detailed` with an image attached."
        ),
        usage="[preset] [colours] [blur] (attach image)",
    )
    @app_commands.describe(
        attachment="Raster image to trace",
        preset="Tracing preset: default, detailed, or posterize",
        colours="Optional number of colours",
        blur="Pre-blur radius",
    )
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def trace(
        self,
        ctx: commands.Context,
        attachment: discord.Attachment | None = None,
        preset: str = "default",
        colours: int | None = None,
        blur: float = 0.0,
    ) -> None:
        if blur < 0:
            await ctx.send("Blur must not be negative.")
            return

        def build(paths: list[Path]) -> list[str]:
            args = [str(paths[0]), "--preset", preset, "--blur", str(blur)]
            if colours is not None:
                args.extend(["--colours", str(colours)])
            return args

        await self._run_file_cli(
            ctx,
            "Image tracing",
            "trace",
            [attachment] if attachment else [],
            build,
            output_extension=".svg",
        )

    @commands.hybrid_command(
        with_app_command=False,
        name="clip",
        description="Trim transparent edges from a PNG.",
        help=(
            "Trim transparent borders around an image. "
            "Example: `clip` with a PNG attached."
        ),
        usage="(attach PNG image)",
    )
    @app_commands.describe(attachment="PNG image to trim")
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def clip(
        self,
        ctx: commands.Context,
        attachment: discord.Attachment | None = None,
    ) -> None:
        await self._run_file_cli(
            ctx,
            "Transparent-edge trim",
            "clip",
            [attachment] if attachment else [],
            lambda paths: list(map(str, paths)),
            output_extension=".png",
        )

    @commands.hybrid_command(
        name="font-info",
        description="Extract metadata from an attached font file.",
        help=(
            "Show metadata from a TTF, OTF, WOFF, or WOFF2 font. "
            "Example: `font-info` with a font file attached."
        ),
        usage="(attach TTF/OTF/WOFF/WOFF2 file)",
    )
    @app_commands.describe(attachment="Font file to inspect")
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def font_info(
        self,
        ctx: commands.Context,
        attachment: discord.Attachment | None = None,
    ) -> None:
        await self._run_file_cli(
            ctx,
            "Font information",
            "font-info",
            [attachment] if attachment else [],
            lambda paths: [str(paths[0])],
            output_files=False,
        )

    @commands.hybrid_command(
        name="preflight",
        description="Analyse a PDF for print-readiness issues.",
        help=(
            "Check an attached PDF for print-readiness issues. "
            "Example: `preflight` with a PDF attached."
        ),
        usage="(attach PDF file)",
    )
    @app_commands.describe(attachment="PDF to analyse")
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def preflight(
        self,
        ctx: commands.Context,
        attachment: discord.Attachment | None = None,
    ) -> None:
        await self._run_file_cli(
            ctx,
            "PDF preflight",
            "preflight",
            [attachment] if attachment else [],
            lambda paths: [str(paths[0])],
            output_files=False,
            success_exit_codes=(0, 3),
            include_stdout_on_failure=True,
        )

    @commands.hybrid_command(
        with_app_command=False,
        name="impose",
        description="Prepare a PDF for booklet or n-up printing.",
        help=(
            "Impose an attached PDF for saddle-stitch, perfect-bind, or n-up "
            "printing. Example: `impose saddle-stitch` with a PDF."
        ),
        usage="[layout] [paper] (attach PDF)",
    )
    @app_commands.describe(
        attachment="PDF to impose",
        layout="saddle-stitch, perfect-bind, or n-up",
        paper="Output paper size (default: A4)",
    )
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def impose(
        self,
        ctx: commands.Context,
        attachment: discord.Attachment | None = None,
        layout: str = "saddle-stitch",
        paper: str = "a4",
    ) -> None:
        await self._run_file_cli(
            ctx,
            "PDF imposition",
            "impose",
            [attachment] if attachment else [],
            lambda paths: [
                str(paths[0]),
                "--layout",
                layout,
                "--paper",
                paper,
            ],
            output_extension=".pdf",
        )

    @commands.hybrid_command(
        with_app_command=False,
        name="zine",
        description="Arrange eight images into a single-sheet mini-zine.",
        help=(
            "Arrange exactly eight attached images into a printable "
            "single-sheet mini-zine. Example: `zine` with 8 images."
        ),
        usage="(attach exactly 8 images)",
    )
    @app_commands.describe(
        image1="First page image",
        image2="Second page image",
        image3="Third page image",
        image4="Fourth page image",
        image5="Fifth page image",
        image6="Sixth page image",
        image7="Seventh page image",
        image8="Eighth page image",
        paper="Output paper size (default: A4)",
        dpi="Raster placement DPI (default: 300)",
    )
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def zine(
        self,
        ctx: commands.Context,
        image1: discord.Attachment | None = None,
        image2: discord.Attachment | None = None,
        image3: discord.Attachment | None = None,
        image4: discord.Attachment | None = None,
        image5: discord.Attachment | None = None,
        image6: discord.Attachment | None = None,
        image7: discord.Attachment | None = None,
        image8: discord.Attachment | None = None,
        paper: str = "a4",
        dpi: int = 300,
    ) -> None:
        attachments = [
            item
            for item in (
                image1,
                image2,
                image3,
                image4,
                image5,
                image6,
                image7,
                image8,
            )
            if item is not None
        ]
        selected_attachments = attachments or list(
            getattr(ctx.message, "attachments", [])
        )
        if len(selected_attachments) != 8:
            await ctx.send("Zine layout requires exactly 8 images.")
            return
        if dpi < 1:
            await ctx.send("DPI must be a positive number.")
            return

        await self._run_file_cli(
            ctx,
            "Zine layout",
            "zine",
            selected_attachments,
            lambda paths: [
                *map(str, paths),
                "--paper",
                paper,
                "--dpi",
                str(dpi),
            ],
            output_extension=".pdf",
            minimum_files=8,
        )

    @commands.hybrid_command(
        name="imgconvert",
        description=("Convert an attached image and optionally resize it."),
        help=(
            "Convert an attached image to PNG, JPG, WebP, GIF, BMP, TIFF, "
            "or ICO. You can also set a width and height in pixels. "
            "Attach the image to the command message. "
            "Example: `imgconvert webp` with an image attached."
        ),
        usage="<format> [width] [height] (attach image)",
    )
    @app_commands.describe(
        attachment="The image to convert",
        format="Target format (png, jpg, webp, gif, bmp, tiff, ico)",
        width="Width in pixels (optional)",
        height="Height in pixels (optional)",
    )
    @app_commands.choices(
        format=[
            app_commands.Choice(name="PNG", value="png"),
            app_commands.Choice(name="JPG", value="jpg"),
            app_commands.Choice(name="WebP", value="webp"),
            app_commands.Choice(name="GIF", value="gif"),
            app_commands.Choice(name="BMP", value="bmp"),
            app_commands.Choice(name="TIFF", value="tiff"),
            app_commands.Choice(name="ICO", value="ico"),
        ]
    )
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def imgconvert(
        self,
        ctx: commands.Context,
        format: str,
        attachment: discord.Attachment | None = None,
        width: int | None = None,
        height: int | None = None,
    ) -> None:
        """Convert an image to a different format with optional resize."""

        if not attachment:
            await ctx.send("Please attach an image to convert.")

            return

        # Check if it's an image

        if (
            not attachment.content_type
            or not attachment.content_type.startswith("image/")
        ):
            await ctx.send("Please attach a valid image file.")

            return

        # Process the attachment

        async with ctx.typing():
            try:
                # Extract attachment data

                attachments = await extract_attachments(
                    ctx.message, attachment
                )

                if not attachments:
                    await ctx.send("Failed to read the attached image.")

                    return

                image_data, _mime_type = attachments[0]

                # Create a temporary directory for processing

                with tempfile.TemporaryDirectory() as tmp_dir:
                    tmp_path = Path(tmp_dir)

                    # Save the input image

                    input_file = (
                        tmp_path / f"input{Path(attachment.filename).suffix}"
                    )

                    await asyncio.to_thread(
                        Path(input_file).write_bytes, image_data
                    )

                    # Determine output filename

                    output_filename = f"output.{format}"

                    output_file = tmp_path / output_filename

                    # Build delphitools convert command

                    cmd = [
                        "dt",
                        "convert",
                        str(input_file),
                        "--to",
                        format,
                        "--output",
                        str(output_file),
                    ]

                    # Add resize parameters if provided

                    if width is not None and height is not None:
                        cmd.extend(["--resize", f"{width}x{height}"])

                    elif width is not None:
                        cmd.extend(["--resize", f"{width}x"])

                    elif height is not None:
                        cmd.extend(["--resize", f"x{height}"])

                    # Run the conversion

                    exit_code, stdout = await _run_capture(
                        *cmd, timeout=_get_subprocess_timeout()
                    )

                    if exit_code != 0:
                        await ctx.send(
                            f"❌ **Conversion failed.** delphitools exited "
                            f"with code {exit_code}."
                        )

                        if stdout:
                            await ctx.send(f"Error details: `{stdout}`")

                        return

                    # Check if output file was created

                    if not output_file.exists():
                        await ctx.send(
                            "❌ **Conversion failed.** Output file was "
                            "not generated."
                        )

                        return

                    # Check file size

                    file_size = output_file.stat().st_size

                    if file_size > self.LIMIT_BYTES:
                        await ctx.send(
                            f"⚠️ **Conversion successful but "
                            "file too large.** "
                            f"The converted image is "
                            f"{file_size / (1024 * 1024):.1f} MB, which "
                            "exceeds the "
                            f"{self.LIMIT_BYTES / (1024 * 1024):.0f} MB "
                            "Discord limit."
                        )

                        return

                    # Send the converted image

                    await ctx.send(
                        content=(
                            f"✅ **Image converted successfully** "
                            f"({attachment.filename} → {output_filename})"
                        ),
                        file=discord.File(str(output_file)),
                    )

            except asyncio.TimeoutError:
                await ctx.send(
                    "❌ **Conversion timed out.** The image conversion "
                    "took too long."
                )

            except Exception as e:
                log.exception("Error in imgconvert command")

                await ctx.send(f"❌ **Conversion failed.** {e!s}")

    @commands.hybrid_command(
        name="watermark",
        description="Overlay a watermark image onto an image.",
        help=(
            "Overlay a second image as a watermark on the first image. "
            "Set opacity and relative scale from 0.0 to 1.0. "
            "Attach the base image and watermark image to the command. "
            "Example: `watermark` with both images attached."
        ),
        usage="[opacity] [position] [scale] (attach base and watermark)",
    )
    @app_commands.describe(
        attachment="The base image",
        mark="The watermark image",
        opacity="Opacity from 0.0 to 1.0 (default: 0.3)",
        position=(
            "Position (top-left, top, top-right, left, center, right, "
            "bottom-left, bottom, bottom-right)"
        ),
        scale="Watermark scale relative to the base image (default: 0.2)",
    )
    @app_commands.choices(
        position=[
            app_commands.Choice(name="Top Left", value="top-left"),
            app_commands.Choice(name="Top", value="top"),
            app_commands.Choice(name="Top Right", value="top-right"),
            app_commands.Choice(name="Left", value="left"),
            app_commands.Choice(name="Center", value="center"),
            app_commands.Choice(name="Right", value="right"),
            app_commands.Choice(name="Bottom Left", value="bottom-left"),
            app_commands.Choice(name="Bottom", value="bottom"),
            app_commands.Choice(name="Bottom Right", value="bottom-right"),
        ]
    )
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def watermark(
        self,
        ctx: commands.Context,
        attachment: discord.Attachment | None = None,
        mark: discord.Attachment | None = None,
        opacity: float = 0.3,
        position: str = "bottom-right",
        scale: float = 0.2,
    ) -> None:
        """Overlay a watermark image onto a base image."""

        if not attachment:
            await ctx.send("Please attach a base image.")

            return

        if not mark:
            await ctx.send("Please attach a watermark image.")

            return

        if any(
            not selected.content_type
            or not selected.content_type.startswith("image/")
            for selected in (attachment, mark)
        ):
            await ctx.send("Please attach valid image files.")

            return

        # Validate opacity

        if opacity < 0.0 or opacity > 1.0:
            await ctx.send("Opacity must be between 0.0 and 1.0.")

            return
        if scale <= 0.0 or scale > 1.0:
            await ctx.send("Scale must be greater than 0 and at most 1.")
            return

        # Process the attachment

        async with ctx.typing():
            try:
                # Extract attachment data

                attachments = await extract_attachments(
                    ctx.message, attachment, mark
                )

                if len(attachments) < 2:
                    await ctx.send("Failed to read both attached images.")

                    return

                image_data, _mime_type = attachments[0]
                mark_data, _mark_mime_type = attachments[1]

                # Create a temporary directory for processing

                with tempfile.TemporaryDirectory() as tmp_dir:
                    tmp_path = Path(tmp_dir)

                    # Save the input image

                    input_file = (
                        tmp_path / f"input{Path(attachment.filename).suffix}"
                    )
                    mark_file = tmp_path / f"mark{Path(mark.filename).suffix}"

                    await asyncio.to_thread(
                        Path(input_file).write_bytes, image_data
                    )
                    await asyncio.to_thread(
                        Path(mark_file).write_bytes, mark_data
                    )

                    # Determine output filename

                    output_filename = (
                        f"watermarked_{Path(attachment.filename).stem}.png"
                    )

                    output_file = tmp_path / output_filename

                    # Build delphitools watermark command

                    cmd = [
                        "dt",
                        "watermark",
                        str(input_file),
                        "--mark",
                        str(mark_file),
                        "--output",
                        str(output_file),
                        "--opacity",
                        str(opacity),
                        "--position",
                        position,
                        "--scale",
                        str(scale),
                    ]

                    # Run the watermark command

                    exit_code, stdout = await _run_capture(
                        *cmd, timeout=_get_subprocess_timeout()
                    )

                    if exit_code != 0:
                        await ctx.send(
                            f"❌ **Watermarking failed.** delphitools "
                            f"exited with code {exit_code}."
                        )

                        if stdout:
                            await ctx.send(f"Error details: `{stdout}`")

                        return

                    # Check if output file was created

                    if not output_file.exists():
                        await ctx.send(
                            "❌ **Watermarking failed.** Output file was "
                            "not generated."
                        )

                        return

                    # Check file size

                    file_size = output_file.stat().st_size

                    if file_size > self.LIMIT_BYTES:
                        await ctx.send(
                            f"⚠️ **Watermarking successful but "
                            "file too large. "
                            f"The watermarked image is "
                            f"{file_size / (1024 * 1024):.1f} MB, "
                            "which exceeds the "
                            f"{self.LIMIT_BYTES / (1024 * 1024):.0f} MB "
                            "Discord limit."
                        )

                        return

                    # Send the watermarked image

                    await ctx.send(
                        content=(
                            f"✅ **Watermark added successfully** "
                            f"({attachment.filename} → {output_filename})"
                        ),
                        file=discord.File(str(output_file)),
                    )

            except asyncio.TimeoutError:
                await ctx.send(
                    "❌ **Watermarking timed out.** The operation took "
                    "too long."
                )

            except Exception as e:
                log.exception("Error in watermark command")

                await ctx.send(f"❌ **Watermarking failed.** {e!s}")

    @commands.hybrid_command(
        name="palette",
        description="Generate a palette of related colors.",
        help=(
            "Create a palette with an analogous, complementary, triadic, "
            "monochromatic, true-random, or random-cohesive strategy. "
            "Choose 1-20 colors (default 5). PNG is the supported image "
            "format. Example: `palette analogous 5 png`."
        ),
        usage="<strategy> [count] [format]",
    )
    @app_commands.describe(
        strategy="Palette generation strategy",
        count="Number of colors in the palette (default: 5)",
        format="Output format (PNG)",
    )
    @app_commands.choices(
        strategy=[
            app_commands.Choice(name="Analogous", value="analogous"),
            app_commands.Choice(name="Complementary", value="complementary"),
            app_commands.Choice(name="Triadic", value="triadic"),
            app_commands.Choice(name="Monochromatic", value="monochromatic"),
            app_commands.Choice(name="True Random", value="true-random"),
            app_commands.Choice(
                name="Random Cohesive", value="random-cohesive"
            ),
        ]
    )
    @app_commands.choices(
        format=[
            app_commands.Choice(name="PNG", value="png"),
        ]
    )
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def palette(
        self,
        ctx: commands.Context,
        strategy: str,
        count: int = 5,
        format: str = "png",
    ) -> None:
        """Generate a color palette using various strategies."""

        # Validate count

        if count < 1 or count > 20:
            await ctx.send("Color count must be between 1 and 20.")

            return

        if strategy not in {
            "analogous",
            "complementary",
            "triadic",
            "monochromatic",
            "true-random",
            "random-cohesive",
        }:
            await ctx.send("Please select a supported palette strategy.")

            return

        if format != "png":
            await ctx.send("PNG is the supported palette image format.")

            return

        # Process the request

        async with ctx.typing():
            try:
                # Create a temporary directory for processing

                with tempfile.TemporaryDirectory() as tmp_dir:
                    tmp_path = Path(tmp_dir)

                    # Determine output filename

                    output_filename = f"palette.{format}"

                    output_file = tmp_path / output_filename

                    # Build delphitools palette command

                    cmd = [
                        "dt",
                        "palette",
                        "--size",
                        str(count),
                        "--format",
                        format,
                        "--output",
                        str(output_file),
                    ]

                    # Add strategy parameter

                    cmd.extend(["--strategy", strategy])

                    # Run the palette generation

                    exit_code, stdout = await _run_capture(
                        *cmd, timeout=_get_subprocess_timeout()
                    )

                    if exit_code != 0:
                        await ctx.send(
                            f"❌ **Palette generation failed.** "
                            f"delphitools exited with code {exit_code}."
                        )

                        if stdout:
                            await ctx.send(f"Error details: `{stdout}`")

                        return

                    # Check if output file was created

                    if not output_file.exists():
                        await ctx.send(
                            "❌ **Palette generation failed.** Output file "
                            "was not generated."
                        )

                        return

                    # Check file size

                    file_size = output_file.stat().st_size

                    if file_size > self.LIMIT_BYTES:
                        await ctx.send(
                            f"⚠️ **Palette generation successful but "
                            "file too large. "
                            f"The palette is "
                            f"{file_size / (1024 * 1024):.1f} MB, "
                            "which exceeds the "
                            f"{self.LIMIT_BYTES / (1024 * 1024):.0f} MB "
                            "Discord limit."
                        )

                        return

                    # Send the palette

                    await ctx.send(
                        content=(
                            f"✅ **Palette generated successfully** "
                            f"({count} colors using {strategy} strategy)"
                        ),
                        file=discord.File(str(output_file)),
                    )

            except asyncio.TimeoutError:
                await ctx.send(
                    "❌ **Palette generation timed out.** The operation "
                    "took too long."
                )

            except Exception as e:
                log.exception("Error in palette command")

                await ctx.send(f"❌ **Palette generation failed.** {e!s}")

    @commands.hybrid_command(
        name="colorblind",
        description="Simulate colorblindness on an image",
        help=(
            "Show how an attached image looks with protanopia, "
            "deuteranopia, tritanopia, or achromatopsia. Select `all` to "
            "generate all four variants. "
            "Attach the image to the command message. "
            "Example: `colorblind all` with an image attached."
        ),
        usage="<type> (attach image)",
    )
    @app_commands.describe(
        attachment="The image to process",
        type=(
            "Select protanopia, deuteranopia, tritanopia, achromatopsia, "
            "or all four"
        ),
    )
    @app_commands.choices(
        type=[
            app_commands.Choice(name="Protanopia", value="protanopia"),
            app_commands.Choice(name="Deuteranopia", value="deuteranopia"),
            app_commands.Choice(name="Tritanopia", value="tritanopia"),
            app_commands.Choice(name="Achromatopsia", value="achromatopsia"),
            app_commands.Choice(name="All four", value="all"),
        ]
    )
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def colorblind(
        self,
        ctx: commands.Context,
        type: str,
        attachment: discord.Attachment | None = None,
    ) -> None:
        """Simulate colorblindness on an image."""

        if not attachment:
            await ctx.send("Please attach an image to process.")

            return

        # Check if it's an image

        if (
            not attachment.content_type
            or not attachment.content_type.startswith("image/")
        ):
            await ctx.send("Please attach a valid image file.")

            return

        # Process the attachment

        async with ctx.typing():
            try:
                started_at = time.perf_counter()

                # Extract attachment data

                attachments = await extract_attachments(
                    ctx.message, attachment
                )

                if not attachments:
                    await ctx.send("Failed to read the attached image.")

                    return

                image_data, _mime_type = attachments[0]

                # Create a temporary directory for processing

                with tempfile.TemporaryDirectory() as tmp_dir:
                    tmp_path = Path(tmp_dir)

                    # Save the input image

                    input_file = (
                        tmp_path / f"input{Path(attachment.filename).suffix}"
                    )

                    await asyncio.to_thread(
                        Path(input_file).write_bytes, image_data
                    )

                    simulation_types = (
                        COLORBLIND_SIMULATIONS if type == "all" else (type,)
                    )
                    output_files: list[Path] = []

                    for simulation_type in simulation_types:
                        output_file = (
                            tmp_path / f"colorblind_{simulation_type}_"
                            f"{Path(attachment.filename).stem}.png"
                        )
                        cmd = [
                            "dt",
                            "colorblind",
                            str(input_file),
                            "--output",
                            str(output_file),
                            "--cb-type",
                            simulation_type,
                        ]

                        exit_code, stdout = await _run_capture(
                            *cmd, timeout=_get_subprocess_timeout()
                        )

                        if exit_code != 0:
                            await ctx.send(
                                f"❌ **Colorblind simulation failed for "
                                f"{simulation_type}.** delphitools exited "
                                f"with code {exit_code}."
                            )

                            if stdout:
                                await ctx.send(f"Error details: `{stdout}`")

                            return

                        if not output_file.exists():
                            await ctx.send(
                                f"❌ **Colorblind simulation failed for "
                                f"{simulation_type}.** Output file was not "
                                "generated."
                            )

                            return

                        file_size = output_file.stat().st_size
                        if file_size > self.LIMIT_BYTES:
                            await ctx.send(
                                f"⚠️ **Colorblind simulation successful but "
                                f"{simulation_type} file is too large.** "
                                f"The processed image is "
                                f"{file_size / (1024 * 1024):.1f} MB, "
                                f"which exceeds the "
                                f"{self.LIMIT_BYTES / (1024 * 1024):.0f} MB "
                                "Discord limit."
                            )

                            return

                        output_files.append(output_file)

                    elapsed = time.perf_counter() - started_at
                    if type == "all":
                        await ctx.send(
                            content=(
                                f"✅ **All simulations done in "
                                f"{elapsed:.2f}s**"
                            ),
                            files=[
                                discord.File(str(output_file))
                                for output_file in output_files
                            ],
                        )
                    else:
                        await ctx.send(
                            content=(
                                f"✅ **{type.capitalize()} done in "
                                f"{elapsed:.2f}s**"
                            ),
                            file=discord.File(str(output_files[0])),
                        )

            except asyncio.TimeoutError:
                await ctx.send(
                    "❌ **Colorblind simulation timed out.** The operation "
                    "took too long."
                )

            except Exception as e:
                log.exception("Error in colorblind command")

                await ctx.send(f"❠ **Colorblind simulation failed.** {e!s}")

    @commands.hybrid_command(
        name="qrgen",
        description="Create a QR code from text or a link.",
        help=(
            "Create a QR code that contains the text or link you provide. "
            "Example: `qrgen https://example.com`."
        ),
        usage="<text or link>",
    )
    @app_commands.describe(
        text="Text to encode in QR code",
    )
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def qrgen(self, ctx: commands.Context, text: str) -> None:
        """Generate QR code."""

        async with ctx.typing():
            try:
                with tempfile.TemporaryDirectory() as tmp_dir:
                    tmp_path = Path(tmp_dir)

                    output_file = tmp_path / "qr.png"

                    cmd = ["dt", "qr", text, "--output", str(output_file)]

                    exit_code, stdout = await _run_capture(
                        *cmd, timeout=_get_subprocess_timeout()
                    )

                    if exit_code != 0:
                        await ctx.send(
                            f"❌ ❌ QR generation failed.** delphitools "
                            f"exited with code {exit_code}."
                        )

                        if stdout:
                            await ctx.send(f"Error details: `{stdout}`")

                        return

                    if not output_file.exists():
                        await ctx.send(
                            "❌ **QR generation failed.** Output not created."
                        )

                        return

                    if output_file.stat().st_size > self.LIMIT_BYTES:
                        await ctx.send(
                            "⚠️ QR image exceeds Discord size limit."
                        )

                        return

                    await ctx.send(file=discord.File(str(output_file)))

            except asyncio.TimeoutError:
                await ctx.send("❌ **QR generation timed out.**")

            except Exception as e:
                log.exception("Error in qrgen command")

                await ctx.send(f"❌ **QR generation failed.** {e!s}")

    @commands.hybrid_command(
        name="barcodegen",
        description="Create a barcode from text or a number.",
        help=(
            "Encode text or a number as a Code 128 or EAN-13 barcode. "
            "Choose the format after the data. "
            "Example: `barcodegen 12345678 code128`."
        ),
        usage="<data> <type>",
    )
    @app_commands.describe(
        text="Data to encode",
        type="Barcode format",
    )
    @app_commands.choices(
        type=[
            app_commands.Choice(name="Code128", value="code128"),
            app_commands.Choice(name="EAN13", value="ean13"),
        ]
    )
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def barcodegen(
        self, ctx: commands.Context, text: str, type: str
    ) -> None:
        """Generate barcode."""

        async with ctx.typing():
            try:
                with tempfile.TemporaryDirectory() as tmp_dir:
                    tmp_path = Path(tmp_dir)

                    output_file = tmp_path / f"barcode.{type}.png"

                    cmd = [
                        "dt",
                        "barcode",
                        text,
                        "--format",
                        type,
                        "--output",
                        str(output_file),
                    ]

                    exit_code, stdout = await _run_capture(
                        *cmd, timeout=_get_subprocess_timeout()
                    )

                    if exit_code != 0:
                        await ctx.send(
                            f"❌ **Barcode generation failed.** delphitools "
                            f"exited with code {exit_code}."
                        )

                        if stdout:
                            await ctx.send(f"Error details: `{stdout}`")

                        return

                    if not output_file.exists():
                        await ctx.send(
                            "❌ **Barcode generation failed.** "
                            "Output not created."
                        )

                        return

                    if output_file.stat().st_size > self.LIMIT_BYTES:
                        await ctx.send(
                            "⚠️ Barcode image exceeds Discord size limit."
                        )

                        return

                    await ctx.send(file=discord.File(str(output_file)))

            except asyncio.TimeoutError:
                await ctx.send("❌ **Barcode generation timed out.**")

            except Exception as e:
                log.exception("Error in barcodegen command")

                await ctx.send(f"❌ **Barcode generation failed.** {e!s}")

    @commands.hybrid_command(
        name="unitconvert",
        description="Convert a value from one unit to another.",
        help=(
            "Convert a number between units. Enter the value, source unit, "
            "then target unit. The available units depend on the unit type. "
            "Example: `unit 10 km mi`."
        ),
        usage="<value> <from_unit> <to_unit>",
    )
    @app_commands.describe(
        value="Numeric value",
        from_unit="Source unit",
        to_unit="Target unit",
    )
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def unitconvert(
        self, ctx: commands.Context, value: float, from_unit: str, to_unit: str
    ) -> None:
        """Unit conversion."""

        async with ctx.typing():
            try:
                cmd = ["dt", "unit", f"{value:g} {from_unit}", to_unit]

                exit_code, stdout = await _run_capture(
                    *cmd, timeout=_get_subprocess_timeout()
                )

                if exit_code != 0:
                    await ctx.send(
                        f"❌ **Unit conversion failed.** delphitools "
                        f"exited with code {exit_code}."
                    )

                    if stdout:
                        await ctx.send(f"Error details: `{stdout}`")

                    return

                await ctx.send(f"✅ **Result:** {stdout}")

            except asyncio.TimeoutError:
                await ctx.send("❌ **Unit conversion timed out.**")

            except Exception as e:
                log.exception("Error in unitconvert command")

                await ctx.send(f"❌ **Unit conversion failed.** {e!s}")

    @commands.hybrid_command(
        name="unit",
        description="Convert a value from one unit to another.",
        help=(
            "Convert a number between units. Enter the value, source unit, "
            "then target unit. Example: `unit 10 km mi`."
        ),
        usage="<value> <from_unit> <to_unit>",
    )
    @app_commands.describe(
        value="Numeric value",
        from_unit="Source unit",
        to_unit="Target unit",
    )
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def unit(
        self, ctx: commands.Context, value: float, from_unit: str, to_unit: str
    ) -> None:
        await self._run_text_cli(
            ctx, "Unit conversion", "unit", f"{value:g} {from_unit}", to_unit
        )

    @commands.hybrid_command(
        name="encode",
        description="Encode text as Base64, hexadecimal, or URL text.",
        help=(
            "Encode text as Base64 or URL text. "
            "Example: `encode hello base64`."
        ),
        usage="<text> <encoding>",
    )
    @app_commands.describe(
        data="Data to encode",
        encoding="Encoding type",
    )
    @app_commands.choices(
        encoding=[
            app_commands.Choice(name="Base64", value="base64"),
            app_commands.Choice(name="URL", value="url"),
        ]
    )
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def encode(
        self, ctx: commands.Context, data: str, encoding: str
    ) -> None:
        """Encode data."""

        async with ctx.typing():
            try:
                cmd = ["dt", "encode", encoding, data]

                exit_code, stdout = await _run_capture(
                    *cmd, timeout=_get_subprocess_timeout()
                )

                if exit_code != 0:
                    await ctx.send(
                        f"❌ **Encode failed.** delphitools "
                        f"exited with code {exit_code}."
                    )

                    if stdout:
                        await ctx.send(f"Error details: `{stdout}`")

                    return

                await ctx.send(f"✅ **Encoded:** {stdout}")

            except asyncio.TimeoutError:
                await ctx.send("❌ **Encode timed out.**")

            except Exception as e:
                log.exception("Error in encode command")

                await ctx.send(f"❌ **Encode failed.** {e!s}")

    @commands.hybrid_command(
        name="decode",
        description="Decode Base64 or URL text.",
        help=(
            "Convert encoded Base64 or URL text back to text. "
            "Example: `decode aGVsbG8= base64`."
        ),
        usage="<encoded_text> <encoding>",
    )
    @app_commands.describe(
        data="Data to decode",
        encoding="Encoding type",
    )
    @app_commands.choices(
        encoding=[
            app_commands.Choice(name="Base64", value="base64"),
            app_commands.Choice(name="URL", value="url"),
        ]
    )
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def decode(
        self, ctx: commands.Context, data: str, encoding: str
    ) -> None:
        """Decode data."""

        async with ctx.typing():
            try:
                cmd = ["dt", "decode", encoding, data]

                exit_code, stdout = await _run_capture(
                    *cmd, timeout=_get_subprocess_timeout()
                )

                if exit_code != 0:
                    await ctx.send(
                        f"❌ **Decode failed.** delphitools "
                        f"exited with code {exit_code}."
                    )

                    if stdout:
                        await ctx.send(f"Error details: `{stdout}`")

                    return

                await ctx.send(f"✅ **Decoded:** {stdout}")

            except asyncio.TimeoutError:
                await ctx.send("❌ **Decode timed out.**")

            except Exception as e:
                log.exception("Error in decode command")

                await ctx.send(f"❌ **Decode failed.** {e!s}")

    @commands.hybrid_command(
        name="hash",
        description=(
            "Create a one-way hash of text with MD5, SHA-1, or SHA-256."
        ),
        help=(
            "Create a fixed-length digest of text. A hash cannot be reversed. "
            "Select `md5`, `sha1`, or `sha256`. "
            "Example: `hash hello sha256`."
        ),
        usage="<data> <algorithm>",
    )
    @app_commands.describe(
        data="Data to hash",
        algorithm="Hash algorithm",
    )
    @app_commands.choices(
        algorithm=[
            app_commands.Choice(name="MD5", value="md5"),
            app_commands.Choice(name="SHA256", value="sha256"),
            app_commands.Choice(name="SHA1", value="sha1"),
        ]
    )
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def hash(
        self, ctx: commands.Context, data: str, algorithm: str
    ) -> None:
        """Hash data."""

        async with ctx.typing():
            try:
                cmd = ["dt", "hash", algorithm, data]

                exit_code, stdout = await _run_capture(
                    *cmd, timeout=_get_subprocess_timeout()
                )

                if exit_code != 0:
                    await ctx.send(
                        f"❌ **Hash failed.** delphitools "
                        f"exited with code {exit_code}."
                    )

                    if stdout:
                        await ctx.send(f"Error details: `{stdout}`")

                    return

                await ctx.send(f"✅ **Hash ({algorithm}):** {stdout}")

            except asyncio.TimeoutError:
                await ctx.send("❌ **Hash timed out.**")

            except Exception as e:
                log.exception("Error in hash command")

                await ctx.send(f"❌ **Hash failed.** {e!s}")


async def setup(bot: commands.Bot) -> None:

    await bot.add_cog(Delphitools(bot))

