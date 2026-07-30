# cogs/ai/genai_memory.py: Python module.
from typing import Optional

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands

from utils.conversation import clear_conversation
from utils.memory import clear_user_facts

from .genai_common import MEMORY_FILE_PATH


class GenAIMemoryCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # -------------------------------------------------------------------
    # /clearmemory
    # -------------------------------------------------------------------
    @commands.hybrid_command(
        name="clearmemory",
        aliases=["smcl"],
        help="Clear conversation memory for this channel (Admin only). Optionally clear long-term facts.",
    )
    @commands.has_permissions(administrator=True)
    @app_commands.describe(
        clear_facts="Also clear long-term memory facts for all users in this channel (default: False)."
    )
    async def clear_memory(self, ctx: commands.Context, clear_facts: bool = False):
        guild = ctx.guild
        if guild is None:
            await ctx.send("Conversation commands are server-only.")
            return
        
        # Clear short-term conversation memory for all users in this channel
        await clear_conversation(guild.id, ctx.channel.id)
        
        if clear_facts:
            # Clear long-term facts for all users in this guild
            await clear_user_facts(guild.id)
            await ctx.send("Conversation memory and long-term facts cleared for this channel.")
        else:
            await ctx.send("Conversation memory cleared for this channel.")

    # -------------------------------------------------------------------
    # /memorylist (long-term SQLite)
    # -------------------------------------------------------------------
    @commands.hybrid_command(
        name="memorylist", aliases=["meml"], help="List long-term memory facts for a user."
    )
    @app_commands.describe(user="The user whose memory to list (defaults to you).")
    async def memory_list(self, ctx: commands.Context, user: Optional[discord.User] = None):
        guild = ctx.guild
        if guild is None:
            await ctx.send("Memory commands are server-only.")
            return

        target_user = user or ctx.author
        member = guild.get_member(ctx.author.id)
        is_admin = bool(
            member and (member.guild_permissions.administrator or member.guild_permissions.manage_guild)
        )

        if target_user.id != ctx.author.id and not is_admin:
            await ctx.send("❌ You can only view your own memory.", ephemeral=True)
            return

        async with aiosqlite.connect(MEMORY_FILE_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT content, importance FROM user_facts WHERE guild_id = ? AND user_id = ? ORDER BY importance DESC",
                (str(guild.id), str(target_user.id)),
            ) as cursor:
                rows = await cursor.fetchall()

        if not rows:
            await ctx.send(f"No long-term memory facts stored for {target_user.mention}.", ephemeral=True)
            return

        lines = [f"{i}. [{r['importance']:.2f}] {r['content']}" for i, r in enumerate(rows, 1)]
        embed = discord.Embed(
            title=f"Memory: {target_user.display_name}",
            description="\n".join(lines)[:4096],
            color=discord.Color.purple(),
        )
        await ctx.send(embed=embed, ephemeral=True)

    # -------------------------------------------------------------------
    # /memoryclear
    # -------------------------------------------------------------------
    @commands.hybrid_command(
        name="memoryclear",
        aliases=["memcl"],
        help="Clear long-term facts. Users can clear their own; Admins can clear anyone.",
    )
    @app_commands.describe(user="The user whose memory to clear (defaults to you).")
    async def memory_clear_user(self, ctx: commands.Context, user: Optional[discord.User] = None):
        guild = ctx.guild
        if guild is None:
            await ctx.send("Memory commands are server-only.")
            return

        target_user = user or ctx.author
        member = guild.get_member(ctx.author.id)
        is_admin = bool(
            member and (member.guild_permissions.administrator or member.guild_permissions.manage_guild)
        )

        if target_user.id != ctx.author.id and not is_admin:
            await ctx.send("❌ You can only clear your own memory.", ephemeral=True)
            return

        async with aiosqlite.connect(MEMORY_FILE_PATH) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM user_facts WHERE guild_id = ? AND user_id = ?",
                (str(guild.id), str(target_user.id)),
            ) as cursor:
                row = await cursor.fetchone()
                count = row[0] if row else 0

            if count > 0:
                await db.execute(
                    "DELETE FROM user_facts WHERE guild_id = ? AND user_id = ?",
                    (str(guild.id), str(target_user.id)),
                )
                await db.commit()
                msg = (
                    f"✅ I have forgotten {count} facts about you in this server."
                    if target_user.id == ctx.author.id
                    else f"✅ Cleared {count} facts for {target_user.mention}."
                )
                await ctx.send(msg, ephemeral=True)
                return
            else:
                await ctx.send(f"No facts found for {target_user.display_name}.", ephemeral=True)
                return

    # -------------------------------------------------------------------
    # /memorydelete
    # -------------------------------------------------------------------
    @commands.hybrid_command(
        name="memorydelete",
        aliases=["memdel"],
        help="Delete a specific memory fact by its list number.",
    )
    @app_commands.describe(
        index="The list number of the fact to delete.",
        user="The user whose memory to delete (defaults to you).",
    )
    async def memory_delete_index(
        self, ctx: commands.Context, index: int, user: Optional[discord.User] = None
    ):
        guild = ctx.guild
        if guild is None:
            return

        target_user = user or ctx.author
        member = guild.get_member(ctx.author.id)
        is_admin = bool(
            member and (member.guild_permissions.administrator or member.guild_permissions.manage_guild)
        )

        if target_user.id != ctx.author.id and not is_admin:
            await ctx.send("❌ You can only delete your own memory facts.", ephemeral=True)
            return

        async with aiosqlite.connect(MEMORY_FILE_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT message_id, content FROM user_facts WHERE guild_id = ? AND user_id = ? ORDER BY importance DESC",
                (str(guild.id), str(target_user.id)),
            ) as cursor:
                rows = list(await cursor.fetchall())

            if not rows or index < 1 or index > len(rows):
                await ctx.send(
                    f"Invalid number. Use `/memorylist` to see the {len(rows)} stored facts.", ephemeral=True
                )
                return

            target_fact = rows[index - 1]
            await db.execute("DELETE FROM user_facts WHERE message_id = ?", (target_fact["message_id"],))
            await db.commit()

        await ctx.send(
            f"✅ Deleted fact #{index} for {target_user.display_name}: *{target_fact['content'][:50]}...*",
            ephemeral=True,
        )

    # -------------------------------------------------------------------
    # /migrate
    # -------------------------------------------------------------------
    @commands.hybrid_command(name="migrate", help="Migrate JSON memory to SQLite (Admin only).")
    @commands.has_permissions(administrator=True)
    async def migrate_memory(self, ctx: commands.Context):
        await ctx.defer(ephemeral=True)
        from utils.memory import run_migration

        success, message = await run_migration()
        await ctx.send(f"{'✅' if success else '❌'} {message}", ephemeral=True)