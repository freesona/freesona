#!/usr/bin/env python3

# cogs/system/config.py: Configuration management commands (/config)



import io
import json

import discord
from discord import app_commands
from discord.ext import commands

from utils.config import DEFAULT_CONFIG, load_config, save_config
from utils.config_schema import (
    CONFIG_CATEGORIES,
)
from utils.views.config_views import (
    ConfigPanelView,
    ConfigSelectView,
)


class ConfigCog(commands.Cog):

    """Cog for /config command group."""



    def __init__(self, bot: commands.Bot):

        self.bot = bot



    @commands.hybrid_group(

        name="config", help="View or modify runtime configuration values."

    )

    @commands.is_owner()

    async def config_group(self, ctx: commands.Context):

        if ctx.invoked_subcommand is None:

            await self.config_show(ctx)



    @config_group.command(  # type: ignore[reportFunctionMemberAccess]

        name="show",

        help="Show current configuration values (optionally filtered by key).",

    )

    @app_commands.describe(

        key="Optional config key to show (e.g. mvsep_poll_interval)"

    )

    @commands.is_owner()

    async def config_show(self, ctx: commands.Context, key: str | None = None):

        config = load_config()

        defaults = DEFAULT_CONFIG



        if key:

            key = key.strip()

            if key not in defaults:

                await ctx.send(

                    f"Unknown config key: `{key}`. "

                    "Use `/config list` to see all keys.",

                    ephemeral=bool(ctx.interaction),

                )

                return

            value = config.get(key, defaults[key])

            await ctx.send(

                f"`{key}` = `{value}` "

                f"(default: `{defaults[key]}`)",

                ephemeral=bool(ctx.interaction),

            )

            return



        # Show all config values grouped by category using embeds

        embeds = []

        for category in CONFIG_CATEGORIES:

            keys = CONFIG_CATEGORIES[category]

            lines = []

            for k in keys:

                if k in defaults:

                    v = config.get(k, defaults[k])

                    diff_marker = " ⚠" if v != defaults[k] else ""

                    lines.append(f"`{k}` = `{v}`{diff_marker}")

            if lines:

                embed = discord.Embed(

                    title=f"Config: {category}",

                    description="\n".join(lines),

                    color=discord.Color.blurple(),

                )

                embed.set_footer(text="⚠ = differs from default")

                embeds.append(embed)



        # Add any uncategorized keys

        categorized_keys = set()

        for keys in CONFIG_CATEGORIES.values():

            categorized_keys.update(keys)

        other_keys = [

            k

            for k in sorted(defaults.keys())

            if k not in categorized_keys

        ]

        if other_keys:

            lines = []

            for k in other_keys:

                v = config.get(k, defaults[k])

                diff_marker = " ⚠" if v != defaults[k] else ""

                lines.append(f"`{k}` = `{v}`{diff_marker}")

            embed = discord.Embed(

                title="Config: Other",

                description="\n".join(lines),

                color=discord.Color.blurple(),

            )

            embed.set_footer(text="⚠ = differs from default")

            embeds.append(embed)



        if embeds:

            for embed in embeds:

                await ctx.send(embed=embed, ephemeral=bool(ctx.interaction))

        else:

            await ctx.send(

                "No configuration values found.",

                ephemeral=bool(ctx.interaction),

            )



    # type: ignore[attr-defined]

    @config_group.command(

        name="list",

        help=(

            "List all configurable keys with descriptions "

            "grouped by category."

        ),

    )

    @commands.is_owner()

    async def config_list(self, ctx: commands.Context):

        embed = await ConfigPanelView.create_initial_embed("list")

        view = ConfigPanelView(self.bot, mode="list")

        await ctx.send(

            embed=embed, view=view, ephemeral=bool(ctx.interaction)

        )



    # type: ignore[attr-defined]

    @config_group.command(

        name="edit",

        help=(

            "Open an interactive button panel to edit "

            "config values via modal."

        ),

    )

    @commands.is_owner()

    async def config_edit(self, ctx: commands.Context):

        """Open a button panel to select a config category,

        then a key, then a modal to edit it."""

        embed = await ConfigPanelView.create_initial_embed("edit")

        view = ConfigPanelView(self.bot, mode="edit")

        await ctx.send(embed=embed, view=view, ephemeral=bool(ctx.interaction))



    # type: ignore[attr-defined]

    @config_group.command(

        name="view",

        help="Open an interactive dropdown to view a config value in detail.",

    )

    @commands.is_owner()

    async def config_view(self, ctx: commands.Context):

        """Open a dropdown to select a config key, then view it in an embed."""

        view = ConfigSelectView(self.bot, mode="view")

        await ctx.send(

            "Select a config key to view:",

            view=view,

            ephemeral=bool(ctx.interaction),

        )



    # type: ignore[attr-defined]

    @config_group.command(

        name="reset-interactive",

        help=(

            "Open an interactive dropdown to reset a config "

            "key to default."

        ),

    )

    @commands.is_owner()

    async def config_reset_interactive(self, ctx: commands.Context):

        """Open a dropdown to select a config key, then reset it to default."""

        view = ConfigSelectView(self.bot, mode="reset")

        await ctx.send(

            "Select a config key to reset:",

            view=view,

            ephemeral=bool(ctx.interaction),

        )



    # type: ignore[attr-defined]

    @config_group.command(

        name="set", help="Set a configuration value directly."

    )

    @app_commands.describe(

        key="Config key to set",

        value="New value (will be type-converted)",

    )

    @commands.is_owner()

    async def config_set(self, ctx: commands.Context, key: str, value: str):

        key = key.strip()

        if key not in DEFAULT_CONFIG:

            await ctx.send(

                f"Unknown config key: `{key}`. "

                "Use `/config list` to see all keys.",

                ephemeral=bool(ctx.interaction),

            )

            return



        # Type conversion based on default value

        default_val = DEFAULT_CONFIG[key]

        try:

            if isinstance(default_val, bool):

                converted = value.lower() in (

                    "true",

                    "1",

                    "yes",

                    "on",

                )

            elif isinstance(default_val, int):

                converted = int(value)

            elif isinstance(default_val, float):

                converted = float(value)

            else:

                converted = value

        except ValueError:

            await ctx.send(

                f"Invalid value for `{key}`: expected "

                f"{type(default_val).__name__}, got `{value}`.",

                ephemeral=bool(ctx.interaction),

            )

            return



        config = load_config()

        config[key] = converted

        save_config(config)

        await ctx.send(

            f"Set `{key}` = `{converted}` "

            f"(was `{config.get(key, default_val)}`).",

            ephemeral=bool(ctx.interaction),

        )



    # type: ignore[attr-defined]

    @config_group.command(

        name="reset",

        help=(

            "Reset a configuration key to its default value."

        ),

    )

    @app_commands.describe(key="Config key to reset")

    @commands.is_owner()

    async def config_reset(self, ctx: commands.Context, key: str):

        key = key.strip()

        if key not in DEFAULT_CONFIG:

            await ctx.send(

                f"Unknown config key: `{key}`. "

                "Use `/config list` to see all keys.",

                ephemeral=bool(ctx.interaction),

            )

            return



        config = load_config()

        if key in config:

            config.pop(key)

            save_config(config)

            await ctx.send(

                f"Reset `{key}` to default "

                f"(`{DEFAULT_CONFIG[key]}`).",

                ephemeral=bool(ctx.interaction),

            )

        else:

            await ctx.send(

                f"`{key}` is already at default value "

                f"(`{DEFAULT_CONFIG[key]}`).",

                ephemeral=bool(ctx.interaction),

            )



    # type: ignore[attr-defined]

    @config_group.command(

        name="dump",

        help="Dump the current config.json contents.",

    )

    @commands.is_owner()

    async def config_dump(self, ctx: commands.Context):

        config = load_config()

        formatted = json.dumps(config, indent=2)

        if len(formatted) > 1990:

            await ctx.send(

                file=discord.File(

                    fp=io.BytesIO(formatted.encode("utf-8")),

                    filename="config.json",

                ),

                ephemeral=bool(ctx.interaction),

            )

        else:

            await ctx.send(

                f"```json\n{formatted}\n```",

                ephemeral=bool(ctx.interaction),

            )





async def setup(bot: commands.Bot):

    await bot.add_cog(ConfigCog(bot))

