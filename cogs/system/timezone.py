# cogs/system/timezone.py: Timezone commands (/settimezone, /timezone)

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import discord
import pytz
from discord import app_commands
from discord.ext import commands

from utils.config import load_config, save_config


async def timezone_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    return [
        app_commands.Choice(name=tz, value=tz)
        for tz in pytz.common_timezones
        if current.lower() in tz.lower()
    ][:25]


class TimezoneCog(commands.Cog):
    """Cog for timezone commands: /settimezone, /timezone."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(
        name="settimezone",
        help="Set the bot's timezone for time-sensitive features.",
        usage="<timezone>",
    )
    @commands.has_permissions(administrator=True)
    @discord.app_commands.describe(
        timezone=("IANA timezone string, e.g. Asia/Manila, America/New_York, UTC")
    )
    @discord.app_commands.autocomplete(timezone=timezone_autocomplete)
    async def settimezone_cmd(self, ctx: commands.Context, timezone: str):
        try:
            ZoneInfo(timezone)
        except ZoneInfoNotFoundError:
            await ctx.send(
                f"`{timezone}` is not a valid IANA timezone. "
                "Examples: `Asia/Manila`, `America/New_York`, "
                "`Europe/London`, `UTC`.",
                ephemeral=bool(ctx.interaction),
            )
            return

        config = load_config()
        config["timezone"] = timezone
        save_config(config)
        await ctx.send(
            f"Timezone set to `{timezone}`.", ephemeral=bool(ctx.interaction)
        )

    @commands.hybrid_command(
        name="timezone",
        aliases=["showtimezone", "viewtimezone"],
        help="Show the bot's currently configured timezone.",
    )
    async def timezone_cmd(self, ctx: commands.Context):
        config = load_config()
        tz = config.get("timezone", "UTC")
        await ctx.send(
            f"Current bot timezone is `{tz}`.", ephemeral=bool(ctx.interaction)
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(TimezoneCog(bot))
