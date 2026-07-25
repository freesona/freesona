import discord
from discord import app_commands
from discord.ext import commands

from utils.config import LAST_DEBUG, get_model_name, get_provider_name, load_config
from utils.persona import (
    LEGACY_DETECTED,
    PERSONA_DATA,
    assemble_persona,
    default_persona_json,
    load_profiles,
    open_persona_panel,
    save_persona_json,
    save_profiles,
)


class GenAIPersonaCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # -------------------------------------------------------------------
    # Set persona
    # -------------------------------------------------------------------
    @app_commands.command(name="setpersona", description="Open the persona editor (Owner only).")
    async def setpersona_cmd(self, interaction: discord.Interaction):
        await open_persona_panel(interaction)

    # -------------------------------------------------------------------
    # Persona lock / unlock
    # -------------------------------------------------------------------
    @commands.hybrid_command(
        name="personalock", aliases=["plock"], help="Lock the persona to prevent changes (Owner only)."
    )
    @commands.is_owner()
    async def persona_lock(self, ctx: commands.Context):
        import utils.persona as p

        p.PERSONA_LOCKED = True
        await ctx.send("Persona locked.", ephemeral=True if ctx.interaction else False)

    @commands.hybrid_command(
        name="personaunlock", aliases=["pulock"], help="Unlock the persona (Owner only)."
    )
    @commands.is_owner()
    async def persona_unlock(self, ctx: commands.Context):
        import utils.persona as p

        p.PERSONA_LOCKED = False
        await ctx.send("Persona unlocked.", ephemeral=True if ctx.interaction else False)

    # -------------------------------------------------------------------
    # Persona profiles
    # -------------------------------------------------------------------
    @commands.hybrid_command(
        name="personasave", aliases=["psave"], help="Save current persona as a named profile (Owner only)."
    )
    @commands.is_owner()
    async def persona_save(self, ctx: commands.Context, name: str):
        profiles = load_profiles()
        profiles[name.lower()] = PERSONA_DATA.copy()
        save_profiles(profiles)
        await ctx.send(f"Saved persona as `{name.lower()}`.", ephemeral=True if ctx.interaction else False)

    @commands.hybrid_command(
        name="personaload", aliases=["pload"], help="Load a saved persona profile (Owner only)."
    )
    @commands.is_owner()
    async def persona_load(self, ctx: commands.Context, name: str):
        import utils.persona as p

        if p.PERSONA_LOCKED:
            await ctx.send("Persona is locked.", ephemeral=True if ctx.interaction else False)
            return
        profiles = load_profiles()
        key = name.lower()
        if key not in profiles:
            await ctx.send(f"No profile named `{key}`. Use `/personalist` to see saved profiles.")
            return
        loaded = profiles[key]
        if isinstance(loaded, str):
            p.CURRENT_PERSONA = loaded
            p.PERSONA_DATA = default_persona_json()
        else:
            p.PERSONA_DATA = loaded
            p.CURRENT_PERSONA = assemble_persona(p.PERSONA_DATA)
        p.CURRENT_PERSONA_ID = key
        save_persona_json(p.PERSONA_DATA)
        await ctx.send(f"Loaded persona `{key}`.", ephemeral=True if ctx.interaction else False)

    @commands.hybrid_command(name="personalist", aliases=["plist"], help="List saved persona profiles.")
    @commands.is_owner()
    async def persona_list(self, ctx: commands.Context):
        profiles = load_profiles()
        if not profiles:
            await ctx.send("No saved profiles yet.")
            return
        names = "\n".join(f"- `{k}`" for k in profiles)
        await ctx.send(names, ephemeral=True if ctx.interaction else False)

    @commands.hybrid_command(
        name="personadelete", aliases=["pdel"], help="Delete a saved persona profile (Owner only)."
    )
    @commands.is_owner()
    async def persona_delete(self, ctx: commands.Context, name: str):
        profiles = load_profiles()
        key = name.lower()
        if key not in profiles:
            await ctx.send(f"No profile named `{key}`.")
            return
        del profiles[key]
        save_profiles(profiles)
        await ctx.send(f"Deleted profile `{key}`.", ephemeral=True if ctx.interaction else False)

    # -------------------------------------------------------------------
    # /debugpersona
    # -------------------------------------------------------------------
    @commands.hybrid_command(
        name="debugpersona", aliases=["pdeb"], help="Show active persona and last prompt (Owner only)."
    )
    @commands.is_owner()
    async def debug_persona(self, ctx: commands.Context):
        import utils.persona as p

        last = LAST_DEBUG.get(ctx.channel.id, "*(no prompt sent in this channel yet)*")
        locked = "Yes" if p.PERSONA_LOCKED else "No"
        legacy = "Yes — migrate via `/setpersona`" if LEGACY_DETECTED else "No"
        config = load_config()
        autonomy_status = "On" if config.get("autonomy", False) else "Off"
        autonomy_freq = config.get("autonomy_frequency", "default")
        response_mode = config.get("conversation_response_mode", "all")
        embed = discord.Embed(title="Persona Debug", color=discord.Color.yellow())
        embed.add_field(name="Locked", value=locked, inline=True)
        embed.add_field(name="Provider", value=get_provider_name(), inline=True)
        embed.add_field(name="Model", value=get_model_name(), inline=True)
        embed.add_field(name="Legacy Mode", value=legacy, inline=True)
        embed.add_field(name="Autonomy", value=f"{autonomy_status} ({autonomy_freq})", inline=True)
        embed.add_field(name="Chat Mode", value=response_mode, inline=True)
        embed.add_field(
            name="Assembled Persona", value=f"```{p.CURRENT_PERSONA[:900]}```", inline=False
        )
        embed.add_field(name="Last Prompt (this channel)", value=f"```{last[:900]}```", inline=False)
        await ctx.send(embed=embed, ephemeral=True if ctx.interaction else False)
