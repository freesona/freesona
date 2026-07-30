# cogs/system/provider.py: Provider management commands (/provider)

import discord
from discord import app_commands
from discord.ext import commands

from utils.config import load_config, save_config, get_provider_name
from utils.config_schema import get_provider_choices, PROVIDER_CHOICES


async def provider_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    _ = interaction
    current = current.lower()
    return [
        app_commands.Choice[str](name=provider, value=provider)
        for provider in PROVIDER_CHOICES
        if current in provider.lower()
    ][:25]


class ProviderCog(commands.Cog):
    """Cog for /provider command group."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_group(name="provider", help="Show or change the active provider.")
    @commands.is_owner()
    async def provider_group(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send(
                f"Current provider: `{get_provider_name()}`",
                ephemeral=True if ctx.interaction else False,
            )

    @provider_group.command(name="show", help="Show the active provider.")  # type: ignore[attr-defined]
    @commands.is_owner()
    async def provider_show(self, ctx: commands.Context):
        await ctx.send(
            f"Current provider: `{get_provider_name()}`",
            ephemeral=True if ctx.interaction else False,
        )

    @provider_group.command(name="set", help="Set the active provider.")  # type: ignore[attr-defined]
    @commands.is_owner()
    @app_commands.autocomplete(name=provider_autocomplete)
    async def provider_set(self, ctx: commands.Context, name: str):
        normalized = name.strip().lower()
        if normalized not in PROVIDER_CHOICES:
            await ctx.send(
                f"Unknown provider `{name}`. Choose from: {', '.join(PROVIDER_CHOICES)}.",
                ephemeral=True if ctx.interaction else False,
            )
            return

        config = load_config()
        config["provider"] = normalized
        save_config(config)
        await ctx.send(
            f"Provider set to `{get_provider_name()}`.", ephemeral=True if ctx.interaction else False
        )

    @provider_group.command(name="reset", help="Reset the active provider to the environment/default value.")  # type: ignore[attr-defined]
    @commands.is_owner()
    async def provider_reset(self, ctx: commands.Context):
        config = load_config()
        config.pop("provider", None)
        save_config(config)
        await ctx.send(
            f"Provider reset to `{get_provider_name()}`.", ephemeral=True if ctx.interaction else False
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(ProviderCog(bot))