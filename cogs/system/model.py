# cogs/system/model.py: Model management commands (/model)

import discord
from discord import app_commands
from discord.ext import commands

from utils.config import load_config, save_config
from utils.providers import get_provider_config
from utils.config_schema import get_model_choices, MODEL_CHOICES


async def model_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    _ = interaction
    current = current.lower()
    # Flatten all model choices from all providers
    all_models = []
    for models in MODEL_CHOICES.values():
        all_models.extend(models)
    return [
        app_commands.Choice[str](name=model, value=model)
        for model in all_models
        if current in model.lower()
    ][:25]


class ModelCog(commands.Cog):
    """Cog for /model command group."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_group(name="model", help="Show or change the active model.")
    @commands.is_owner()
    async def model_group(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            config = get_provider_config()
            await ctx.send(
                f"Current provider: `{config['provider']}`\nCurrent model: `{config['model']}`",
                ephemeral=True if ctx.interaction else False,
            )

    @model_group.command(name="show", help="Show the active provider and model.")  # type: ignore[attr-defined]
    @commands.is_owner()
    async def model_show(self, ctx: commands.Context):
        config = get_provider_config()
        await ctx.send(
            f"Current provider: `{config['provider']}`\nCurrent model: `{config['model']}`",
            ephemeral=True if ctx.interaction else False,
        )

    @model_group.command(name="set", help="Set the active model.")  # type: ignore[attr-defined]
    @commands.is_owner()
    @app_commands.autocomplete(name=model_autocomplete)
    async def model_set(self, ctx: commands.Context, name: str):
        config = load_config()
        config["model_name"] = name.strip()
        config["provider_model"] = name.strip()
        save_config(config)
        config = get_provider_config()
        await ctx.send(
            f"Model set to `{config['model']}`.", ephemeral=True if ctx.interaction else False
        )

    @model_group.command(name="reset", help="Reset the model to the environment/default value.")  # type: ignore[attr-defined]
    @commands.is_owner()
    async def model_reset(self, ctx: commands.Context):
        config = load_config()
        config.pop("model_name", None)
        config.pop("provider_model", None)
        save_config(config)
        config = get_provider_config()
        await ctx.send(
            f"Model reset to `{config['model']}`.", ephemeral=True if ctx.interaction else False
        )

    @model_group.command(name="temperature", help="Set the model temperature (0.0-2.0).")  # type: ignore[attr-defined]
    @commands.is_owner()
    @app_commands.describe(value="Temperature value between 0.0 (deterministic) and 2.0 (very creative)")
    async def model_temperature(self, ctx: commands.Context, value: float):
        if value < 0.0 or value > 2.0:
            await ctx.send(
                "Temperature must be between 0.0 and 2.0.",
                ephemeral=True if ctx.interaction else False,
            )
            return
        config = load_config()
        config["model_temperature"] = value
        save_config(config)
        await ctx.send(
            f"Model temperature set to `{value}`.", ephemeral=True if ctx.interaction else False
        )

    @model_group.command(name="temperature_reset", help="Reset temperature to default (0.7).")  # type: ignore[attr-defined]
    @commands.is_owner()
    async def model_temperature_reset(self, ctx: commands.Context):
        config = load_config()
        config.pop("model_temperature", None)
        save_config(config)
        await ctx.send(
            f"Model temperature reset to default (0.7).",
            ephemeral=True if ctx.interaction else False,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(ModelCog(bot))