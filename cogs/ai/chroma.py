# cogs/ai/chroma.py: ChromaDB Cog for Discord bot to manage a local knowledge base.
import asyncio
import discord
from discord import ui, app_commands
from discord.ext import commands

from utils.chroma import (
    add_knowledge,
    delete_knowledge,
    extract_text_from_bytes,
    get_knowledge_by_persona,
    list_knowledge,
    query_knowledge,
    VALID_CANON_LEVELS,
)


VALID_SOURCE_TYPES = {"anime", "novel", "manga", "game", "guidebook", "interview", "website", "other"}
VALID_ENTRY_TYPES = {"dialogue", "narration", "event", "relationship", "description"}


class MetadataModal(ui.Modal, title="Knowledge Entry Metadata"):
    persona = ui.TextInput(
        label="Persona ID",
        style=discord.TextStyle.short,
        required=True,
        max_length=100,
        placeholder="e.g., chisato_nishikigi",
    )
    source = ui.TextInput(
        label="Source",
        style=discord.TextStyle.short,
        required=True,
        max_length=200,
        placeholder="e.g., Episode 06",
    )
    source_type = ui.TextInput(
        label="Source Type",
        style=discord.TextStyle.short,
        required=True,
        max_length=20,
        placeholder="anime, novel, manga, game, guidebook, interview, website, other",
    )
    entry_type = ui.TextInput(
        label="Entry Type",
        style=discord.TextStyle.short,
        required=True,
        max_length=20,
        placeholder="dialogue, narration, event, relationship, description",
    )
    topics = ui.TextInput(
        label="Topics (comma-separated)",
        style=discord.TextStyle.short,
        required=True,
        max_length=200,
        placeholder="e.g., friendship, optimism, coffee",
    )
    # Optional fields
    scene = ui.TextInput(
        label="Scene (optional)",
        style=discord.TextStyle.short,
        required=False,
        max_length=200,
        placeholder="e.g., Aquarium visit",
    )
    speaker = ui.TextInput(
        label="Speaker (optional)",
        style=discord.TextStyle.short,
        required=False,
        max_length=100,
        placeholder="e.g., Chisato",
    )
    episode = ui.TextInput(
        label="Episode (optional)",
        style=discord.TextStyle.short,
        required=False,
        max_length=50,
        placeholder="e.g., 06",
    )
    chapter = ui.TextInput(
        label="Chapter (optional)",
        style=discord.TextStyle.short,
        required=False,
        max_length=50,
        placeholder="e.g., Chapter 12",
    )
    timestamp = ui.TextInput(
        label="Timestamp (optional)",
        style=discord.TextStyle.short,
        required=False,
        max_length=50,
        placeholder="e.g., 2023-01-15 or S01E06 12:34",
    )
    canon_level = ui.TextInput(
        label="Canon Level (optional)",
        style=discord.TextStyle.short,
        required=False,
        max_length=20,
        placeholder="canon, semi-canon, non-canon, headcanon, alternate",
    )
    tags = ui.TextInput(
        label="Tags (comma-separated, optional)",
        style=discord.TextStyle.short,
        required=False,
        max_length=200,
        placeholder="e.g., canon, emotional, key_moment",
    )

    def __init__(self, document: str, title: str | None, attachment_filename: str | None):
        super().__init__()
        self.document = document
        self.document_title = title or ""
        self.attachment_filename = attachment_filename

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        # Validate source_type
        source_type = self.source_type.value.strip().lower()
        if source_type not in VALID_SOURCE_TYPES:
            await interaction.followup.send(
                f"Invalid source_type. Must be one of: {', '.join(sorted(VALID_SOURCE_TYPES))}",
                ephemeral=True,
            )
            return

        # Validate entry_type
        entry_type = self.entry_type.value.strip().lower()
        if entry_type not in VALID_ENTRY_TYPES:
            await interaction.followup.send(
                f"Invalid entry_type. Must be one of: {', '.join(sorted(VALID_ENTRY_TYPES))}",
                ephemeral=True,
            )
            return

        # Validate canon_level if provided
        canon_level = self.canon_level.value.strip().lower() if self.canon_level.value.strip() else None
        if canon_level and canon_level not in VALID_CANON_LEVELS:
            await interaction.followup.send(
                f"Invalid canon_level. Must be one of: {', '.join(sorted(VALID_CANON_LEVELS))}",
                ephemeral=True,
            )
            return

        # Parse topics
        topics = [t.strip() for t in self.topics.value.split(",") if t.strip()]
        if not topics:
            await interaction.followup.send("At least one topic is required.", ephemeral=True)
            return

        # Build metadata
        metadata = {
            "persona": self.persona.value.strip(),
            "source": self.source.value.strip(),
            "source_type": source_type,
            "entry_type": entry_type,
            "topics": topics,
        }

        # Add optional fields if provided
        if self.scene.value.strip():
            metadata["scene"] = self.scene.value.strip()
        if self.speaker.value.strip():
            metadata["speaker"] = self.speaker.value.strip()
        if self.episode.value.strip():
            metadata["episode"] = self.episode.value.strip()
        if self.chapter.value.strip():
            metadata["chapter"] = self.chapter.value.strip()
        if self.timestamp.value.strip():
            metadata["timestamp"] = self.timestamp.value.strip()
        if canon_level:
            metadata["canon_level"] = canon_level
        if self.tags.value.strip():
            metadata["tags"] = [t.strip() for t in self.tags.value.split(",") if t.strip()]

        # Add to knowledge base
        doc_id = await asyncio.to_thread(
            add_knowledge,
            self.document,
            source="discord",
            title=self.document_title.strip() if self.document_title else None,
            metadata=metadata,
        )

        if not doc_id:
            await interaction.followup.send("ChromaDB is not available or could not initialize the collection.", ephemeral=True)
            return

        await interaction.followup.send(f"Added knowledge entry with ID `{doc_id}` for persona `{metadata['persona']}`.", ephemeral=True)


class ChromaCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="kbsearch", help="Search the local knowledge base.")
    @app_commands.describe(query="Search query", persona="Optional persona to filter by", limit="Maximum results (default 5)")
    @commands.has_permissions(administrator=True)
    async def kbsearch(
        self,
        ctx: commands.Context,
        *,
        query: str,
        persona: str | None = None,
        limit: int = 5,
    ):
        await ctx.defer(ephemeral=True)

        # Run ChromaDB query off-thread to prevent event loop blocking
        matches = await asyncio.to_thread(query_knowledge, query, limit=limit, persona=persona)
        if not matches:
            await ctx.send("No knowledge base matches found.", ephemeral=True)
            return

        lines = []
        for item in matches:
            meta = item.get("metadata", {})
            persona_name = meta.get("persona", "unknown")
            source = meta.get("source", "unknown")
            entry_type = meta.get("entry_type", "unknown")
            snippet = item.get("document", "").strip().replace("\n", " ")
            if len(snippet) > 150:
                snippet = snippet[:147] + "..."
            lines.append(f"- **{persona_name}** ({entry_type}, {source}): {snippet}")

        response_text = "\n".join(lines)

        # Ensure text fits within Discord's 2000-character limit
        if len(response_text) > 1950:
            response_text = response_text[:1947] + "..."

        await ctx.send(response_text, ephemeral=True)

    @commands.hybrid_command(
        name="kbadd",
        help="Add a note or attached PDF, EPUB, TXT, or JSON file to the local knowledge base with metadata.",
    )
    @app_commands.describe(
        title="Title for the knowledge entry",
        content="Text content (optional if attaching a file)",
        attachment="File attachment (PDF, EPUB, TXT, JSON)",
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

        # Show modal to collect metadata
        modal = MetadataModal(document, title, attachment.filename if attachment else None)
        await ctx.send("Please provide metadata for this knowledge entry:", ephemeral=True)
        interaction = ctx.interaction
        if interaction is not None:
            await interaction.response.send_modal(modal)
        else:
            # For prefix commands, we might need a different way to send modal or just fail
            await ctx.send("Modals can only be sent in response to slash commands.", ephemeral=True)

    @commands.hybrid_command(name="kblist", help="List the newest knowledge base entries.")
    @app_commands.describe(persona="Optional persona to filter by", limit="Maximum entries to show (default 15)")
    @commands.has_permissions(administrator=True)
    async def kblist(self, ctx: commands.Context, persona: str | None = None, limit: int = 15):
        await ctx.defer(ephemeral=True)

        if persona:
            # Run disk lookup off-thread
            entries = await asyncio.to_thread(get_knowledge_by_persona, persona, limit=limit)
        else:
            entries = await asyncio.to_thread(list_knowledge, limit=limit)

        if not entries:
            await ctx.send("No knowledge base entries found.", ephemeral=True)
            return

        lines = []
        for index, item in enumerate(entries, start=1):
            meta = item.get("metadata", {})
            # Fallback chain for a clean title display
            title = meta.get("title") or meta.get("filename") or item["id"]
            persona_name = meta.get("persona", "unknown")
            source = meta.get("source", "unknown")
            entry_type = meta.get("entry_type", "unknown")

            # If the title is a long file path, pull just the filename
            if "/" in title or "\\" in title:
                title = title.replace("\\", "/").split("/")[-1]

            snippet = item.get("document", "").strip().replace("\n", " ")
            if len(snippet) > 80:
                snippet = snippet[:77] + "..."
            lines.append(f"**{index}.** [{persona_name}] {title} (`{item['id']}`)\n└ {entry_type} · {source} · *{snippet}*")

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

    @commands.hybrid_command(name="kbpersona", help="List all knowledge entries for a specific persona.")
    @app_commands.describe(persona="Persona ID to list entries for", limit="Maximum entries to show (default 50)")
    @commands.has_permissions(administrator=True)
    async def kbpersona(self, ctx: commands.Context, persona: str, limit: int = 50):
        await ctx.defer(ephemeral=True)

        entries = await asyncio.to_thread(get_knowledge_by_persona, persona, limit=limit)
        if not entries:
            await ctx.send(f"No knowledge base entries found for persona `{persona}`.", ephemeral=True)
            return

        lines = []
        for index, item in enumerate(entries, start=1):
            meta = item.get("metadata", {})
            source = meta.get("source", "unknown")
            entry_type = meta.get("entry_type", "unknown")
            scene = meta.get("scene", "")
            scene_str = f" · {scene}" if scene else ""
            snippet = item.get("document", "").strip().replace("\n", " ")
            if len(snippet) > 100:
                snippet = snippet[:97] + "..."
            lines.append(f"**{index}.** `{item['id']}` [{entry_type}] {source}{scene_str}\n└ *{snippet}*")

        full_message = "\n".join(lines)

        if len(full_message) > 1950:
            full_message = full_message[:1947] + "..."

        await ctx.send(full_message, ephemeral=True)


async def setup(bot):
    await bot.add_cog(ChromaCog(bot))