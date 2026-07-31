# cogs/system/logging.py: Logging system control commands (/logging)

import logging

import discord
from discord import app_commands
from discord.ext import commands

from utils.config import load_config, save_config
from utils.logging_utils import (
    LOG_SECTIONS,
    get_section_filter,
    refresh_section_filter,
    send_log_message,
    setup_logging,
)


def is_owner_check():
    """Check if the interaction user is the bot owner (for app_commands)."""

    async def predicate(interaction: discord.Interaction) -> bool:
        try:
            return await interaction.client.is_owner(interaction.user)  # type: ignore[reportAttributeAccessIssue]
        except (AttributeError, discord.DiscordException) as e:
            logging.getLogger(__name__).warning(
                "is_owner_check failed for user %s: %s", interaction.user, e
            )
            return False

    return app_commands.check(predicate)


# --- Logging command group ---
logging_group = app_commands.Group(
    name="logging",
    description="Logging system control (owner only)",
    default_permissions=discord.Permissions(administrator=True),
)


@logging_group.command(
    name="status",
    description="Show current logging configuration and enabled sections",
)
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
    enabled_sections = (
        sorted(section_filter._enabled_sections) if section_filter else []
    )
    embed.add_field(
        name="Active Sections (from filter)",
        value=(
            ", ".join(f"`{s}`" for s in enabled_sections)
            if enabled_sections
            else "None"
        ),
        inline=False,
    )

    await interaction.response.send_message(embed=embed, ephemeral=True)


@logging_group.command(name="enable", description="Enable a logging section")
@app_commands.describe(
    section="Section to enable (general, config, ai, memory, media, moderation, security, webhook)"
)
@app_commands.choices(
    section=[
        app_commands.Choice(name="General", value="general"),
        app_commands.Choice(name="Config", value="config"),
        app_commands.Choice(name="AI", value="ai"),
        app_commands.Choice(name="Memory", value="memory"),
        app_commands.Choice(name="Media", value="media"),
        app_commands.Choice(name="Moderation", value="moderation"),
        app_commands.Choice(name="Security", value="security"),
        app_commands.Choice(name="Webhook", value="webhook"),
    ]
)
@is_owner_check()
async def logging_enable(
    interaction: discord.Interaction, section: app_commands.Choice[str]
):

    key = LOG_SECTIONS.get(section.value)
    if not key:
        await interaction.response.send_message(
            f"Unknown section: `{section.value}`", ephemeral=True
        )
        return

    config = load_config()
    config[key] = True
    save_config(config)
    refresh_section_filter()

    await interaction.response.send_message(
        f"✅ Enabled logging section: **{section.name}** (`{key}`)",
        ephemeral=True,
    )


@logging_group.command(name="disable", description="Disable a logging section")
@app_commands.describe(
    section="Section to disable (general, config, ai, memory, media, moderation, security, webhook)"
)
@app_commands.choices(
    section=[
        app_commands.Choice(name="General", value="general"),
        app_commands.Choice(name="Config", value="config"),
        app_commands.Choice(name="AI", value="ai"),
        app_commands.Choice(name="Memory", value="memory"),
        app_commands.Choice(name="Media", value="media"),
        app_commands.Choice(name="Moderation", value="moderation"),
        app_commands.Choice(name="Security", value="security"),
        app_commands.Choice(name="Webhook", value="webhook"),
    ]
)
@is_owner_check()
async def logging_disable(
    interaction: discord.Interaction, section: app_commands.Choice[str]
):

    key = LOG_SECTIONS.get(section.value)
    if not key:
        await interaction.response.send_message(
            f"Unknown section: `{section.value}`", ephemeral=True
        )
        return

    config = load_config()
    config[key] = False
    save_config(config)
    refresh_section_filter()

    await interaction.response.send_message(
        f"❌ Disabled logging section: **{section.name}** (`{key}`)",
        ephemeral=True,
    )


@logging_group.command(name="toggle", description="Toggle a logging section on/off")
@app_commands.describe(
    section="Section to toggle (general, config, ai, memory, media, moderation, security, webhook)"
)
@app_commands.choices(
    section=[
        app_commands.Choice(name="General", value="general"),
        app_commands.Choice(name="Config", value="config"),
        app_commands.Choice(name="AI", value="ai"),
        app_commands.Choice(name="Memory", value="memory"),
        app_commands.Choice(name="Media", value="media"),
        app_commands.Choice(name="Moderation", value="moderation"),
        app_commands.Choice(name="Security", value="security"),
        app_commands.Choice(name="Webhook", value="webhook"),
    ]
)
@is_owner_check()
async def logging_toggle(
    interaction: discord.Interaction, section: app_commands.Choice[str]
):

    key = LOG_SECTIONS.get(section.value)
    if not key:
        await interaction.response.send_message(
            f"Unknown section: `{section.value}`", ephemeral=True
        )
        return

    config = load_config()
    new_value = not config.get(key, False)
    config[key] = new_value
    save_config(config)
    refresh_section_filter()

    status = "enabled" if new_value else "disabled"
    await interaction.response.send_message(
        f"🔄 Toggled logging section **{section.name}** (`{key}`) → **{status}**",
        ephemeral=True,
    )


@logging_group.command(
    name="setchannel", description="Set the Discord channel for log output"
)
@app_commands.describe(channel="Discord channel to send logs to")
@is_owner_check()
async def logging_setchannel(
    interaction: discord.Interaction, channel: discord.TextChannel
):

    config = load_config()
    config["log_channel_id"] = channel.id
    save_config(config)

    await interaction.response.send_message(
        f"✅ Log channel set to {channel.mention} (`{channel.id}`)",
        ephemeral=True,
    )


@logging_group.command(
    name="clearchannel", description="Clear the Discord log channel setting"
)
@is_owner_check()
async def logging_clearchannel(interaction: discord.Interaction):

    config = load_config()
    config["log_channel_id"] = 0
    save_config(config)

    await interaction.response.send_message("✅ Log channel cleared.", ephemeral=True)


@logging_group.command(name="setlevel", description="Set the log level")
@app_commands.describe(level="Log level (DEBUG, INFO, WARNING, ERROR)")
@app_commands.choices(
    level=[
        app_commands.Choice(name="DEBUG", value="DEBUG"),
        app_commands.Choice(name="INFO", value="INFO"),
        app_commands.Choice(name="WARNING", value="WARNING"),
        app_commands.Choice(name="ERROR", value="ERROR"),
    ]
)
@is_owner_check()
async def logging_setlevel(
    interaction: discord.Interaction, level: app_commands.Choice[str]
):

    config = load_config()
    config["log_level"] = level.value
    save_config(config)
    # Re-setup logging to apply new level
    setup_logging(interaction.client)  # type: ignore[arg-type]

    await interaction.response.send_message(
        f"✅ Log level set to **{level.value}**", ephemeral=True
    )


@logging_group.command(
    name="test",
    description="Send a test log message to the configured channel",
)
@app_commands.describe(message="Test message to send")
@is_owner_check()
async def logging_test(
    interaction: discord.Interaction, message: str = "Test log message"
):

    # type: ignore[arg-type]
    await send_log_message(interaction.client, message, "INFO")
    await interaction.response.send_message("✅ Test log message sent.", ephemeral=True)


class LoggingCog(commands.Cog):
    """Cog that registers the logging command group."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Add the logging command group to the bot's tree
        bot.tree.add_command(logging_group)


async def setup(bot: commands.Bot):
    await bot.add_cog(LoggingCog(bot))
