# utils/views/config_views.py: Shared UI components for config commands.
# Moved from cogs/system/admin.py to be shared across config-related cogs.


import discord
from discord import ui

from utils.config import DEFAULT_CONFIG, load_config, save_config
from utils.config_schema import (
    CONFIG_CATEGORIES,
    CONFIG_DESCRIPTIONS,
    PROVIDER_CHOICES,
    get_config_default,
    get_config_description,
)

# Allowed values for enum-like config keys
CONFIG_ALLOWED_VALUES = {
    "conversation_response_mode": ["all", "mentions", "reply", "dm"],
    "log_level": ["DEBUG", "INFO", "WARNING", "ERROR"],
    "provider": PROVIDER_CHOICES,
}


class ConfigModal(ui.Modal, title="Edit Config Value"):
    """Modal for editing a single config value."""

    def __init__(self, key: str, current_value: str, description: str):
        super().__init__(title=f"Edit {key}")
        self.key = key
        self.description = description

        self.value_input = ui.TextInput(
            label=key,
            placeholder=(
                f"Current: {current_value}"
                if current_value
                else "Enter value..."
            ),
            default=current_value,
            required=False,
            max_length=2000,
        )
        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction):
        new_value = self.value_input.value.strip()

        # Try to parse as appropriate type
        default = get_config_default(self.key)
        if default is not None:
            if isinstance(default, bool):
                if new_value.lower() in ("true", "yes", "1", "on"):
                    new_value = True
                elif new_value.lower() in ("false", "no", "0", "off"):
                    new_value = False
                else:
                    await interaction.response.send_message(
                        (
                            f"❌ Invalid boolean value for `{self.key}`. "
                            "Use true/false, yes/no, 1/0, on/off"
                        ),
                        ephemeral=True,
                    )
                    return
            elif isinstance(default, int):
                try:
                    new_value = int(new_value)
                except ValueError:
                    await interaction.response.send_message(
                        f"❌ Invalid integer value for `{self.key}`.",
                        ephemeral=True,
                    )
                    return
            elif isinstance(default, float):
                try:
                    new_value = float(new_value)
                except ValueError:
                    await interaction.response.send_message(
                        f"❌ Invalid float value for `{self.key}`.",
                        ephemeral=True,
                    )
                    return

        # Validate enum-like values
        if self.key in CONFIG_ALLOWED_VALUES:
            allowed = CONFIG_ALLOWED_VALUES[self.key]
            if str(new_value).lower() not in [v.lower() for v in allowed]:
                await interaction.response.send_message(
                    (
                        f"❌ Invalid value for `{self.key}`. "
                        f"Allowed: {', '.join(allowed)}"
                    ),
                    ephemeral=True,
                )
                return
            # Normalize to the canonical case
            for v in allowed:
                if v.lower() == str(new_value).lower():
                    new_value = v
                    break

        config = load_config()
        config[self.key] = new_value
        save_config(config)

        await interaction.response.send_message(
            f"✅ Config `{self.key}` updated to: `{new_value}`", ephemeral=True
        )


class ConfigKeySelect(ui.Select):
    """Select menu for choosing a config key to edit."""

    def __init__(
        self, keys: list[str], placeholder: str = "Select a config key..."
    ):
        options = [
            discord.SelectOption(
                label=key,
                description=CONFIG_DESCRIPTIONS.get(key, "No description")[
                    :100
                ],
                value=key,
            )
            for key in keys[:25]  # Discord limit
        ]
        super().__init__(
            placeholder=placeholder,
            options=options,
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction):
        key = self.values[0]
        config = load_config()
        current_value = config.get(key, get_config_default(key))
        description = get_config_description(key)

        modal = ConfigModal(
            key,
            str(current_value) if current_value is not None else "",
            description,
        )
        await interaction.response.send_modal(modal)


class ConfigKeySelectView(ui.View):
    """View with select menu for choosing config key to edit."""

    def __init__(self, keys: list[str]):
        super().__init__(timeout=60)
        self.add_item(ConfigKeySelect(keys))


class ConfigPanelView(ui.View):
    """Main config panel with category navigation and key editing."""

    def __init__(self, bot, mode: str = "edit"):
        super().__init__(timeout=180)
        self.bot = bot
        self.mode = mode
        self.author_id = bot.owner_id
        self.current_category: str | None = None
        self.message: discord.Message | None = None

        # Add category select
        self.add_item(ConfigCategorySelect())

    @staticmethod
    async def create_initial_embed(mode: str = "edit") -> discord.Embed:
        """Create the initial embed for the config panel."""
        if mode == "list":
            embed = discord.Embed(
                title="⚙️ Configuration Categories",
                description=(
                    "Select a category to view all config keys "
                    "and their current values."
                ),
                color=discord.Color.blurple(),
            )
        else:
            embed = discord.Embed(
                title="⚙️ Configuration Panel",
                description=(
                    "Select a category to view and edit "
                    "config values."
                ),
                color=discord.Color.blue(),
            )
        for category, keys in CONFIG_CATEGORIES.items():
            embed.add_field(
                name=category,
                value=f"{len(keys)} settings",
                inline=True,
            )
        embed.set_footer(text="Use the dropdown to select a category")
        return embed

    async def interaction_check(
        self, interaction: discord.Interaction
    ) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "You cannot interact with this panel.", ephemeral=True
            )
            return False
        return True

    def create_category_embed(self) -> discord.Embed:
        """Create embed showing all categories."""
        embed = discord.Embed(
            title="⚙️ Configuration Panel",
            description="Select a category to view and edit config values.",
            color=discord.Color.blue(),
        )
        for category, keys in CONFIG_CATEGORIES.items():
            embed.add_field(
                name=category,
                value=f"{len(keys)} settings",
                inline=True,
            )
        embed.set_footer(text="Use the dropdown to select a category")
        return embed

    def create_key_embed(self, category: str) -> discord.Embed:
        """Create embed showing keys in a category."""
        keys = CONFIG_CATEGORIES.get(category, [])
        config = load_config()

        embed = discord.Embed(
            title=f"⚙️ {category} Settings",
            description=(
                "Select a key to edit its value. "
                "Current values shown."
            ),
            color=discord.Color.green(),
        )

        for key in keys:
            current = config.get(key, get_config_default(key))
            desc = get_config_description(key)
            embed.add_field(
                name=key,
                value=f"{desc}\nCurrent: `{current}`",
                inline=False,
            )

        embed.set_footer(text=f"Category: {category} • Use dropdown to edit")
        return embed


class ConfigCategorySelect(ui.Select):
    """Select menu for choosing config category."""

    def __init__(self):
        options = [
            discord.SelectOption(
                label=category,
                description=f"{len(keys)} settings",
                value=category,
            )
            for category, keys in CONFIG_CATEGORIES.items()
        ]
        super().__init__(
            placeholder="Select a category...",
            options=options,
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction):
        from typing import cast

        view = cast(ConfigPanelView, self.view)
        view.current_category = self.values[0]
        view.clear_items()
        view.add_item(ConfigCategorySelect())
        view.add_item(
            ConfigKeySelect(CONFIG_CATEGORIES[view.current_category])
        )
        await interaction.response.edit_message(
            embed=view.create_key_embed(view.current_category), view=view
        )


class ConfigResetConfirmView(ui.View):
    """Confirmation view for resetting config to defaults."""

    def __init__(self, author_id: int, keys: list[str] | None = None):
        super().__init__(timeout=30)
        self.author_id = author_id
        self.keys = keys
        self.message: discord.Message | None = None

    async def interaction_check(
        self, interaction: discord.Interaction
    ) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "You cannot interact with this panel.", ephemeral=True
            )
            return False
        return True

    @ui.button(label="Confirm Reset", style=discord.ButtonStyle.danger)
    async def confirm(
        self, interaction: discord.Interaction, button: ui.Button
    ):
        config = load_config()
        if self.keys:
            for key in self.keys:
                if key in DEFAULT_CONFIG:
                    config[key] = DEFAULT_CONFIG[key]
        else:
            # Reset all
            config = DEFAULT_CONFIG.copy()
        save_config(config)

        await interaction.response.edit_message(
            content=(
                f"✅ Config reset to defaults"
                f"{' for selected keys' if self.keys else ''}."
            ),
            embed=None,
            view=None,
        )
        self.stop()

    @ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(
        self, interaction: discord.Interaction, button: ui.Button
    ):
        await interaction.response.edit_message(
            content="❌ Reset cancelled.", embed=None, view=None
        )
        self.stop()


class ConfigSelectView(ui.View):
    """View with a dropdown to select a config key for viewing or resetting."""

    def __init__(self, bot, mode: str = "view"):
        super().__init__(timeout=60)
        self.bot = bot
        self.mode = mode
        self.author_id = bot.owner_id
        self.add_item(ConfigKeySelectForMode(mode))

    async def interaction_check(
        self, interaction: discord.Interaction
    ) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "You cannot interact with this panel.", ephemeral=True
            )
            return False
        return True


class ConfigKeySelectForMode(ui.Select):
    """Select menu for choosing a config key for view/reset mode."""

    def __init__(self, mode: str):
        self.mode = mode
        # Flatten all keys from all categories
        all_keys = []
        for keys in CONFIG_CATEGORIES.values():
            all_keys.extend(keys)
        options = [
            discord.SelectOption(
                label=key,
                description=CONFIG_DESCRIPTIONS.get(key, "No description")[
                    :100
                ],
                value=key,
            )
            for key in sorted(all_keys)[:25]  # Discord limit
        ]
        placeholder = (
            "Select a key to view..."
            if mode == "view"
            else "Select a key to reset..."
        )
        super().__init__(
            placeholder=placeholder,
            options=options,
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction):
        key = self.values[0]
        config = load_config()
        default = DEFAULT_CONFIG.get(key)
        current = config.get(key, default)

        if self.mode == "view":
            desc = CONFIG_DESCRIPTIONS.get(key, "No description available.")
            embed = discord.Embed(
                title=f"Config: {key}",
                description=(
                    f"{desc}\n\n**Current Value:** `{current}`\n"
                    f"**Default Value:** `{default}`"
                ),
                color=discord.Color.blurple(),
            )
            await interaction.response.edit_message(embed=embed, view=None)
        else:  # reset mode
            if key in config:
                config.pop(key)
                save_config(config)
                await interaction.response.edit_message(
                    content=(
                        f"✅ Reset `{key}` to default "
                        f"(`{default}`)."
                    ),
                    embed=None,
                    view=None,
                )
            else:
                await interaction.response.edit_message(
                    content=(
                        f"`{key}` is already at default value "
                        f"(`{default}`)."
                    ),
                    embed=None,
                    view=None,
                )
