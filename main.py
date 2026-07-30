# main.py: Main code that loads the cogs and makes the bot run. Also contains the prefix command and the on_ready event that sends a message to the specified channel when the bot starts up. The bot also starts a FastAPI server in the background for future webhooks and health checks.

import discord
from discord.ext import commands
from discord import app_commands, abc
import os
import logging
import asyncio
import uvicorn
from pathlib import Path
from fastapi_server import app
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().with_name(".env"))

from utils.config import load_config, save_config
from utils.modules import CORE_EXTENSIONS, OPTIONAL_MODULES, load_enabled_modules
from utils.conversation import start_cleanup_task, stop_cleanup_task
from utils.character_memory import start_extraction_task, stop_extraction_task
from utils.logging_utils import setup_logging

# Initial basic logging until setup_logging is called
logging.basicConfig(level=logging.INFO, format='%(asctime)s:%(levelname)s:%(name)s: %(message)s')
logger = logging.getLogger(__name__)

# --- Configuration & Persistence Setup ---
bot_token = os.getenv("BOT_TOKEN")
channel_id_str = os.getenv("CHANNEL_ID")

if not bot_token or not channel_id_str:
    raise ValueError("Missing BOT_TOKEN or CHANNEL_ID in environment variables")

try:
    CHANNEL_ID = int(channel_id_str)
except ValueError:
    raise ValueError("CHANNEL_ID must be an integer")

def get_prefix(bot, message):
    """Reads the prefix from the in-memory bot config."""
    _ = message
    return getattr(bot, "config", {}).get("prefix", "~")

# --- Bot Class Definition ---
class Freesona(commands.Bot):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.config = load_config()  # Cache config in memory to eliminate disk read on prefix checks
        self._legacy_notice_sent = False  # guard: only DM once per session
        self._startup_sent = False        # guard: only send startup message once per session

    @property
    def startup_sent(self) -> bool:
        return self._startup_sent

    @startup_sent.setter
    def startup_sent(self, value: bool) -> None:
        self._startup_sent = value

    async def setup_hook(self):
        # Start background cleanup tasks
        await start_cleanup_task()
        await start_extraction_task()

        # Setup logging after bot is initialized (for Discord channel logging)
        setup_logging(self)

        enabled_modules = load_enabled_modules(self.config)
        extensions = CORE_EXTENSIONS + [
            ext for name, ext in OPTIONAL_MODULES.items()
            if enabled_modules.get(name, True)
        ]

        for ext in extensions:
            try:
                await self.load_extension(ext)
            except Exception:
                logger.exception(f"Failed to load extension {ext}")  # Capture full traceback

        await self.tree.sync()
        logger.info(f"Synced slash commands for {self.user}")

    async def close(self):
        # Stop background cleanup tasks before closing
        await stop_cleanup_task()
        await stop_extraction_task()
        await super().close()

    async def notify_owner_legacy(self, bot_name: str):
        """DM the bot owner about legacy persona.txt — called from genai cog."""
        if self._legacy_notice_sent:
            return
        self._legacy_notice_sent = True
        try:
            info = await self.application_info()
            owner = info.owner
            await owner.send(
                f"⚠️ **{bot_name} detected a legacy `persona.txt` file.**\n\n"
                f"The persona system now uses a structured `persona.json` format. "
                f"Your existing persona is still active, but to use the new structured editor, "
                f"you'll need to migrate your content into the new fields.\n\n"
                f"Use `/setpersona core` and `/setpersona style` to set up the new format. "
                f"Once saved, `persona.json` will take over and `persona.txt` can be removed.\n\n"
                f"You can also run `/debugpersona` to confirm your current state."
            )
        except Exception as e:
            logger.warning(f"Could not DM owner for legacy persona notice: {e}")

# Initialize Bot
intents = discord.Intents.default()
setattr(intents, "message_content", True)
setattr(intents, "members", True)
setattr(intents, "dm_messages", True)
setattr(intents, "guilds", True)

bot = Freesona(command_prefix=get_prefix, intents=intents)
bot.remove_command('help')

# --- Commands & Events ---
@bot.hybrid_command(name="prefix", description="Changes the bot prefix and saves it to config.json")
@commands.has_permissions(administrator=True)
async def change_prefix(ctx, new_prefix: str):
    clean_prefix = new_prefix.strip()

    if not clean_prefix:
        await ctx.send("Prefix cannot be empty.")
        return
    if len(clean_prefix) > 5:
        await ctx.send("Prefix cannot be longer than 5 characters.")
        return

    try:
        bot.config["prefix"] = clean_prefix
        save_config(bot.config)
        await ctx.send(f"Prefix updated to: `{clean_prefix}`")
    except Exception as e:
        logger.error(f"Failed to save prefix: {e}")
        await ctx.send("Error saving prefix to persistent storage.")

@bot.event
async def on_ready():
    logger.info(f'Logged in as {bot.user}')

    if not bot.startup_sent:
        bot.startup_sent = True
        channel = bot.get_channel(CHANNEL_ID)
        if isinstance(channel, abc.Messageable):
            bot_name = os.getenv("BOT_NAME", "Bot")
            try:
                current_p = get_prefix(bot, None)
                await channel.send(
                    f"Heya! {bot_name} here! Current prefix is `{current_p}`. "
                    "For fresh info, use `search <query>`."
                )
            except Exception as e:
                logger.warning(f"Failed to send startup message: {e}")

    # Trigger legacy persona DM if needed — deferred here so bot is fully ready
    try:
        from cogs.ai.genai import LEGACY_DETECTED, BOT_NAME as GENAI_BOT_NAME
        if LEGACY_DETECTED:
            await bot.notify_owner_legacy(GENAI_BOT_NAME)
    except Exception as e:
        logger.warning(f"Legacy check failed: {e}")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        cmd = ctx.command
        prefix = ctx.prefix
        embed = discord.Embed(
            title=f"Help: `{prefix}{cmd.name}`" + (f" (alias: `{prefix}{ctx.invoked_with}`)" if ctx.invoked_with != cmd.name else ""),
            description=cmd.help or "No description provided.",
            color=discord.Color.green()
        )
        if cmd.usage:
            embed.add_field(name="Usage", value=f"`{prefix}{cmd.name} {cmd.usage}`", inline=False)
        if cmd.aliases:
            embed.add_field(name="Aliases", value=", ".join(f"`{prefix}{a}`" for a in cmd.aliases), inline=False)
        await ctx.send(embed=embed)
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("You don't have permission to use this command.")
    elif isinstance(error, commands.BotMissingPermissions):
        await ctx.send("I don't have permission to do that.")
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"Cooldown. Try again in {error.retry_after:.1f}s.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f"Invalid argument: {error}")

@bot.event
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    """Handle slash command errors safely without type or attribute exceptions."""
    raw_error = error.original if isinstance(error, app_commands.CommandInvokeError) else error

    if isinstance(raw_error, app_commands.MissingPermissions):
        await send_app_error(interaction, "You don't have permission to use this command.")
    elif isinstance(raw_error, app_commands.BotMissingPermissions):
        await send_app_error(interaction, "I don't have permission to do that.")
    elif isinstance(raw_error, app_commands.CommandOnCooldown):
        await send_app_error(interaction, f"Cooldown. Try again in {raw_error.retry_after:.1f}s.")
    elif isinstance(raw_error, (commands.BadArgument, app_commands.TransformerError)):
        await send_app_error(interaction, f"Invalid argument: {raw_error}")
    else:
        logger.error(f"Unhandled slash command error: {type(raw_error).__name__}: {raw_error}")
        await send_app_error(interaction, "An unexpected error occurred. Please try again.")

async def send_app_error(interaction: discord.Interaction, message: str):
    """Safely send an error response to a slash command interaction."""
    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    except Exception as e:
        logger.warning(f"Failed to send app error response: {e}")

# --- Background Tasks & Execution ---
HTTP_PORT = int(os.getenv("HTTP_PORT", "10000"))

async def start_http():
    config = uvicorn.Config(app, host="0.0.0.0", port=HTTP_PORT, log_level="warning")
    server = uvicorn.Server(config)
    await server.serve()

async def start_bot():
    await bot.start(str(bot_token))

async def main():
    await asyncio.gather(
        start_http(),
        start_bot()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped.")