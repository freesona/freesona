# cogs/system/admin.py: Owner/admin runtime controls.

import io
import json
import logging
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Select, Modal, TextInput, Button
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from utils.config import load_config, save_config, get_provider_name, DEFAULT_CONFIG
from utils.providers import get_provider_config
from utils.modules import OPTIONAL_MODULES, load_enabled_modules, module_extension, save_module_state
from utils.logging_utils import (
    LOG_SECTIONS,
    get_section_filter,
    refresh_section_filter,
    send_log_message,
    setup_logging,
)

MODEL_CHOICES: list[str] = [
    "gemini-flash-lite-latest",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.0-flash",
]

PROVIDER_CHOICES: list[str] = ["gemini", "openai", "ollama", "nim", "azure", "groq", "openrouter"]


def is_owner_check():
    """Check if the interaction user is the bot owner (for app_commands)."""
    async def predicate(interaction: discord.Interaction) -> bool:
        try:
            # interaction.client inherits is_owner from discord.Client via commands.Bot
            # Use type: ignore to satisfy Pylance type checking since discord.Client.is_owner
            # is not recognized on the base discord.Client type in stubs
            return await interaction.client.is_owner(interaction.user)  # type: ignore[attr-defined]
        except Exception as e:
            # Log the error but don't fail silently - let the check fail
            logging.getLogger(__name__).warning(
                "is_owner_check failed for user %s: %s", interaction.user, e
            )
            return False
    return app_commands.check(predicate)


# Config key categories for organized display
CONFIG_CATEGORIES = {
    "Core": [
        "prefix",
        "conversation_response_mode",
        "provider",
        "provider_model",
    ],
    "Vector DB (Chroma)": [
        "chroma_collection",
        "chroma_persist_directory",
    ],
    "Conversation": [
        "debounce_seconds",
        "autonomy_cooldown_seconds",
        "autonomy_user_cooldown",
    ],
    "MVSEP (Music Separation)": [
        "mvsep_poll_interval",
        "mvsep_poll_timeout",
    ],
    "YT-DLP (Audio/Video)": [
        "ytdlp_subprocess_timeout",
        "ytdlp_compress_target_mb",
    ],
    "Generation (Text Splitting & Rate Limiting)": [
        "generation_split_min_length",
        "generation_split_delay_base",
        "generation_split_delay_per_char",
        "generation_split_delay_max",
        "generation_rate_limit",
    ],
    "Logging": [
        "log_enabled",
        "log_channel_id",
        "log_level",
        "log_file_path",
        "log_file_max_months",
        "log_include_discord",
    ],
    "Logging Sections": [
        "log_section_general",
        "log_section_config",
        "log_section_ai",
        "log_section_memory",
        "log_section_media",
        "log_section_moderation",
        "log_section_security",
        "log_section_webhook",
    ],
}

CONFIG_DESCRIPTIONS = {
    "prefix": "Command prefix for text commands (default: ~)",
    "conversation_response_mode": "How the bot responds in conversations: all, mention, reply (default: all)",
    "provider": "AI provider to use: gemini, openai, ollama, nim, azure, groq, openrouter (default: gemini)",
    "provider_model": "Model name for the selected provider (default: from env)",
    "chroma_collection": "ChromaDB collection name (default: freesona)",
    "chroma_persist_directory": "ChromaDB persistence directory (default: ./.chroma)",
    "debounce_seconds": "Debounce time for message processing in seconds (default: 1.2)",
    "autonomy_cooldown_seconds": "Cooldown between autonomous actions in seconds (default: 120)",
    "autonomy_user_cooldown": "Per-user cooldown for autonomous actions in seconds (default: 60)",
    "mvsep_poll_interval": "Seconds between MVSEP API polling checks (default: 10)",
    "mvsep_poll_timeout": "Max seconds to wait for MVSEP task completion (default: 600)",
    "ytdlp_subprocess_timeout": "Max seconds for yt-dlp subprocess to complete (default: 300)",
    "ytdlp_compress_target_mb": "Target size in MB for video compression (default: 9.5)",
    "generation_split_min_length": "Minimum message length before splitting into segments (default: 280)",
    "generation_split_delay_base": "Base delay in seconds between message segments (default: 1.2)",
    "generation_split_delay_per_char": "Additional delay per character in segment (default: 0.012)",
    "generation_split_delay_max": "Maximum delay between segments in seconds (default: 3.5)",
    "generation_rate_limit": "Minimum seconds between AI generation calls (default: 5)",
    "log_enabled": "Enable optional logging (default: false)",
    "log_channel_id": "Discord channel ID for log messages (default: 0, disabled)",
    "log_level": "Log level: DEBUG, INFO, WARNING, ERROR (default: INFO)",
    "log_file_path": "Log file path with monthly rotation (default: logs/freesona.log)",
    "log_file_max_months": "Log file rotation period in months (default: 3)",
    "log_include_discord": "Also send logs to Discord channel (default: true)",
    # Logging sections
    "log_section_general": "Log general bot events (startup, shutdown, cogs) (default: true)",
    "log_section_config": "Log configuration changes (default: false)",
    "log_section_ai": "Log AI provider calls, generation, prompts (default: true)",
    "log_section_memory": "Log memory operations (conversation, facts, character, canon, KB) (default: false)",
    "log_section_media": "Log media operations (MVSEP, yt-dlp, search) (default: false)",
    "log_section_moderation": "Log moderation actions (kick, ban, warn) (default: false)",
    "log_section_security": "Log security checks (injection detection, URL validation) (default: true)",
    "log_section_webhook": "Log webhook events (FastAPI/MVSEP) (default: false)",
}


def get_config_category(key: str) -> str:
    """Get the category name for a config key."""
    for category, keys in CONFIG_CATEGORIES.items():
        if key in keys:
            return category
    return "Other"


def get_config_type(key: str) -> type:
    """Get the expected type for a config key based on its default value."""
    return type(DEFAULT_CONFIG.get(key, ""))


def get_default_value(key: str):
    """Get the default value for a config key."""
    return DEFAULT_CONFIG.get(key, None)


class ConfigCategoryButton(Button):
    """Button for a config category in the panel view."""

    def __init__(self, category: str, style: discord.ButtonStyle = discord.ButtonStyle.primary, row: int | None = None):
        super().__init__(label=category, style=style, row=row)
        self.category = category

    async def callback(self, interaction: discord.Interaction):
        view: ConfigPanelView = self.view  # type: ignore
        await view.show_category(interaction, self.category)


class ConfigPanelView(View):
    """Button panel view for /config list and /config edit - similar to PersonaPanelView."""

    def __init__(self, bot: commands.Bot, mode: str = "list"):
        super().__init__(timeout=300)
        self.bot = bot
        self.mode = mode  # "list" or "edit"

        # Add category buttons
        for i, category in enumerate(CONFIG_CATEGORIES.keys()):
            row = i // 5  # 5 buttons per row (Discord limit)
            self.add_item(ConfigCategoryButton(category, row=row))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message("Owner only.", ephemeral=True)
            return False
        return True

    async def show_category(self, interaction: discord.Interaction, category: str):
        """Show keys in a category as an embed with buttons for editing."""
        keys = CONFIG_CATEGORIES.get(category, [])
        config = load_config()
        defaults = DEFAULT_CONFIG

        if self.mode == "list":
            # Show embed with all keys in category
            lines = []
            for k in keys:
                if k in defaults:
                    desc = CONFIG_DESCRIPTIONS.get(k, "No description available")
                    v = config.get(k, defaults[k])
                    diff_marker = " ⚠" if v != defaults[k] else ""
                    lines.append(f"`{k}` = `{v}`{diff_marker} — {desc}")
            if not lines:
                await interaction.response.send_message(f"No keys in category `{category}`.", ephemeral=True)
                return

            embed = discord.Embed(
                title=f"Config Keys: {category}",
                description="\n".join(lines),
                color=discord.Color.green(),
            )
            embed.set_footer(text="⚠ = differs from default | Use /config edit to change values")
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            # Edit mode: show buttons for each key
            view = ConfigKeySelectView(self.bot, category, self.mode)
            embed = discord.Embed(
                title=f"Edit Config: {category}",
                description="Select a key to edit:",
                color=discord.Color.blurple(),
            )
            await interaction.response.edit_message(embed=embed, view=view)

    @classmethod
    async def create_initial_embed(cls, mode: str) -> discord.Embed:
        """Create the initial embed showing all categories."""
        if mode == "list":
            title = "Config List"
            description = "Click a category button below to view its configuration keys."
        else:
            title = "Config Editor"
            description = "Click a category button below to edit its configuration keys."
        embed = discord.Embed(
            title=title,
            description=description,
            color=discord.Color.yellow(),
        )
        embed.add_field(
            name="Categories",
            value="\n".join(f"• {cat}" for cat in CONFIG_CATEGORIES.keys()),
            inline=False,
        )
        return embed


class ConfigKeySelectView(View):
    """View with buttons for each config key in a category."""

    def __init__(self, bot: commands.Bot, category: str, mode: str = "edit"):
        super().__init__(timeout=300)
        self.bot = bot
        self.category = category
        self.mode = mode  # "list" or "edit"

        # Add buttons for each key in the category
        keys = CONFIG_CATEGORIES.get(category, [])
        config = load_config()
        defaults = DEFAULT_CONFIG

        for key in keys:
            if key in defaults:
                current_val = config.get(key, defaults[key])
                diff_marker = " ⚠" if current_val != defaults[key] else ""
                btn = ConfigKeyButton(key, f"`{key}`{diff_marker}")
                self.add_item(btn)

        # Add back button
        self.add_item(ConfigBackButton())

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message("Owner only.", ephemeral=True)
            return False
        return True


class ConfigKeyButton(Button):
    """Button for a specific config key - opens modal to edit."""

    def __init__(self, key: str, label: str):
        # Truncate label if too long
        display_label = label[:80]
        super().__init__(label=display_label, style=discord.ButtonStyle.secondary)
        self.key = key

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ConfigModal(self.key, self.view.bot))  # type: ignore


class ConfigBackButton(Button):
    """Back button to return to category list."""

    def __init__(self):
        super().__init__(label="← Back", style=discord.ButtonStyle.danger, row=4)

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        embed = await ConfigPanelView.create_initial_embed(view.mode)
        await interaction.response.edit_message(embed=embed, view=ConfigPanelView(view.bot, view.mode))


class ConfigSelectView(View):
    """View with a dropdown to select a config key for viewing/editing."""

    def __init__(self, bot: commands.Bot, mode: str = "edit"):
        super().__init__(timeout=120)
        self.bot = bot
        self.mode = mode  # "edit", "view", or "reset"

        # Build options grouped by category
        options = []
        for category in CONFIG_CATEGORIES:
            keys = CONFIG_CATEGORIES[category]
            for key in keys:
                if key in DEFAULT_CONFIG:
                    default_val = DEFAULT_CONFIG[key]
                    config = load_config()
                    current_val = config.get(key, default_val)
                    desc = CONFIG_DESCRIPTIONS.get(key, "No description")
                    options.append(
                        discord.SelectOption(
                            label=key,
                            value=key,
                            description=f"{category}: {desc[:90]}" if len(desc) > 90 else f"{category}: {desc}",
                            default=(current_val != default_val),  # Highlight non-default values
                        )
                    )
        # Add any keys not in categories
        categorized_keys: set[str] = set()
        for keys in CONFIG_CATEGORIES.values():
            categorized_keys.update(keys)
        for key in sorted(str(config_key) for config_key in DEFAULT_CONFIG.keys()):
            if key not in categorized_keys:
                default_val = DEFAULT_CONFIG[key]
                config = load_config()
                current_val = config.get(key, default_val)
                desc = CONFIG_DESCRIPTIONS.get(key, "No description")
                options.append(
                    discord.SelectOption(
                        label=key,
                        value=key,
                        description=f"Other: {desc[:90]}",
                        default=(current_val != default_val),
                    )
                )

        # Discord limits to 25 options per select
        if len(options) > 25:
            options = options[:25]

        self.select = Select(
            placeholder="Select a config key to " + ("edit" if mode == "edit" else "view" if mode == "view" else "reset"),
            options=options,
            min_values=1,
            max_values=1,
        )
        self.select.callback = self.on_select
        self.add_item(self.select)

    async def on_select(self, interaction: discord.Interaction):
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message("Owner only.", ephemeral=True)
            return

        key = self.select.values[0]
        if self.mode == "edit":
            await interaction.response.send_modal(ConfigModal(key, self.bot))
        elif self.mode == "view":
            config = load_config()
            default_val = DEFAULT_CONFIG[key]
            current_val = config.get(key, default_val)
            desc = CONFIG_DESCRIPTIONS.get(key, "No description available.")
            cat = get_config_category(key)

            embed = discord.Embed(
                title=f"Config: {key}",
                color=discord.Color.blurple(),
            )
            embed.add_field(name="Category", value=cat, inline=True)
            embed.add_field(name="Type", value=type(default_val).__name__, inline=True)
            embed.add_field(name="Current Value", value=f"`{current_val}`", inline=False)
            embed.add_field(name="Default Value", value=f"`{default_val}`", inline=False)
            embed.add_field(name="Description", value=desc, inline=False)
            if current_val != default_val:
                embed.set_footer(text="⚠ This value differs from the default")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        elif self.mode == "reset":
            config = load_config()
            default_val = DEFAULT_CONFIG[key]
            if key in config:
                config.pop(key)
                save_config(config)
                await interaction.response.send_message(
                    f"Reset `{key}` to default (`{default_val}`).", ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"`{key}` is already at default value (`{default_val}`).", ephemeral=True
                )


class ConfigModal(Modal):
    """Modal for editing a config value with appropriate input type."""

    def __init__(self, key: str, bot: commands.Bot):
        super().__init__(title=f"Edit Config: {key}")
        self.key = key
        self.bot = bot

        default_val = DEFAULT_CONFIG[key]
        config = load_config()
        current_val = config.get(key, default_val)
        desc = CONFIG_DESCRIPTIONS.get(key, "No description available.")

        # Create appropriate TextInput based on type
        if isinstance(default_val, bool):
            self.value_input = TextInput(
                label="Value (true/false)",
                style=discord.TextStyle.short,
                placeholder="true or false",
                default=str(current_val).lower(),
                required=True,
                max_length=5,
            )
        elif isinstance(default_val, int):
            self.value_input = TextInput(
                label="Value (integer)",
                style=discord.TextStyle.short,
                placeholder=str(default_val),
                default=str(current_val),
                required=True,
                max_length=20,
            )
        elif isinstance(default_val, float):
            self.value_input = TextInput(
                label="Value (decimal)",
                style=discord.TextStyle.short,
                placeholder=str(default_val),
                default=str(current_val),
                required=True,
                max_length=20,
            )
        else:
            self.value_input = TextInput(
                label="Value (string)",
                style=discord.TextStyle.short if len(str(current_val)) < 100 else discord.TextStyle.paragraph,
                placeholder=str(default_val),
                default=str(current_val),
                required=True,
                max_length=4000,
            )

        # Add description as a label on the modal (read-only field for visibility)
        self.description_field = TextInput(
            label="Description",
            style=discord.TextStyle.paragraph,
            default=desc,
            required=False,
        )
        # Note: TextInput doesn't support disabled=True, but required=False makes it non-editable in practice

        self.add_item(self.value_input)
        self.add_item(self.description_field)

    async def on_submit(self, interaction: discord.Interaction):
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message("Owner only.", ephemeral=True)
            return

        default_val = DEFAULT_CONFIG[self.key]
        value_str = self.value_input.value.strip()

        # Type conversion
        try:
            if isinstance(default_val, bool):
                converted = value_str.lower() in ("true", "1", "yes", "on")
            elif isinstance(default_val, int):
                converted = int(value_str)
            elif isinstance(default_val, float):
                converted = float(value_str)
            else:
                converted = value_str
        except ValueError:
            await interaction.response.send_message(
                f"Invalid value for `{self.key}`: expected {type(default_val).__name__}, got `{value_str}`.",
                ephemeral=True,
            )
            return

        config = load_config()
        old_val = config.get(self.key, default_val)
        config[self.key] = converted
        save_config(config)

        embed = discord.Embed(
            title="✅ Config Updated",
            color=discord.Color.green(),
        )
        embed.add_field(name="Key", value=f"`{self.key}`", inline=True)
        embed.add_field(name="Type", value=type(default_val).__name__, inline=True)
        embed.add_field(name="Previous Value", value=f"`{old_val}`", inline=False)
        embed.add_field(name="New Value", value=f"`{converted}`", inline=False)
        if converted != default_val:
            embed.add_field(name="Default Value", value=f"`{default_val}` (differs)", inline=False)
        else:
            embed.add_field(name="Default Value", value=f"`{default_val}` (now matches)", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def module_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    _ = interaction
    current = current.lower()
    choices = []
    module_names = [str(name) for name in OPTIONAL_MODULES]
    for name in sorted(module_names):
        if current in name:
            choices.append(app_commands.Choice(name=name, value=name))
    return choices[:25]


async def model_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    _ = interaction
    current = current.lower()
    return [
        app_commands.Choice[str](name=model, value=model)
        for model in MODEL_CHOICES
        if current in model.lower()
    ][:25]


async def provider_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    _ = interaction
    current = current.lower()
    return [
        app_commands.Choice[str](name=provider, value=provider)
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

    @model_group.command(name="temperature", help="Set the model temperature (0.0-2.0).")  # type: ignore[attr-defined]
    @commands.is_owner()
    @app_commands.describe(value="Temperature value between 0.0 (deterministic) and 2.0 (very creative)")
    async def model_temperature(self, ctx, value: float):
        if value < 0.0 or value > 2.0:
            await ctx.send("Temperature must be between 0.0 and 2.0.", ephemeral=True if ctx.interaction else False)
            return
        config = load_config()
        config["model_temperature"] = value
        save_config(config)
        await ctx.send(f"Model temperature set to `{value}`.", ephemeral=True if ctx.interaction else False)

    @model_group.command(name="temperature_reset", help="Reset temperature to default (0.7).")  # type: ignore[attr-defined]
    @commands.is_owner()
    async def model_temperature_reset(self, ctx):
        config = load_config()
        config.pop("model_temperature", None)
        save_config(config)
        await ctx.send(f"Model temperature reset to default (0.7).", ephemeral=True if ctx.interaction else False)

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
    # /reboot
    # ------------------------------------------------------------------
    @commands.hybrid_command(name="reboot", help="Gracefully shutdown the bot for restart (Owner only). Requires process manager to restart.")
    @commands.is_owner()
    async def reboot_cmd(self, ctx):
        await ctx.send("Rebooting...", ephemeral=True if ctx.interaction else False)
        await self.bot.close()

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
        other_keys = [k for k in sorted(defaults.keys()) if k not in categorized_keys]
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
                await ctx.send(embed=embed, ephemeral=True if ctx.interaction else False)
        else:
            await ctx.send("No configuration values found.", ephemeral=True if ctx.interaction else False)

    @config_group.command(name="list", help="List all configurable keys with descriptions grouped by category.")  # type: ignore[attr-defined]
    @commands.is_owner()
    async def config_list(self, ctx):
        embed = await ConfigPanelView.create_initial_embed("list")
        view = ConfigPanelView(self.bot, mode="list")
        await ctx.send(embed=embed, view=view, ephemeral=True if ctx.interaction else False)

    @config_group.command(name="edit", help="Open an interactive button panel to edit config values via modal.")  # type: ignore[attr-defined]
    @commands.is_owner()
    async def config_edit(self, ctx):
        """Open a button panel to select a config category, then a key, then a modal to edit it."""
        embed = await ConfigPanelView.create_initial_embed("edit")
        view = ConfigPanelView(self.bot, mode="edit")
        await ctx.send(embed=embed, view=view, ephemeral=True if ctx.interaction else False)

    @config_group.command(name="view", help="Open an interactive dropdown to view a config value in detail.")  # type: ignore[attr-defined]
    @commands.is_owner()
    async def config_view(self, ctx):
        """Open a dropdown to select a config key, then view it in an embed."""
        view = ConfigSelectView(self.bot, mode="view")
        await ctx.send("Select a config key to view:", view=view, ephemeral=True if ctx.interaction else False)

    @config_group.command(name="reset-interactive", help="Open an interactive dropdown to reset a config key to default.")  # type: ignore[attr-defined]
    @commands.is_owner()
    async def config_reset_interactive(self, ctx):
        """Open a dropdown to select a config key, then reset it to default."""
        view = ConfigSelectView(self.bot, mode="reset")
        await ctx.send("Select a config key to reset:", view=view, ephemeral=True if ctx.interaction else False)

    @config_group.command(name="set", help="Set a configuration value directly.")  # type: ignore[attr-defined]
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


# --- Logging command group ---
logging_group = app_commands.Group(name="logging", description="Logging system control (owner only)", default_permissions=discord.Permissions(administrator=True))


@logging_group.command(name="status", description="Show current logging configuration and enabled sections")
@is_owner_check()
async def logging_status(interaction: discord.Interaction):

    config = load_config()
    section_filter = get_section_filter()

    embed = discord.Embed(
        title="📋 Logging Configuration",
        color=discord.Color.blurple(),
    )

    # Main logging settings
    embed.add_field(
        name="Core Settings",
        value=(
            f"**Enabled:** `{config.get('log_enabled', False)}`\n"
            f"**Channel ID:** `{config.get('log_channel_id', 0)}`\n"
            f"**Level:** `{config.get('log_level', 'INFO')}`\n"
            f"**File Path:** `{config.get('log_file_path', 'logs/freesona.log')}`\n"
            f"**Rotation (months):** `{config.get('log_file_max_months', 3)}`\n"
            f"**Discord Output:** `{config.get('log_include_discord', True)}`"
        ),
        inline=False,
    )

    # Section statuses
    sections = []
    for section, key in LOG_SECTIONS.items():
        enabled = config.get(key, False)
        status = "✅" if enabled else "❌"
        sections.append(f"{status} **{section}** (`{key}`): `{enabled}`")

    embed.add_field(
        name="Log Sections",
        value="\n".join(sections),
        inline=False,
    )

    # Currently enabled sections from filter
    enabled_sections = sorted(section_filter._enabled_sections)
    embed.add_field(
        name="Active Sections (from filter)",
        value=", ".join(f"`{s}`" for s in enabled_sections) if enabled_sections else "None",
        inline=False,
    )

    await interaction.response.send_message(embed=embed, ephemeral=True)


@logging_group.command(name="enable", description="Enable a logging section")
@app_commands.describe(section="Section to enable (general, config, ai, memory, media, moderation, security, webhook)")
@app_commands.choices(section=[
    app_commands.Choice(name="General", value="general"),
    app_commands.Choice(name="Config", value="config"),
    app_commands.Choice(name="AI", value="ai"),
    app_commands.Choice(name="Memory", value="memory"),
    app_commands.Choice(name="Media", value="media"),
    app_commands.Choice(name="Moderation", value="moderation"),
    app_commands.Choice(name="Security", value="security"),
    app_commands.Choice(name="Webhook", value="webhook"),
])
@is_owner_check()
async def logging_enable(interaction: discord.Interaction, section: app_commands.Choice[str]):

    key = LOG_SECTIONS.get(section.value)
    if not key:
        await interaction.response.send_message(f"Unknown section: `{section.value}`", ephemeral=True)
        return

    config = load_config()
    config[key] = True
    save_config(config)
    refresh_section_filter()

    await interaction.response.send_message(f"✅ Enabled logging section: **{section.name}** (`{key}`)", ephemeral=True)


@logging_group.command(name="disable", description="Disable a logging section")
@app_commands.describe(section="Section to disable (general, config, ai, memory, media, moderation, security, webhook)")
@app_commands.choices(section=[
    app_commands.Choice(name="General", value="general"),
    app_commands.Choice(name="Config", value="config"),
    app_commands.Choice(name="AI", value="ai"),
    app_commands.Choice(name="Memory", value="memory"),
    app_commands.Choice(name="Media", value="media"),
    app_commands.Choice(name="Moderation", value="moderation"),
    app_commands.Choice(name="Security", value="security"),
    app_commands.Choice(name="Webhook", value="webhook"),
])
@is_owner_check()
async def logging_disable(interaction: discord.Interaction, section: app_commands.Choice[str]):

    key = LOG_SECTIONS.get(section.value)
    if not key:
        await interaction.response.send_message(f"Unknown section: `{section.value}`", ephemeral=True)
        return

    config = load_config()
    config[key] = False
    save_config(config)
    refresh_section_filter()

    await interaction.response.send_message(f"❌ Disabled logging section: **{section.name}** (`{key}`)", ephemeral=True)


@logging_group.command(name="toggle", description="Toggle a logging section on/off")
@app_commands.describe(section="Section to toggle (general, config, ai, memory, media, moderation, security, webhook)")
@app_commands.choices(section=[
    app_commands.Choice(name="General", value="general"),
    app_commands.Choice(name="Config", value="config"),
    app_commands.Choice(name="AI", value="ai"),
    app_commands.Choice(name="Memory", value="memory"),
    app_commands.Choice(name="Media", value="media"),
    app_commands.Choice(name="Moderation", value="moderation"),
    app_commands.Choice(name="Security", value="security"),
    app_commands.Choice(name="Webhook", value="webhook"),
])
@is_owner_check()
async def logging_toggle(interaction: discord.Interaction, section: app_commands.Choice[str]):

    key = LOG_SECTIONS.get(section.value)
    if not key:
        await interaction.response.send_message(f"Unknown section: `{section.value}`", ephemeral=True)
        return

    config = load_config()
    new_value = not config.get(key, False)
    config[key] = new_value
    save_config(config)
    refresh_section_filter()

    status = "enabled" if new_value else "disabled"
    await interaction.response.send_message(f"🔄 Toggled logging section **{section.name}** (`{key}`) → **{status}**", ephemeral=True)


@logging_group.command(name="setchannel", description="Set the Discord channel for log output")
@app_commands.describe(channel="Discord channel to send logs to")
@is_owner_check()
async def logging_setchannel(interaction: discord.Interaction, channel: discord.TextChannel):

    config = load_config()
    config["log_channel_id"] = channel.id
    save_config(config)

    await interaction.response.send_message(f"✅ Log channel set to {channel.mention} (`{channel.id}`)", ephemeral=True)


@logging_group.command(name="clearchannel", description="Clear the Discord log channel setting")
@is_owner_check()
async def logging_clearchannel(interaction: discord.Interaction):

    config = load_config()
    config["log_channel_id"] = 0
    save_config(config)

    await interaction.response.send_message("✅ Log channel cleared.", ephemeral=True)


@logging_group.command(name="setlevel", description="Set the log level")
@app_commands.describe(level="Log level (DEBUG, INFO, WARNING, ERROR)")
@app_commands.choices(level=[
    app_commands.Choice(name="DEBUG", value="DEBUG"),
    app_commands.Choice(name="INFO", value="INFO"),
    app_commands.Choice(name="WARNING", value="WARNING"),
    app_commands.Choice(name="ERROR", value="ERROR"),
])
@is_owner_check()
async def logging_setlevel(interaction: discord.Interaction, level: app_commands.Choice[str]):

    config = load_config()
    config["log_level"] = level.value
    save_config(config)
    # Re-setup logging to apply new level
    setup_logging(interaction.client)  # type: ignore[arg-type]

    await interaction.response.send_message(f"✅ Log level set to **{level.value}**", ephemeral=True)


@logging_group.command(name="test", description="Send a test log message to the configured channel")
@app_commands.describe(message="Test message to send")
@is_owner_check()
async def logging_test(interaction: discord.Interaction, message: str = "Test log message"):

    await send_log_message(interaction.client, message, "INFO")  # type: ignore[arg-type]
    await interaction.response.send_message("✅ Test log message sent.", ephemeral=True)


# Add logging group to the bot's tree
def _add_logging_group(bot: commands.Bot):
    bot.tree.add_command(logging_group)


async def setup(bot):
    await bot.add_cog(AdminCog(bot))
    _add_logging_group(bot)
