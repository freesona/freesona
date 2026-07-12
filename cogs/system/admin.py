# cogs/system/admin.py: Owner/admin runtime controls.

import io
import json
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from utils.config import load_config, save_config, get_model_name, get_provider_name, DEFAULT_CONFIG
from utils.providers import get_provider_config
from utils.modules import OPTIONAL_MODULES, load_enabled_modules, module_extension, save_module_state

MODEL_CHOICES = [
    "gemini-flash-lite-latest",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.0-flash",
]

PROVIDER_CHOICES = ["gemini", "openai", "anthropic", "nvidia-nim"]


async def module_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    current = current.lower()
    choices = []
    for name in sorted(OPTIONAL_MODULES):
        if current in name:
            choices.append(app_commands.Choice(name=name, value=name))
    return choices[:25]


async def model_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    current = current.lower()
    return [
        app_commands.Choice(name=model, value=model)
        for model in MODEL_CHOICES
        if current in model.lower()
    ][:25]


async def provider_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    current = current.lower()
    return [
        app_commands.Choice(name=provider, value=provider)
        for provider in PROVIDER_CHOICES
        if current in provider.lower()
    ][:25]


class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ------------------------------------------------------------------
    # /module
    # ------------------------------------------------------------------
    @commands.hybrid_group(name="module", help="List or change enabled bot modules.")
    @commands.has_permissions(administrator=True)
    async def module_group(self, ctx):
        if ctx.invoked_subcommand is None:
            await ctx.send("Use `/module list`, `/module enable`, `/module disable`, or `/module reload`.", ephemeral=True if ctx.interaction else False)

    @module_group.command(name="list", help="List enabled and disabled modules.")  # type: ignore[attr-defined]
    @commands.has_permissions(administrator=True)
    async def module_list(self, ctx):
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
    async def module_enable(self, ctx, name: str):
        key = name.lower().strip()
        ext = module_extension(key)
        if ext is None:
            await ctx.send(f"Unknown module `{key}`.", ephemeral=True if ctx.interaction else False)
            return

        config = load_config()
        enabled = load_enabled_modules(config)
        if key == "mvsep" and not enabled.get("ytdlp", True):
            await ctx.send("Enable `ytdlp` before enabling `mvsep`.", ephemeral=True if ctx.interaction else False)
            return

        if ext not in self.bot.extensions:
            try:
                await self.bot.load_extension(ext)
            except Exception as e:
                await ctx.send(f"Could not load `{key}`: `{e}`", ephemeral=True if ctx.interaction else False)
                return

        save_module_state(config, key, True)
        save_config(config)
        await self.bot.tree.sync()
        await ctx.send(f"Module `{key}` enabled.", ephemeral=True if ctx.interaction else False)

    @module_group.command(name="disable", help="Disable a module and unload it now.")  # type: ignore[attr-defined]
    @commands.has_permissions(administrator=True)
    @app_commands.autocomplete(name=module_autocomplete)
    async def module_disable(self, ctx, name: str):
        key = name.lower().strip()
        ext = module_extension(key)
        if ext is None:
            await ctx.send(f"Unknown module `{key}`.", ephemeral=True if ctx.interaction else False)
            return

        config = load_config()
        enabled = load_enabled_modules(config)
        if key == "ytdlp" and enabled.get("mvsep", True):
            await ctx.send("Disable `mvsep` before disabling `ytdlp`.", ephemeral=True if ctx.interaction else False)
            return

        if ext in self.bot.extensions:
            try:
                await self.bot.unload_extension(ext)
            except Exception as e:
                await ctx.send(f"Could not unload `{key}`: `{e}`", ephemeral=True if ctx.interaction else False)
                return

        save_module_state(config, key, False)
        save_config(config)
        await self.bot.tree.sync()
        await ctx.send(f"Module `{key}` disabled.", ephemeral=True if ctx.interaction else False)

    @module_group.command(name="reload", help="Reload an enabled module.")  # type: ignore[attr-defined]
    @commands.has_permissions(administrator=True)
    @app_commands.autocomplete(name=module_autocomplete)
    async def module_reload(self, ctx, name: str):
        key = name.lower().strip()
        ext = module_extension(key)
        if ext is None:
            await ctx.send(f"Unknown module `{key}`.", ephemeral=True if ctx.interaction else False)
            return

        config = load_config()
        enabled = load_enabled_modules(config)
        if not enabled.get(key, True):
            await ctx.send(f"Module `{key}` is disabled. Enable it first.", ephemeral=True if ctx.interaction else False)
            return

        try:
            if ext in self.bot.extensions:
                await self.bot.reload_extension(ext)
            else:
                await self.bot.load_extension(ext)
        except Exception as e:
            await ctx.send(f"Reload failed for `{key}`: `{e}`", ephemeral=True if ctx.interaction else False)
            return

        await self.bot.tree.sync()
        await ctx.send(f"Module `{key}` reloaded.", ephemeral=True if ctx.interaction else False)

    # ------------------------------------------------------------------
    # /model
    # ------------------------------------------------------------------
    @commands.hybrid_group(name="model", help="Show or change the active model.")
    @commands.is_owner()
    async def model_group(self, ctx):
        if ctx.invoked_subcommand is None:
            config = get_provider_config()
            await ctx.send(f"Current provider: `{config['provider']}`\nCurrent model: `{config['model']}`", ephemeral=True if ctx.interaction else False)

    @model_group.command(name="show", help="Show the active provider and model.")  # type: ignore[attr-defined]
    @commands.is_owner()
    async def model_show(self, ctx):
        config = get_provider_config()
        await ctx.send(f"Current provider: `{config['provider']}`\nCurrent model: `{config['model']}`", ephemeral=True if ctx.interaction else False)

    @model_group.command(name="set", help="Set the active model.")  # type: ignore[attr-defined]
    @commands.is_owner()
    @app_commands.autocomplete(name=model_autocomplete)
    async def model_set(self, ctx, name: str):
        config = load_config()
        config["model_name"] = name.strip()
        config["provider_model"] = name.strip()
        save_config(config)
        config = get_provider_config()
        await ctx.send(f"Model set to `{config['model']}`.", ephemeral=True if ctx.interaction else False)

    @model_group.command(name="reset", help="Reset the model to the environment/default value.")  # type: ignore[attr-defined]
    @commands.is_owner()
    async def model_reset(self, ctx):
        config = load_config()
        config.pop("model_name", None)
        config.pop("provider_model", None)
        save_config(config)
        config = get_provider_config()
        await ctx.send(f"Model reset to `{config['model']}`.", ephemeral=True if ctx.interaction else False)

    # ------------------------------------------------------------------
    # /provider
    # ------------------------------------------------------------------
    @commands.hybrid_group(name="provider", help="Show or change the active provider.")
    @commands.is_owner()
    async def provider_group(self, ctx):
        if ctx.invoked_subcommand is None:
            await ctx.send(f"Current provider: `{get_provider_name()}`", ephemeral=True if ctx.interaction else False)

    @provider_group.command(name="show", help="Show the active provider.")  # type: ignore[attr-defined]
    @commands.is_owner()
    async def provider_show(self, ctx):
        await ctx.send(f"Current provider: `{get_provider_name()}`", ephemeral=True if ctx.interaction else False)

    @provider_group.command(name="set", help="Set the active provider.")  # type: ignore[attr-defined]
    @commands.is_owner()
    @app_commands.autocomplete(name=provider_autocomplete)
    async def provider_set(self, ctx, name: str):
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
        await ctx.send(f"Provider set to `{get_provider_name()}`.", ephemeral=True if ctx.interaction else False)

    @provider_group.command(name="reset", help="Reset the active provider to the environment/default value.")  # type: ignore[attr-defined]
    @commands.is_owner()
    async def provider_reset(self, ctx):
        config = load_config()
        config.pop("provider", None)
        save_config(config)
        await ctx.send(f"Provider reset to `{get_provider_name()}`.", ephemeral=True if ctx.interaction else False)

    # ------------------------------------------------------------------
    # /sync
    # ------------------------------------------------------------------
    @commands.hybrid_command(name="sync", help="Sync all global slash commands (Owner only).")
    @commands.is_owner()
    async def sync_commands(self, ctx):
        await ctx.defer(ephemeral=True)
        try:
            synced = await self.bot.tree.sync()
            await ctx.send(f"Synced {len(synced)} commands.", ephemeral=True)
        except Exception as e:
            await ctx.send(f"Sync failed: {e}", ephemeral=True)

    # ------------------------------------------------------------------
    # /settimezone
    # ------------------------------------------------------------------
    @commands.hybrid_command(name="settimezone", help="Set the bot's timezone for time-sensitive features.", usage="<timezone>")
    @app_commands.describe(timezone="IANA timezone string, e.g. Asia/Manila, America/New_York, UTC")
    @commands.has_permissions(administrator=True)
    async def settimezone_cmd(self, ctx, timezone: str):
        try:
            ZoneInfo(timezone)
        except ZoneInfoNotFoundError:
            await ctx.send(
                f"`{timezone}` is not a valid IANA timezone. "
                "Examples: `Asia/Manila`, `America/New_York`, `Europe/London`, `UTC`.",
                ephemeral=True if ctx.interaction else False
            )
            return

        config = load_config()
        config["timezone"] = timezone
        save_config(config)
        await ctx.send(f"Timezone set to `{timezone}`.", ephemeral=True if ctx.interaction else False)

    # ------------------------------------------------------------------
    # /timezone
    # ------------------------------------------------------------------
    @commands.hybrid_command(name="timezone", aliases=["showtimezone", "viewtimezone"], help="Show the bot's currently configured timezone.")
    async def timezone_cmd(self, ctx):
        config = load_config()
        tz = config.get("timezone", "UTC")
        await ctx.send(f"Current bot timezone is `{tz}`.", ephemeral=True if ctx.interaction else False)

    # ------------------------------------------------------------------
    # /dumpconfig
    # ------------------------------------------------------------------
    @commands.hybrid_command(name="dumpconfig", help="Dumps the current config.json contents (Owner only).")
    @commands.is_owner()
    async def dumpconfig_cmd(self, ctx):
        config = load_config()
        formatted = json.dumps(config, indent=2)
        if len(formatted) > 1990:
            await ctx.send(
                file=discord.File(fp=io.BytesIO(formatted.encode("utf-8")), filename="config.json"),
                ephemeral=True if ctx.interaction else False
            )
        else:
            await ctx.send(f"```json\n{formatted}\n```", ephemeral=True if ctx.interaction else False)

    # ------------------------------------------------------------------
    # /config
    # ------------------------------------------------------------------
    @commands.hybrid_group(name="config", help="View or modify runtime configuration values.")
    @commands.is_owner()
    async def config_group(self, ctx):
        if ctx.invoked_subcommand is None:
            await self.config_show(ctx)

    @config_group.command(name="show", help="Show current configuration values (optionally filtered by key).")  # type: ignore[attr-defined]
    @app_commands.describe(key="Optional config key to show (e.g. mvsep_poll_interval)")
    @commands.is_owner()
    async def config_show(self, ctx, key: Optional[str] = None):
        config = load_config()
        defaults = DEFAULT_CONFIG

        if key:
            key = key.strip()
            if key not in defaults:
                await ctx.send(f"Unknown config key: `{key}`. Use `/config list` to see all keys.", ephemeral=True if ctx.interaction else False)
                return
            value = config.get(key, defaults[key])
            await ctx.send(f"`{key}` = `{value}` (default: `{defaults[key]}`)", ephemeral=True if ctx.interaction else False)
            return

        # Show all config values
        lines = []
        for k in sorted(defaults.keys()):
            v = config.get(k, defaults[k])
            lines.append(f"`{k}` = `{v}` (default: `{defaults[k]}`)")
        output = "\n".join(lines)
        if len(output) > 1990:
            await ctx.send(
                file=discord.File(fp=io.BytesIO(output.encode("utf-8")), filename="config.txt"),
                ephemeral=True if ctx.interaction else False
            )
        else:
            await ctx.send(f"```\n{output}\n```", ephemeral=True if ctx.interaction else False)

    @config_group.command(name="list", help="List all configurable keys with descriptions.")  # type: ignore[attr-defined]
    @commands.is_owner()
    async def config_list(self, ctx):
        descriptions = {
            "mvsep_poll_interval": "Seconds between MVSEP API polling checks (default: 5)",
            "mvsep_poll_timeout": "Max seconds to wait for MVSEP task completion (default: 300)",
            "ytdlp_subprocess_timeout": "Max seconds for yt-dlp subprocess to complete (default: 300)",
            "ytdlp_compress_target_mb": "Target size in MB for video compression (default: 9.5)",
            "generation_split_min_length": "Minimum message length before splitting into segments (default: 1900)",
            "generation_split_delay_base": "Base delay in seconds between message segments (default: 0.5)",
            "generation_split_delay_per_char": "Additional delay per character in segment (default: 0.001)",
            "generation_split_delay_max": "Maximum delay between segments in seconds (default: 3.0)",
            "generation_rate_limit": "Minimum seconds between AI generation calls (default: 1.0)",
        }
        lines = []
        for k in sorted(DEFAULT_CONFIG.keys()):
            desc = descriptions.get(k, "No description available")
            lines.append(f"`{k}` — {desc}")
        output = "\n".join(lines)
        await ctx.send(f"```\n{output}\n```", ephemeral=True if ctx.interaction else False)

    @config_group.command(name="set", help="Set a configuration value.")  # type: ignore[attr-defined]
    @app_commands.describe(key="Config key to set", value="New value (will be type-converted)")
    @commands.is_owner()
    async def config_set(self, ctx, key: str, value: str):
        key = key.strip()
        if key not in DEFAULT_CONFIG:
            await ctx.send(f"Unknown config key: `{key}`. Use `/config list` to see all keys.", ephemeral=True if ctx.interaction else False)
            return

        # Type conversion based on default value
        default_val = DEFAULT_CONFIG[key]
        try:
            if isinstance(default_val, bool):
                converted = value.lower() in ("true", "1", "yes", "on")
            elif isinstance(default_val, int):
                converted = int(value)
            elif isinstance(default_val, float):
                converted = float(value)
            else:
                converted = value
        except ValueError:
            await ctx.send(f"Invalid value for `{key}`: expected {type(default_val).__name__}, got `{value}`.", ephemeral=True if ctx.interaction else False)
            return

        config = load_config()
        config[key] = converted
        save_config(config)
        await ctx.send(f"Set `{key}` = `{converted}` (was `{config.get(key, default_val)}`).", ephemeral=True if ctx.interaction else False)

    @config_group.command(name="reset", help="Reset a configuration key to its default value.")  # type: ignore[attr-defined]
    @app_commands.describe(key="Config key to reset")
    @commands.is_owner()
    async def config_reset(self, ctx, key: str):
        key = key.strip()
        if key not in DEFAULT_CONFIG:
            await ctx.send(f"Unknown config key: `{key}`. Use `/config list` to see all keys.", ephemeral=True if ctx.interaction else False)
            return

        config = load_config()
        if key in config:
            config.pop(key)
            save_config(config)
            await ctx.send(f"Reset `{key}` to default (`{DEFAULT_CONFIG[key]}`).", ephemeral=True if ctx.interaction else False)
        else:
            await ctx.send(f"`{key}` is already at default value (`{DEFAULT_CONFIG[key]}`).", ephemeral=True if ctx.interaction else False)


async def setup(bot):
    await bot.add_cog(AdminCog(bot))