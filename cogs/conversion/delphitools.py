#!/usr/bin/env python3

# cogs/conversion/delphitools.py: Delphitools CLI integration for file
# conversion


import asyncio
import logging
import os
import tempfile
import time
from pathlib import Path

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
    *cmd: str, timeout: int | None = None
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

    output = stderr if return_code != 0 and stderr else stdout
    return return_code, output.decode().strip()


class Delphitools(commands.Cog):
    LIMIT_BYTES = 10 * 1024 * 1024  # 10 MB Discord upload limit

    help_category = "Conversion"

    def __init__(self, bot: commands.Bot) -> None:

        self.bot = bot

    # ------------------------------------------------------------------

    # Internal helpers

    # ------------------------------------------------------------------

    # ------------------------------------------------------------------

    # Commands

    # ------------------------------------------------------------------

    @commands.hybrid_command(
        name="imgconvert",
        description=("Convert an attached image and optionally resize it."),
        help=(
            "Convert an attached image to PNG, JPG, WebP, GIF, BMP, TIFF, "
            "or ICO. You can also set a width and height in pixels. "
            "Attach the image to the command message. "
            "Example: `{prefix}imgconvert webp` with an image attached."
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
            "Opacity is from 0.0 (transparent) to 1.0 (opaque). "
            "Attach the base image and watermark image to the command. "
            "Example: `{prefix}watermark` with both images attached."
        ),
        usage="[opacity] [position] (attach base and watermark images)",
    )
    @app_commands.describe(
        attachment="The base image",
        mark="The watermark image",
        opacity="Opacity from 0.0 to 1.0 (default: 0.3)",
        position=(
            "Position (top-left, top, top-right, left, center, right, "
            "bottom-left, bottom, bottom-right)"
        ),
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
            "format. Example: `{prefix}palette analogous 5 png`."
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
            "Example: `{prefix}colorblind all` with an image attached."
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
            "Example: `{prefix}qrgen https://example.com`."
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
            "Example: `{prefix}barcodegen 12345678 code128`."
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
            "Example: `{prefix}unitconvert 10 km mi`."
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
        name="encode",
        description="Encode text as Base64, hexadecimal, or URL text.",
        help=(
            "Encode text as Base64 or URL text. "
            "Example: `{prefix}encode hello base64`."
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
            "Example: `{prefix}decode aGVsbG8= base64`."
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
            "Example: `{prefix}hash hello sha256`."
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
