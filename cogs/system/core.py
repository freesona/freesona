# cogs/system/core.py: Core system commands (/sync, /reboot)

import discord
from discord import app_commands
from discord.ext import commands


class CoreCog(commands.Cog):
    """Cog for core system commands: /sync, /reboot."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="sync", help="Sync all global slash commands (Owner only).")
    @app_commands.describe(guild="Optional guild ID to sync to (for development)")
    @commands.is_owner()
    async def sync_commands(self, ctx: commands.Context, guild: discord.Object | None = None):
        await ctx.defer(ephemeral=True)
        try:
            if guild:
                synced = await self.bot.tree.sync(guild=guild)
            else:
                synced = await self.bot.tree.sync()
            await ctx.send(f"Synced {len(synced)} commands.", ephemeral=True)
        except Exception as e:
            await ctx.send(f"Sync failed: {e}", ephemeral=True)

    @commands.hybrid_command(
        name="reboot",
        help="Gracefully shutdown the bot for restart (Owner only). Requires process manager to restart."
    )
    @commands.is_owner()
    async def reboot_cmd(self, ctx: commands.Context):
        await ctx.send("Rebooting...", ephemeral=True if ctx.interaction else False)
        await self.bot.close()


async def setup(bot: commands.Bot):
    await bot.add_cog(CoreCog(bot))