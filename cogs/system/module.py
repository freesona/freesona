# cogs/system/module.py: Module management commands (/module)

import discord
from discord import app_commands
from discord.ext import commands

from utils.config import load_config, save_config
from utils.modules import OPTIONAL_MODULES, load_enabled_modules, module_extension, save_module_state


async def module_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    _ = interaction
    current = current.lower()
    choices = []
    module_names = [str(name) for name in OPTIONAL_MODULES]
    for name in sorted(module_names):
        if current in name:
            choices.append(app_commands.Choice(name=name, value=name))
    return choices[:25]


class ModuleCog(commands.Cog):
    """Cog for /module command group."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_group(name="module", help="List or change enabled bot modules.")
    @commands.has_permissions(administrator=True)
    async def module_group(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send(
                "Use `/module list`, `/module enable`, `/module disable`, or `/module reload`.",
                ephemeral=True if ctx.interaction else False,
            )

    @module_group.command(name="list", help="List enabled and disabled modules.")  # type: ignore[attr-defined]
    @commands.has_permissions(administrator=True)
    async def module_list(self, ctx: commands.Context):
        config = load_config()
        enabled = load_enabled_modules(config)
        lines = []
        for name, ext in OPTIONAL_MODULES.items():
            configured = enabled.get(name, True)
            loaded = ext in self.bot.extensions
            state = "on" if configured else "off"
            runtime = "loaded" if loaded else "unloaded"
            lines.append(f"`{name}`: {state} ({runtime})")

        embed = discord.Embed(
            title="Modules",
            description="\n".join(lines),
            color=discord.Color.blurple(),
        )
        await ctx.send(embed=embed, ephemeral=True if ctx.interaction else False)

    @module_group.command(name="enable", help="Enable a module and load it now.")  # type: ignore[attr-defined]
    @commands.has_permissions(administrator=True)
    @app_commands.autocomplete(name=module_autocomplete)
    async def module_enable(self, ctx: commands.Context, name: str):
        key = name.lower().strip()
        ext = module_extension(key)
        if ext is None:
            await ctx.send(
                f"Unknown module `{key}`.",
                ephemeral=True if ctx.interaction else False,
            )
            return

        config = load_config()
        enabled = load_enabled_modules(config)
        if key == "mvsep" and not enabled.get("ytdlp", True):
            await ctx.send(
                "Enable `ytdlp` before enabling `mvsep`.",
                ephemeral=True if ctx.interaction else False,
            )
            return

        if ext not in self.bot.extensions:
            try:
                await self.bot.load_extension(ext)
            except Exception as e:
                await ctx.send(
                    f"Could not load `{key}`: `{e}`",
                    ephemeral=True if ctx.interaction else False,
                )
                return

        save_module_state(config, key, True)
        save_config(config)
        await self.bot.tree.sync()
        await ctx.send(
            f"Module `{key}` enabled.", ephemeral=True if ctx.interaction else False
        )

    @module_group.command(name="disable", help="Disable a module and unload it now.")  # type: ignore[attr-defined]
    @commands.has_permissions(administrator=True)
    @app_commands.autocomplete(name=module_autocomplete)
    async def module_disable(self, ctx: commands.Context, name: str):
        key = name.lower().strip()
        ext = module_extension(key)
        if ext is None:
            await ctx.send(
                f"Unknown module `{key}`.",
                ephemeral=True if ctx.interaction else False,
            )
            return

        config = load_config()
        enabled = load_enabled_modules(config)
        if key == "ytdlp" and enabled.get("mvsep", True):
            await ctx.send(
                "Disable `mvsep` before disabling `ytdlp`.",
                ephemeral=True if ctx.interaction else False,
            )
            return

        if ext in self.bot.extensions:
            try:
                await self.bot.unload_extension(ext)
            except Exception as e:
                await ctx.send(
                    f"Could not unload `{key}`: `{e}`",
                    ephemeral=True if ctx.interaction else False,
                )
                return

        save_module_state(config, key, False)
        save_config(config)
        await self.bot.tree.sync()
        await ctx.send(
            f"Module `{key}` disabled.", ephemeral=True if ctx.interaction else False
        )

    @module_group.command(name="reload", help="Reload an enabled module.")  # type: ignore[attr-defined]
    @commands.has_permissions(administrator=True)
    @app_commands.autocomplete(name=module_autocomplete)
    async def module_reload(self, ctx: commands.Context, name: str):
        key = name.lower().strip()
        ext = module_extension(key)
        if ext is None:
            await ctx.send(
                f"Unknown module `{key}`.",
                ephemeral=True if ctx.interaction else False,
            )
            return

        config = load_config()
        enabled = load_enabled_modules(config)
        if not enabled.get(key, True):
            await ctx.send(
                f"Module `{key}` is disabled. Enable it first.",
                ephemeral=True if ctx.interaction else False,
            )
            return

        try:
            if ext in self.bot.extensions:
                await self.bot.reload_extension(ext)
            else:
                await self.bot.load_extension(ext)
        except Exception as e:
            await ctx.send(
                f"Reload failed for `{key}`: `{e}`",
                ephemeral=True if ctx.interaction else False,
            )
            return

        await self.bot.tree.sync()
        await ctx.send(
            f"Module `{key}` reloaded.", ephemeral=True if ctx.interaction else False
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(ModuleCog(bot))