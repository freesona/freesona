# cogs/ai/chroma.py: ChromaDB Cog for Discord bot to manage a local knowledge base.
import discord
from discord.ext import commands

from utils.chroma import add_knowledge, delete_knowledge, list_knowledge, query_knowledge


class ChromaCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="kbsearch", help="Search the local knowledge base.")
    async def kbsearch(self, ctx, *, query: str):
        await ctx.defer(ephemeral=True)
        matches = query_knowledge(query, limit=5)
        if not matches:
            await ctx.send("No knowledge base matches found.", ephemeral=True)
            return
        lines = [f"- {item}" for item in matches]
        await ctx.send("\n".join(lines[:10]), ephemeral=True)

    @commands.hybrid_command(name="kbadd", help="Add a note to the local knowledge base.")
    @commands.has_permissions(administrator=True)
    async def kbadd(self, ctx, title: str, *, content: str):
        await ctx.defer(ephemeral=True)
        if not content.strip():
            await ctx.send("Knowledge base content cannot be empty.", ephemeral=True)
            return

        doc_id = add_knowledge(content.strip(), source="discord", title=title.strip())
        if not doc_id:
            await ctx.send("ChromaDB is not available or could not initialize the collection.", ephemeral=True)
            return

        await ctx.send(f"Added knowledge entry with ID `{doc_id}`.", ephemeral=True)

    @commands.hybrid_command(name="kblist", help="List knowledge base entries.")
    @commands.has_permissions(administrator=True)
    async def kblist(self, ctx):
        await ctx.defer(ephemeral=True)
        entries = list_knowledge()
        if not entries:
            await ctx.send("No knowledge base entries found.", ephemeral=True)
            return

        lines = []
        for index, item in enumerate(entries, start=1):
            title = item.get("metadata", {}).get("title") or "Untitled"
            snippet = item.get("document", "").strip()
            if len(snippet) > 120:
                snippet = snippet[:117] + "..."
            lines.append(f"{index}. {title} — {item['id']} — {snippet}")

        await ctx.send("\n".join(lines[:20]), ephemeral=True)

    @commands.hybrid_command(name="kbdelete", help="Delete a knowledge base entry by id.")
    @commands.has_permissions(administrator=True)
    async def kbdelete(self, ctx, entry_id: str):
        await ctx.defer(ephemeral=True)
        if delete_knowledge(entry_id):
            await ctx.send(f"Deleted knowledge entry `{entry_id}`.", ephemeral=True)
            return

        await ctx.send("Could not delete that knowledge entry.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(ChromaCog(bot))
