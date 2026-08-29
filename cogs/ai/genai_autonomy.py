# cogs/ai/genai_autonomy.py: Autonomy mode configuration and bot whitelist
# management.


import discord
from discord import app_commands
from discord.ext import commands

from utils.config import load_config, save_config

from .genai_common import logger  # Import shared logger for error reporting


class GenAIAutonomyCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # -------------------------------------------------------------------
    # /autonomy
    # -------------------------------------------------------------------
    @app_commands.command(
        name="autonomy",
        description="Configure autonomy mode settings (Admin only).",
    )
    @app_commands.describe(
        action="on / off / frequency",
        frequency=("low / default / high — only used when action is 'frequency'"),
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def autonomy_cmd(
        self,
        interaction: discord.Interaction,
        action: str,
        frequency: str | None = None,
    ):
        config = load_config()
        action = action.lower().strip()

        if action == "on":
            config["autonomy"] = True
            save_config(config)
            await interaction.response.send_message(
                "Autonomy mode enabled.", ephemeral=True
            )
        elif action == "off":
            config["autonomy"] = False
            save_config(config)
            await interaction.response.send_message(
                "Autonomy mode disabled.", ephemeral=True
            )
        elif action == "frequency":
            if frequency not in ("low", "default", "high"):
                await interaction.response.send_message(
                    "Frequency must be `low`, `default`, or `high`.",
                    ephemeral=True,
                )
                return
            config["autonomy_frequency"] = frequency
            save_config(config)
            await interaction.response.send_message(
                f"Autonomy frequency set to `{frequency}`.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "Unknown action. Use `on`, `off`, or `frequency`.",
                ephemeral=True,
            )

    # -------------------------------------------------------------------
    # /botwhitelist add / remove / list
    # -------------------------------------------------------------------
    @commands.hybrid_group(
        name="botwhitelist",
        aliases=["bw"],
        help="Manage whitelisted bot IDs (Admin only).",
    )
    @commands.has_permissions(administrator=True)
    async def whitelist_group(self, ctx: commands.Context):
        """Root group command displaying whitelisted bots if
        no subcommand is invoked."""
        if ctx.invoked_subcommand is not None:
            return

        config = load_config()
        whitelist = [int(x) for x in config.get("whitelist_bot_ids", [])]
        if not whitelist:
            await ctx.send("No bots are whitelisted.", ephemeral=bool(ctx.interaction))
            return
        lines = "\n".join(f"- `{bot_id}`" for bot_id in whitelist)
        await ctx.send(f"Whitelisted bots:\n{lines}", ephemeral=bool(ctx.interaction))

    # type: ignore[attr-defined]
    @whitelist_group.command(name="add", help="Add a bot ID to the whitelist.")
    @app_commands.describe(
        bot_id="The Discord bot ID (integer snowflake) to whitelist."
    )
    async def whitelist_add(self, ctx: commands.Context, bot_id: str):
        try:
            bid = int(bot_id)
        except ValueError:
            # Report parsing error to terminal via logger and inform user
            logger.exception("Failed to parse bot ID for whitelist addition")
            await ctx.send(
                f"Invalid bot ID `{bot_id}` — must be a numeric Discord snowflake.",
                ephemeral=bool(ctx.interaction),
            )
            return
        config = load_config()
        whitelist = [int(x) for x in config.get("whitelist_bot_ids", [])]
        if bid in whitelist:
            await ctx.send(
                f"Bot `{bid}` is already whitelisted.",
                ephemeral=bool(ctx.interaction),
            )
            return
        whitelist.append(bid)
        config["whitelist_bot_ids"] = whitelist
        save_config(config)
        await ctx.send(
            f"Successfully added bot `{bid}` to the whitelist.",
            ephemeral=bool(ctx.interaction),
        )

    # type: ignore[attr-defined]
    @whitelist_group.command(name="remove", help="Remove a bot ID from the whitelist.")
    @app_commands.describe(bot_id="The Discord bot ID (integer snowflake) to remove.")
    async def whitelist_remove(self, ctx: commands.Context, bot_id: str):
        try:
            bid = int(bot_id)
        except ValueError:
            # Log the exception for terminal visibility
            logger.exception("Failed to parse bot ID for whitelist removal")
            await ctx.send(
                f"Invalid bot ID `{bot_id}` — must be a numeric Discord snowflake.",
                ephemeral=bool(ctx.interaction),
            )
            return
        config = load_config()
        whitelist = [int(x) for x in config.get("whitelist_bot_ids", [])]
        if bid not in whitelist:
            await ctx.send(
                f"Bot `{bid}` is not in the whitelist.",
                ephemeral=bool(ctx.interaction),
            )
            return
        whitelist.remove(bid)
        config["whitelist_bot_ids"] = whitelist
        save_config(config)
        await ctx.send(
            f"Successfully removed bot `{bid}` from the whitelist.",
            ephemeral=bool(ctx.interaction),
        )
