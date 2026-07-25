import discord
from discord import app_commands
from discord.ext import commands

from utils.config import load_config, save_config

from .genai_common import CHAT_RESPONSE_MODES


class GenAIChannelCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # -------------------------------------------------------------------
    # /setchannel + /clearchannel
    # -------------------------------------------------------------------
    @commands.hybrid_command(
        name="setchannel", aliases=["sc"], help="Set the AI conversation channel (Admin only)."
    )
    @app_commands.describe(channel="The channel to set for AI conversations.")
    @commands.has_permissions(administrator=True)
    async def set_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        config = load_config()
        config["chat_channel_id"] = channel.id
        save_config(config)
        await ctx.send(f"Conversation channel set to {channel.mention}.")

    @commands.hybrid_command(
        name="clearchannel", aliases=["cc"], help="Remove the AI conversation channel (Admin only)."
    )
    @commands.has_permissions(administrator=True)
    async def clear_channel(self, ctx: commands.Context):
        config = load_config()
        config.pop("chat_channel_id", None)
        save_config(config)
        await ctx.send("Conversation channel cleared.")

    # -------------------------------------------------------------------
    # /chatmode
    # -------------------------------------------------------------------
    @commands.hybrid_command(name="chatmode", help="Set conversation channel response mode (Admin only).")
    @app_commands.describe(mode="Mode can be `all`, `mentions`, or `smart`.")
    @commands.has_permissions(administrator=True)
    async def chat_mode(self, ctx: commands.Context, mode: str):
        mode = mode.lower().strip()
        if mode not in CHAT_RESPONSE_MODES:
            await ctx.send(
                "Mode must be `all`, `mentions`, or `smart`.", ephemeral=True if ctx.interaction else False
            )
            return
        config = load_config()
        config["conversation_response_mode"] = mode
        save_config(config)
        descriptions = {
            "all": "respond to every message in the conversation channel",
            "mentions": "respond only to bot mentions or replies",
            "smart": "respond to bot mentions, replies, or attachments",
        }
        await ctx.send(
            f"Conversation response mode set to `{mode}`: {descriptions[mode]}.",
            ephemeral=True if ctx.interaction else False,
        )
