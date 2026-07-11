# cogs/ai/chroma.py: ChromaDB Cog for Discord bot to manage a local knowledge base.
import asyncio
import discord
from discord.ext import commands

from utils.chroma import add_knowledge, delete_knowledge, extract_text_from_bytes, list_knowledge, query_knowledge


class ChromaCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="kbsearch", help="Search the local knowledge base.")
    @commands.has_permissions(administrator=True)
    async def kbsearch(self, ctx: commands.Context, *, query: str):
        await ctx.defer(ephemeral=True)

        # Run ChromaDB query off-thread to prevent event loop blocking
        matches = await asyncio.to_thread(query_knowledge, query, limit=5)
        if not matches:
            await ctx.send("No knowledge base matches found.", ephemeral=True)
            return

        lines = [f"- {item[:200]}..." if len(item) > 200 else f"- {item}" for item in matches]
        response_text = "\n".join(lines)

        # Ensure text fits within Discord's 2000 character limit
        if len(response_text) > 1950:
            response_text = response_text[:1947] + "..."

        await ctx.send(response_text, ephemeral=True)

    @commands.hybrid_command(
        name="kbadd", 
        help="Add a note or attached PDF, EPUB, TXT, or JSON file to the local knowledge base."
    )
    @commands.has_permissions(administrator=True)
    async def kbadd(
        self,
        ctx: commands.Context,
        title: str,
        content: str | None = None,
        attachment: discord.Attachment | None = None,
    ):
        await ctx.defer(ephemeral=True)

        attachment = attachment or (
            ctx.message.attachments[0] 
            if getattr(ctx, "message", None) and ctx.message.attachments 
            else None
        )

        text_parts: list[str] = []
        if content and content.strip():
            text_parts.append(content.strip())

        if attachment is not None:
            try:
                raw_bytes = await attachment.read()
            except Exception as exc:
                await ctx.send(f"Failed to read attachment: {exc}", ephemeral=True)
                return

            # Extract text off-thread for CPU-heavy parsing (PDFs, EPUBs, JSON)
            extracted = await asyncio.to_thread(
                extract_text_from_bytes, attachment.filename or "attachment.bin", raw_bytes
            )

            if not extracted.strip():
                await ctx.send(
                    "Could not extract readable text from that file. Supported input includes PDF, EPUB, TXT, and JSON files.",
                    ephemeral=True,
                )
                return
            text_parts.append(extracted)

        if not text_parts:
            await ctx.send("Provide text or attach a supported file (PDF, EPUB, TXT, JSON).", ephemeral=True)
            return

        document = "\n\n".join(text_parts)

        # Run embedding generation off-thread
        doc_id = await asyncio.to_thread(
            add_knowledge,
            document,
            source="discord",
            title=title.strip(),
            metadata={"filename": getattr(attachment, "filename", None)} if attachment is not None else None,
        )

        if not doc_id:
            await ctx.send("ChromaDB is not available or could not initialize the collection.", ephemeral=True)
            return

        await ctx.send(f"Added knowledge entry with ID `{doc_id}`.", ephemeral=True)

    @commands.hybrid_command(name="kblist", help="List the newest knowledge base entries.")
    @commands.has_permissions(administrator=True)
    async def kblist(self, ctx: commands.Context):
        await ctx.defer(ephemeral=True)

        # Run disk lookup off-thread
        entries = await asyncio.to_thread(list_knowledge, limit=15)
        if not entries:
            await ctx.send("No knowledge base entries found.", ephemeral=True)
            return

        lines = []
        for index, item in enumerate(entries, start=1):
            meta = item.get("metadata", {})
            # Fallback chain for a clean title display
            title = meta.get("title") or meta.get("filename") or item["id"]

            # If the title is a long file path, pull just the filename
            if "/" in title or "\\" in title:
                title = title.replace("\\", "/").split("/")[-1]

            snippet = item.get("document", "").strip().replace("\n", " ")
            if len(snippet) > 80:
                snippet = snippet[:77] + "..."
            lines.append(f"**{index}.** {title} (`{item['id']}`)\n└ *Snippet:* {snippet}")

        full_message = "\n".join(lines)

        # Safe pagination / length check for Discord output limit
        if len(full_message) > 1950:
            full_message = full_message[:1947] + "..."

        await ctx.send(full_message, ephemeral=True)

    @commands.hybrid_command(name="kbdelete", help="Delete a knowledge base entry by id.")
    @commands.has_permissions(administrator=True)
    async def kbdelete(self, ctx: commands.Context, entry_id: str):
        await ctx.defer(ephemeral=True)

        success = await asyncio.to_thread(delete_knowledge, entry_id)
        if success:
            await ctx.send(f"Deleted knowledge entry `{entry_id}`.", ephemeral=True)
            return

        await ctx.send("Could not delete that knowledge entry.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(ChromaCog(bot))