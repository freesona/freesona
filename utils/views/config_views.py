#!/usr/bin/env python3

# utils/views/config_views.py: Shared UI components for config commands.
# Moved from cogs/system/admin.py to be shared across config-related cogs.

import copy

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

# Discord caps select menus at 25 options, so longer key lists are paginated.
PAGE_SIZE = 25

# Keys whose name contains one of these are masked in embeds and messages.
SENSITIVE_MARKERS = ("token", "secret", "password", "api_key", "apikey", "webhook")

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def is_sensitive(key: str) -> bool:
    lowered = key.lower()
    return any(marker in lowered for marker in SENSITIVE_MARKERS)

def display_value(key: str, value) -> str:
    """Format a config value for display, masking secrets and truncating."""
    if is_sensitive(key) and value not in (None, ""):
        return "<hidden>"
    text = str(value)
    return text if len(text) <= 200 else text[:197] + "..."

def page_count(total: int) -> int:
    return max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

def page_slice(items: list, page: int) -> list:
    start = page * PAGE_SIZE
    return items[start : start + PAGE_SIZE]

def reset_key(config: dict, key: str) -> None:
    """Reset one key the same way everywhere: write the default if known."""
    if key in DEFAULT_CONFIG:
        config[key] = copy.deepcopy(DEFAULT_CONFIG[key])
    else:
        config.pop(key, None)

def coerce_value(key: str, raw: str):
    """Convert raw modal text to the right type. Raises ValueError on bad input."""
    raw = raw.strip()
    default = get_config_default(key)

    # Clearing a non-text field (or an enum field) resets it to the default.
    if (
        default is not None
        and raw == ""
        and (not isinstance(default, str) or key in CONFIG_ALLOWED_VALUES)
    ):
        return default

    value = raw

    if default is not None:
        if isinstance(default, bool):
            if raw.lower() in ("true", "yes", "1", "on"):
                value = True
            elif raw.lower() in ("false", "no", "0", "off"):
                value = False
            else:
                raise ValueError(
                    f"Invalid boolean value for `{key}`. "
                    "Use true/false, yes/no, 1/0, on/off"
                )
        elif isinstance(default, int):
            try:
                value = int(raw)
            except ValueError:
                raise ValueError(f"Invalid integer value for `{key}`.") from None
        elif isinstance(default, float):
            try:
                value = float(raw)
            except ValueError:
                raise ValueError(f"Invalid float value for `{key}`.") from None

    if key in CONFIG_ALLOWED_VALUES:
        allowed = CONFIG_ALLOWED_VALUES[key]
        match = next((v for v in allowed if v.lower() == str(value).lower()), None)
        if match is None:
            raise ValueError(
                f"Invalid value for `{key}`. Allowed: {', '.join(allowed)}"
            )
        return match  # canonical case

    return value

def build_categories_embed(mode: str = "edit") -> discord.Embed:
    """Embed listing all config categories."""
    if mode == "list":
        embed = discord.Embed(
            title="⚙️ Configuration Categories",
            description=(
                "Select a category to view all config keys and their current values."
            ),
            color=discord.Color.blurple(),
        )
    else:
        embed = discord.Embed(
            title="⚙️ Configuration Panel",
            description="Select a category to view and edit config values.",
            color=discord.Color.blue(),
        )

    for category, keys in CONFIG_CATEGORIES.items():
        embed.add_field(name=category, value=f"{len(keys)} settings", inline=True)

    embed.set_footer(text="Use the dropdown to select a category")
    return embed

# --------------------------------------------------------------------------
# Modal
# --------------------------------------------------------------------------

class ConfigModal(ui.Modal, title="Edit Config Value"):
    """Modal for editing a single config value."""

    def __init__(self, key: str, current_value: str, description: str = ""):
        # `description` is accepted for backwards compatibility but not used.
        super().__init__(title=f"Edit {key}"[:45])

        self.key = key

        self.value_input = ui.TextInput(
            label=key[:45],
            placeholder=(
                f"Current: {current_value}"[:100] if current_value else "Enter value..."
            ),
            default=current_value[:2000],
            required=False,
            max_length=2000,
        )
        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            new_value = coerce_value(self.key, self.value_input.value)
        except ValueError as exc:
            await interaction.response.send_message(f"❌ {exc}", ephemeral=True)
            return

        config = load_config()
        config[self.key] = new_value
        save_config(config)

        await interaction.response.send_message(
            f"✅ Config `{self.key}` updated to: `{display_value(self.key, new_value)}`",
            ephemeral=True,
        )

# --------------------------------------------------------------------------
# Paged key selection (shared base)
# --------------------------------------------------------------------------

class PageButton(ui.Button):
    """Prev/Next button for paged key views."""

    def __init__(self, delta: int, disabled: bool):
        super().__init__(
            label="◀ Prev" if delta < 0 else "Next ▶",
            style=discord.ButtonStyle.secondary,
            disabled=disabled,
        )
        self.delta = delta

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not isinstance(view, PagedKeyView):
            return
        view.page += self.delta
        await view.refresh(interaction)

class PagedKeyView(ui.View):
    """Owner-only view with a key dropdown that paginates past 25 keys.

    Provide either `author_id` (checked directly) or `bot` (checked with
    `bot.is_owner`, which also handles `owner_ids` and teams).
    """

    def __init__(
        self,
        keys: list[str],
        *,
        timeout: float,
        bot=None,
        author_id: int | None = None,
    ):
        super().__init__(timeout=timeout)
        self.keys = keys
        self.bot = bot
        self.author_id = author_id
        self.page = 0

    def make_select(self) -> ui.Select:
        raise NotImplementedError

    def _add_page_buttons(self):
        pages = page_count(len(self.keys))
        if pages > 1:
            self.add_item(PageButton(-1, self.page <= 0))
            self.add_item(PageButton(1, self.page >= pages - 1))

    def build_items(self):
        self.clear_items()
        self.add_item(self.make_select())
        self._add_page_buttons()

    async def refresh(self, interaction: discord.Interaction):
        self.build_items()
        await interaction.response.edit_message(view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.author_id is not None:
            allowed = interaction.user.id == self.author_id
        elif self.bot is not None:
            allowed = await self.bot.is_owner(interaction.user)
        else:
            allowed = False

        if not allowed:
            await interaction.response.send_message(
                "You cannot interact with this panel.", ephemeral=True
            )
        return allowed

def _key_options(keys: list[str]) -> list[discord.SelectOption]:
    return [
        discord.SelectOption(
            label=key[:100],
            description=CONFIG_DESCRIPTIONS.get(key, "No description")[:100],
            value=key,
        )
        for key in keys
    ]

def _paged_placeholder(base: str, page: int, total_keys: int) -> str:
    pages = page_count(total_keys)
    return f"{base} (page {page + 1}/{pages})" if pages > 1 else base

# --------------------------------------------------------------------------
# Edit flow
# --------------------------------------------------------------------------

class ConfigKeySelect(ui.Select):
    """Select menu for choosing a config key to edit."""

    def __init__(
        self,
        keys: list[str],
        page: int = 0,
        placeholder: str = "Select a config key...",
    ):
        page = max(0, min(page, page_count(len(keys)) - 1))
        super().__init__(
            placeholder=_paged_placeholder(placeholder, page, len(keys)),
            options=_key_options(page_slice(keys, page)),
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction):
        key = self.values[0]
        config = load_config()
        current_value = config.get(key, get_config_default(key))

        modal = ConfigModal(
            key,
            str(current_value) if current_value is not None else "",
            get_config_description(key),
        )
        await interaction.response.send_modal(modal)

class ConfigKeySelectView(PagedKeyView):
    """View with select menu for choosing config key to edit.

    `author_id` is now required so only the invoking user can open the modal.
    """

    def __init__(self, keys: list[str], author_id: int):
        super().__init__(keys, timeout=60, author_id=author_id)
        self.build_items()

    def make_select(self) -> ui.Select:
        return ConfigKeySelect(self.keys, self.page)

class ConfigPanelView(PagedKeyView):
    """Main config panel with category navigation and key editing."""

    def __init__(self, bot, mode: str = "edit"):
        super().__init__([], timeout=180, bot=bot)
        self.mode = mode
        self.current_category: str | None = None
        self.message: discord.Message | None = None
        self.build_items()

    @staticmethod
    async def create_initial_embed(mode: str = "edit") -> discord.Embed:
        """Create the initial embed for the config panel."""
        return build_categories_embed(mode)

    def create_category_embed(self) -> discord.Embed:
        """Create embed showing all categories."""
        return build_categories_embed(self.mode)

    def make_select(self) -> ui.Select:
        return ConfigKeySelect(self.keys, self.page)

    def build_items(self):
        self.clear_items()
        self.add_item(ConfigCategorySelect())
        if self.current_category is not None:
            self.add_item(self.make_select())
            self._add_page_buttons()

    def create_key_embed(self, category: str, page: int | None = None) -> discord.Embed:
        """Create embed showing the keys on the current page of a category."""
        all_keys = CONFIG_CATEGORIES.get(category, [])
        page = self.page if page is None else page
        pages = page_count(len(all_keys))
        config = load_config()

        embed = discord.Embed(
            title=f"⚙️ {category} Settings",
            description="Select a key to edit its value. Current values shown.",
            color=discord.Color.green(),
        )

        for key in page_slice(all_keys, page):
            current = config.get(key, get_config_default(key))
            desc = get_config_description(key)
            embed.add_field(
                name=key[:256],
                value=f"{desc}\nCurrent: `{display_value(key, current)}`"[:1024],
                inline=False,
            )

        footer = f"Category: {category} • Use dropdown to edit"
        if pages > 1:
            footer += f" • Page {page + 1}/{pages}"
        embed.set_footer(text=footer)
        return embed

    async def refresh(self, interaction: discord.Interaction):
        self.build_items()
        if self.current_category is None:
            embed = build_categories_embed(self.mode)
        else:
            embed = self.create_key_embed(self.current_category)
        await interaction.response.edit_message(embed=embed, view=self)

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
        view: ConfigPanelView = self.view  # type: ignore[assignment]
        view.current_category = self.values[0]
        view.keys = CONFIG_CATEGORIES[view.current_category]
        view.page = 0
        await view.refresh(interaction)

# --------------------------------------------------------------------------
# Reset / view flow
# --------------------------------------------------------------------------

class ConfigResetConfirmView(ui.View):
    """Confirmation view for resetting config to defaults."""

    def __init__(self, author_id: int, keys: list[str] | None = None):
        super().__init__(timeout=30)
        self.author_id = author_id
        self.keys = keys
        self.message: discord.Message | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "You cannot interact with this panel.", ephemeral=True
            )
            return False
        return True

    @ui.button(label="Confirm Reset", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: ui.Button):
        config = load_config()

        if self.keys:
            for key in self.keys:
                reset_key(config, key)
        else:
            # Reset all
            config = copy.deepcopy(DEFAULT_CONFIG)

        save_config(config)

        await interaction.response.edit_message(
            content=(
                "✅ Config reset to defaults"
                f"{' for selected keys' if self.keys else ''}."
            ),
            embed=None,
            view=None,
        )
        self.stop()

    @ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.edit_message(
            content="❌ Reset cancelled.", embed=None, view=None
        )
        self.stop()

class ConfigKeySelectForMode(ui.Select):
    """Select menu for choosing a config key for view/reset mode."""

    def __init__(self, mode: str, keys: list[str], page: int = 0):
        self.mode = mode

        page = max(0, min(page, page_count(len(keys)) - 1))
        base = (
            "Select a key to view..." if mode == "view" else "Select a key to reset..."
        )

        super().__init__(
            placeholder=_paged_placeholder(base, page, len(keys)),
            options=_key_options(page_slice(keys, page)),
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
                    f"{desc}\n\n**Current Value:** `{display_value(key, current)}`\n"
                    f"**Default Value:** `{display_value(key, default)}`"
                ),
                color=discord.Color.blurple(),
            )
            await interaction.response.edit_message(embed=embed, view=None)
            return

        # reset mode
        if key in config and config[key] != default:
            reset_key(config, key)
            save_config(config)
            content = f"✅ Reset `{key}` to default (`{display_value(key, default)}`)."
        else:
            content = (
                f"`{key}` is already at default value "
                f"(`{display_value(key, default)}`)."
            )

        await interaction.response.edit_message(content=content, embed=None, view=None)

class ConfigSelectView(PagedKeyView):
    """View with a dropdown to select a config key for viewing or resetting."""

    def __init__(self, bot, mode: str = "view"):
        all_keys = sorted(k for keys in CONFIG_CATEGORIES.values() for k in keys)
        super().__init__(all_keys, timeout=60, bot=bot)
        self.mode = mode
        self.build_items()

    def make_select(self) -> ui.Select:
        return ConfigKeySelectForMode(self.mode, self.keys, self.page)
