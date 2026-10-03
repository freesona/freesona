#!/usr/bin/env python3

# cogs/conversion/delphitools.py: Delphitools CLI integration for file conversion



import asyncio
import logging
import tempfile
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from utils.config import load_config
from utils.generation import extract_attachments

log = logging.getLogger(__name__)



# Configurable values loaded from config.json (settable via /config slash commands)





def _get_subprocess_timeout() -> int:

    return int(load_config().get("delphitools_subprocess_timeout", 300))





def _get_limit_bytes() -> int:

    return int(load_config().get("delphitools_limit_bytes", 10 * 1024 * 1024))  # 10 MB default







async def _run(*cmd: str, timeout: int | None = None) -> int:

    """Run a subprocess and return its exit code. Raises TimeoutError on timeout."""

    if timeout is None:

        timeout = _get_subprocess_timeout()

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





async def _run_capture(*cmd: str, timeout: int | None = None) -> tuple[int,

    str]:

    """Run a subprocess, capture stdout, and return (exit_code, stdout_text)."""

    if timeout is None:

        timeout = _get_subprocess_timeout()

    proc = await asyncio.create_subprocess_exec(

        *cmd,

        stdout=asyncio.subprocess.PIPE,

        stderr=asyncio.subprocess.PIPE,

    )

    try:

        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)

    except asyncio.TimeoutError:

        proc.kill()

        stdout = b""

    return_code = proc.returncode

    if return_code is None:

        raise RuntimeError("Subprocess finished without an exit code.")

    return return_code, stdout.decode().strip()





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

        description="Convert image formats (PNG, JPG, WebP, etc.) with optional resize",

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

    @commands.cooldown(1, 30, commands.BucketType.user)

    async def imgconvert(

        self,

        ctx: commands.Context,

        format: str,

        attachment: discord.Attachment | None = None,

        width: int | None = None, height: int | None = None, ) -> None:

        """Convert an image to a different format with optional resize."""

        if not attachment:

            await ctx.send("Please attach an image to convert.")

            return



        # Check if it's an image

        if not attachment.content_type or not attachment.content_type.startswith("image/"):

            await ctx.send("Please attach a valid image file.")

            return



        # Process the attachment

        async with ctx.typing():

            try:

                # Extract attachment data

                attachments = await extract_attachments(ctx.message)

                if not attachments:

                    await ctx.send("Failed to read the attached image.")

                    return

                

                image_data, _mime_type = attachments[0]

                

                # Create a temporary directory for processing

                with tempfile.TemporaryDirectory() as tmp_dir:

                    tmp_path = Path(tmp_dir)

                    

                    # Save the input image

                    input_file = tmp_path / f"input{Path(attachment.filename).suffix}"

                    await asyncio.to_thread(Path(input_file).write_bytes, image_data)

                    

                    # Determine output filename

                    output_filename = f"output.{format}"

                    output_file = tmp_path / output_filename

                    

                    # Build delphitools convert command

                    cmd = ["dt", "convert", str(input_file), str(output_file)]

                    

                    # Add resize parameters if provided

                    if width is not None and height is not None:

                        cmd.extend(["--resize", f"{width}x{height}"])

                    elif width is not None:

                        cmd.extend(["--resize", f"{width}"])

                    elif height is not None:

                        cmd.extend(["--resize", f"x{height}"])

                    

                    # Run the conversion

                    exit_code, stdout = await _run_capture(*cmd,

                        timeout=_get_subprocess_timeout())

                    

                    if exit_code != 0:

                        await ctx.send(f"❌ **Conversion failed.** delphitools exited with code {exit_code}.")

                        if stdout:

                            await ctx.send(f"Error details: `{stdout}`")

                        return

                    

                    # Check if output file was created

                    if not output_file.exists():

                        await ctx.send("❌ **Conversion failed.** Output file was not generated.")

                        return

                    

                    # Check file size

                    file_size = output_file.stat().st_size

                    if file_size > self.LIMIT_BYTES:

                        await ctx.send(f"⚠️ **Conversion successful but file too large.** The converted image is {file_size / (1024 * 1024):.1f} MB, which exceeds the {self.LIMIT_BYTES / (1024 * 1024):.0f} MB Discord limit.")

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

                await ctx.send("❌ **Conversion timed out.** The image conversion took too long.")

            except Exception as e:

                log.exception("Error in imgconvert command")

                await ctx.send(f"❌ **Conversion failed.** {e!s}")



    @commands.hybrid_command(

        name="watermark",

        description="Add a watermark to an image",

    )

    @app_commands.describe(

        attachment="The image to watermark",

        text="Watermark text",

        opacity="Opacity percentage (0-100, default: 50)",

        position="Position of watermark (top-left, top-right, bottom-left, bottom-right, center)",

    )

    @app_commands.choices(

        position=[

            app_commands.Choice(name="Top Left", value="top-left"),

            app_commands.Choice(name="Top Right", value="top-right"),

            app_commands.Choice(name="Bottom Left", value="bottom-left"),

            app_commands.Choice(name="Bottom Right", value="bottom-right"),

            app_commands.Choice(name="Center", value="center"),

        ]

    )

    @commands.cooldown(1, 30, commands.BucketType.user)

    async def watermark(

        self,

        ctx: commands.Context,

        text: str,

        attachment: discord.Attachment | None = None,

        opacity: int = 50, position: str = "bottom-right", ) -> None:

        """Add a watermark to an image."""

        if not attachment:

            await ctx.send("Please attach an image to watermark.")

            return



        # Check if it's an image

        if not attachment.content_type or not attachment.content_type.startswith("image/"):

            await ctx.send("Please attach a valid image file.")

            return



        # Validate opacity

        if opacity < 0 or opacity > 100:

            await ctx.send("Opacity must be between 0 and 100.")

            return



        # Process the attachment

        async with ctx.typing():

            try:

                # Extract attachment data

                attachments = await extract_attachments(ctx.message)

                if not attachments:

                    await ctx.send("Failed to read the attached image.")

                    return

                

                image_data, _mime_type = attachments[0]

                

                # Create a temporary directory for processing

                with tempfile.TemporaryDirectory() as tmp_dir:

                    tmp_path = Path(tmp_dir)

                    

                    # Save the input image

                    input_file = tmp_path / f"input{Path(attachment.filename).suffix}"

                    await asyncio.to_thread(Path(input_file).write_bytes, image_data)

                    

                    # Determine output filename

                    output_filename = f"watermarked_{Path(attachment.filename).stem}.png"

                    output_file = tmp_path / output_filename

                    

                    # Build delphitools watermark command

                    cmd = ["dt", "watermark", str(input_file), str(output_file),

                        "--text", text]

                    

                    # Add opacity parameter

                    cmd.extend(["--opacity", str(opacity)])

                    

                    # Add position parameter

                    cmd.extend(["--position", position])

                    

                    # Run the watermark command

                    exit_code, stdout = await _run_capture(*cmd,

                        timeout=_get_subprocess_timeout())

                    

                    if exit_code != 0:

                        await ctx.send(f"❌ **Watermarking failed.** delphitools "

                            f"exited with code {exit_code}.")

                        if stdout:

                            await ctx.send(f"Error details: `{stdout}`")

                        return

                    

                    # Check if output file was created

                    if not output_file.exists():

                        await ctx.send("❌ **Watermarking failed.** Output file "

                            "was not generated.")

                        return

                    

                    # Check file size

                    file_size = output_file.stat().st_size

                    if file_size > self.LIMIT_BYTES:

                        await ctx.send(

                            f"⚠️ **Watermarking successful but file too large. "

                            f"The watermarked image is {file_size / (1024 * 1024):.1f} MB, "

                            f"which exceeds the {self.LIMIT_BYTES / (1024 * 1024):.0f} MB Discord limit."

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

                    "❌ **Watermarking timed out.** The operation took too "

                    "long."

                )

            except Exception as e:

                log.exception("Error in watermark command")

                await ctx.send(f"❌ **Watermarking failed.** {e!s}")



    @commands.hybrid_command(

        name="palette",

        description="Generate a color palette using various strategies",

    )

    @app_commands.describe(

        strategy="Palette generation strategy",

        count="Number of colors in the palette (default: 5)",

        format="Output format (png, jpg, webp, svg)",

    )

    @app_commands.choices(

        strategy=[

            app_commands.Choice(name="Analogous", value="analogous"),

            app_commands.Choice(name="Complementary", value="complementary"),

            app_commands.Choice(name="Triadic", value="triadic"),

            app_commands.Choice(name="Monochromatic", value="monochromatic"),

            app_commands.Choice(name="Random", value="random"),

            app_commands.Choice(name="Gradient", value="gradient"),

        ]

    )

    @app_commands.choices(

        format=[

            app_commands.Choice(name="PNG", value="png"),

            app_commands.Choice(name="JPG", value="jpg"),

            app_commands.Choice(name="WebP", value="webp"),

            app_commands.Choice(name="SVG", value="svg"),

        ]

    )

    @commands.cooldown(1, 30, commands.BucketType.user)

    async def palette(

        self,

        ctx: commands.Context,

        strategy: str,

        count: int = 5, format: str = "png", ) -> None:

        """Generate a color palette using various strategies."""

        # Validate count

        if count < 1 or count > 20:

            await ctx.send("Color count must be between 1 and 20.")

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

                    cmd = ["dt", "palette", "--count", str(count), "--format",

                        format, "--output", str(output_file)]

                    

                    # Add strategy parameter

                    cmd.extend(["--strategy", strategy])

                    

                    # Run the palette generation

                    exit_code, stdout = await _run_capture(*cmd,

                        timeout=_get_subprocess_timeout())

                    

                    if exit_code != 0:

                        await ctx.send(f"❌ **Palette generation failed.** "

                            f"delphitools exited with code {exit_code}.")

                        if stdout:

                            await ctx.send(f"Error details: `{stdout}`")

                        return

                    

                    # Check if output file was created

                    if not output_file.exists():

                        await ctx.send("❌ **Palette generation failed.** Output file was not generated.")

                        return

                    

                    # Check file size

                    file_size = output_file.stat().st_size

                    if file_size > self.LIMIT_BYTES:

                        await ctx.send(

                            f"⚠️ **Palette generation successful but file too large. "

                            f"The palette is {file_size / (1024 * 1024):.1f} MB, "

                            f"which exceeds the {self.LIMIT_BYTES / (1024 * 1024):.0f} MB Discord limit."

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

                    "❌ **Palette generation timed out.** The operation took too "

                    "long."

                )

            except Exception as e:

                log.exception("Error in palette command")

                await ctx.send(f"❌ **Palette generation failed.** {e!s}")



    @commands.hybrid_command(

        name="colorblind",

        description="Simulate colorblindness on an image",

    )

    @app_commands.describe(

        attachment="The image to process",

        type="Type of colorblindness to simulate (protanopia, deuteranopia, tritanopia, achromatopsia)",

    )

    @app_commands.choices(

        type=[

            app_commands.Choice(name="Protanopia", value="protanopia"),

            app_commands.Choice(name="Deuteranopia", value="deuteranopia"),

            app_commands.Choice(name="Tritanopia", value="tritanopia"),

            app_commands.Choice(name="Achromatopsia", value="achromatopsia"),

        ]

    )

    @commands.cooldown(1, 30, commands.BucketType.user)

    async def colorblind(

        self,

        ctx: commands.Context,

        type: str, attachment: discord.Attachment | None = None, ) -> None:

        """Simulate colorblindness on an image."""

        if not attachment:

            await ctx.send("Please attach an image to process.")

            return



        # Check if it's an image

        if not attachment.content_type or not attachment.content_type.startswith("image/"):

            await ctx.send("Please attach a valid image file.")

            return



        # Process the attachment

        async with ctx.typing():

            try:

                # Extract attachment data

                attachments = await extract_attachments(ctx.message)

                if not attachments:

                    await ctx.send("Failed to read the attached image.")

                    return

                

                image_data, _mime_type = attachments[0]

                

                # Create a temporary directory for processing

                with tempfile.TemporaryDirectory() as tmp_dir:

                    tmp_path = Path(tmp_dir)

                    

                    # Save the input image

                    input_file = tmp_path / f"input{Path(attachment.filename).suffix}"

                    await asyncio.to_thread(Path(input_file).write_bytes, image_data)

                    

                    # Determine output filename

                    output_filename = f"colorblind_{type}_{Path(attachment.filename).stem}.png"

                    output_file = tmp_path / output_filename

                    

                    # Build delphitools colorblind command

                    cmd = ["dt", "colorblind", str(input_file),

                        str(output_file), "--type", type]

                    

                    # Run the colorblind simulation

                    exit_code, stdout = await _run_capture(*cmd,

                        timeout=_get_subprocess_timeout())

                    

                    if exit_code != 0:

                        await ctx.send(f"❌ **Colorblind simulation failed.** delphitools exited with code {exit_code}.")

                        if stdout:

                            await ctx.send(f"Error details: `{stdout}`")

                        return

                    

                    # Check if output file was created

                    if not output_file.exists():

                        await ctx.send("❌ **Colorblind simulation failed.** Output file was not generated.")

                        return

                    

                    # Check file size

                    file_size = output_file.stat().st_size

                    if file_size > self.LIMIT_BYTES:

                        await ctx.send(

                            f"⚠️ **Colorblind simulation successful but file too large.** "

                            f"The processed image is {file_size / (1024 * 1024):.1f} MB, "

                            f"which exceeds the {self.LIMIT_BYTES / (1024 * 1024):.0f} MB Discord limit."

                        )

                        return

                    

                    # Send the processed image

                    await ctx.send(

                        content=(

                            f"✅ **Colorblind simulation completed** "

                            f"({type} simulation applied to {attachment.filename})"

                        ),

                        file=discord.File(str(output_file)),

                    )

                    

            except asyncio.TimeoutError:

                await ctx.send(

                    "❌ **Colorblind simulation timed out.** The operation took too long."

                )

            except Exception as e:

                log.exception("Error in colorblind command")

                await ctx.send(f"❠ **Colorblind simulation failed.** {e!s}")



    @commands.hybrid_command(

        name="qrgen",

        description="Generate a QR code from text",

    )

    @app_commands.describe(

        text="Text to encode in QR code",

    )

    @commands.cooldown(1, 30, commands.BucketType.user)

    async def qrgen(self, ctx: commands.Context, text: str) -> None:

        """Generate QR code."""

        async with ctx.typing():

            try:

                with tempfile.TemporaryDirectory() as tmp_dir:

                    tmp_path = Path(tmp_dir)

                    output_file = tmp_path / "qr.png"

                    cmd = ["dt", "qr", text, "--output", str(output_file)]

                    exit_code, stdout = await _run_capture(*cmd,

                        timeout=_get_subprocess_timeout())

                    if exit_code != 0:

                        await ctx.send(f"❌ ❌ QR generation failed.** delphitools exited with code {exit_code}.")

                        if stdout:

                            await ctx.send(f"Error details: `{stdout}`")

                        return

                    if not output_file.exists():

                        await ctx.send("❌ **QR generation failed.** Output not created.")

                        return

                    if output_file.stat().st_size > self.LIMIT_BYTES:

                        await ctx.send("⚠️ QR image exceeds Discord size limit.")

                        return

                    await ctx.send(file=discord.File(str(output_file)))

            except asyncio.TimeoutError:

                await ctx.send("❌ **QR generation timed out.**")

            except Exception as e:

                log.exception("Error in qrgen command")

                await ctx.send(f"❌ **QR generation failed.** {e!s}")



    @commands.hybrid_command(

        name="barcodegen",

        description="Generate a barcode from text",

    )

    @app_commands.describe(

        text="Data to encode",

        type="Barcode format",

    )

    @app_commands.choices(

        type=[

            app_commands.Choice(name="Code128", value="code128"),

            app_commands.Choice(name="EAN13", value="ean13"),

            app_commands.Choice(name="QR", value="qr"),

        ]

    )

    @commands.cooldown(1, 30, commands.BucketType.user)

    async def barcodegen(self, ctx: commands.Context, text: str, type: str) -> None:

        """Generate barcode."""

        async with ctx.typing():

            try:

                with tempfile.TemporaryDirectory() as tmp_dir:

                    tmp_path = Path(tmp_dir)

                    output_file = tmp_path / f"barcode.{type}.png"

                    cmd = ["dt", "barcode", type, text, "--output",

                        str(output_file)]

                    exit_code, stdout = await _run_capture(*cmd,

                        timeout=_get_subprocess_timeout())

                    if exit_code != 0:

                        await ctx.send(f"❌ **Barcode generation failed.** delphitools exited with code {exit_code}.")

                        if stdout:

                            await ctx.send(f"Error details: `{stdout}`")

                        return

                    if not output_file.exists():

                        await ctx.send("❌ **Barcode generation failed.** Output not created.")

                        return

                    if output_file.stat().st_size > self.LIMIT_BYTES:

                        await ctx.send("⚠️ Barcode image exceeds Discord size limit.")

                        return

                    await ctx.send(file=discord.File(str(output_file)))

            except asyncio.TimeoutError:

                await ctx.send("❌ **Barcode generation timed out.**")

            except Exception as e:

                log.exception("Error in barcodegen command")

                await ctx.send(f"❌ **Barcode generation failed.** {e!s}")



    @commands.hybrid_command(

        name="unitconvert",

        description="Convert units",

    )

    @app_commands.describe(

        value="Numeric value",

        from_unit="Source unit",

        to_unit="Target unit",

    )

    @commands.cooldown(1, 30, commands.BucketType.user)

    async def unitconvert(self, ctx: commands.Context, value: float, from_unit: str, to_unit: str) -> None:

        """Unit conversion."""

        async with ctx.typing():

            try:

                cmd = ["dt", "unit", str(value), from_unit, to_unit]

                exit_code, stdout = await _run_capture(*cmd,

                    timeout=_get_subprocess_timeout())

                if exit_code != 0:

                    await ctx.send(f"❌ **Unit conversion failed.** delphitools exited with code {exit_code}.")

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

        description="Encode data",

    )

    @app_commands.describe(

        data="Data to encode",

        encoding="Encoding type",

    )

    @app_commands.choices(

        encoding=[

            app_commands.Choice(name="Base64", value="base64"),

            app_commands.Choice(name="Hex", value="hex"),

            app_commands.Choice(name="URL", value="url"),

        ]

    )

    @commands.cooldown(1, 30, commands.BucketType.user)

    async def encode(self, ctx: commands.Context, data: str, encoding: str) -> None:

        """Encode data."""

        async with ctx.typing():

            try:

                cmd = ["dt", "encode", "--type", encoding, "--input", data]

                exit_code, stdout = await _run_capture(*cmd,

                    timeout=_get_subprocess_timeout())

                if exit_code != 0:

                    await ctx.send(f"❌ **Encode failed.** delphitools exited with code {exit_code}.")

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

        description="Decode data",

    )

    @app_commands.describe(

        data="Data to decode",

        encoding="Encoding type",

    )

    @app_commands.choices(

        encoding=[

            app_commands.Choice(name="Base64", value="base64"),

            app_commands.Choice(name="Hex", value="hex"),

            app_commands.Choice(name="URL", value="url"),

        ]

    )

    @commands.cooldown(1, 30, commands.BucketType.user)

    async def decode(self, ctx: commands.Context, data: str, encoding: str) -> None:

        """Decode data."""

        async with ctx.typing():

            try:

                cmd = ["dt", "decode", "--type", encoding, "--input", data]

                exit_code, stdout = await _run_capture(*cmd,

                    timeout=_get_subprocess_timeout())

                if exit_code != 0:

                    await ctx.send(f"❌ **Decode failed.** delphitools exited with code {exit_code}.")

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

        description="Generate hash of data",

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

    @commands.cooldown(1, 30, commands.BucketType.user)

    async def hash(self, ctx: commands.Context, data: str, algorithm: str) -> None:

        """Hash data."""

        async with ctx.typing():

            try:

                cmd = ["dt", "hash", "--algo", algorithm, "--input", data]

                exit_code, stdout = await _run_capture(*cmd,

                    timeout=_get_subprocess_timeout())

                if exit_code != 0:

                    await ctx.send(f"❌ **Hash failed.** delphitools exited with code {exit_code}.")

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

