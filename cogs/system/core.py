# cogs/system/core.py: Core system commands (/sync, /reboot, /dumpconfig)

import io
import json
import discord
from discord.ext import commands


class CoreCog(commands.Cog):
    """Cog for core system commands: /sync, /reboot, /dumpconfig."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="sync", help="Sync all global slash commands (Owner only).")
    @commands.is_owner()
    async def sync_commands(self, ctx: commands.Context):
        await ctx.defer(ephemeral=True)
        try:
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

    @commands.hybrid_command(name="dumpconfig", help="Dumps the current config.json contents (Owner only).")
    @commands.is_owner()
    async def dumpconfig_cmd(self, ctx: commands.Context):
        from utils.config import load_config
        config = load_config()
        formatted = json.dumps(config, indent=2)
        if len(formatted) > 1990:
            await ctx.send(
                file=discord.File(fp=io.BytesIO(formatted.encode("utf-8")), filename="config.json"),
                ephemeral=True if ctx.interaction else False
            )
        else:
            await ctx.send(f"```json\n{formatted}\n```", ephemeral=True if ctx.interaction else False)


async def setup(bot: commands.Bot):
    await bot.add_cog(CoreCog(bot))