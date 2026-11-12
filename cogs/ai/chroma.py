#!/usr/bin/env python3
"""Knowledge-base commands backed by the local ChromaDB store.

This cog lets administrators search, add, list, and remove persona-scoped
knowledge entries. It accepts plain text or supported attachments, extracts
readable content from files, and saves the result to the bot's shared
knowledge-base service.
"""

import asyncio
import logging
from typing import Any

import discord
from discord import app_commands, ui
from discord.ext import commands

from utils.chroma import (
    VALID_CANON_LEVELS,
    VALID_ENTRY_TYPES,
    VALID_SOURCE_TYPES,
    ChromaBackendError,
    extract_epub_book_info,
    extract_text_from_bytes,
    ingest_source,
    query_knowledge,
)
from utils.config import get_default_persona, get_knowledge_base_database
from utils.knowledge_base import KnowledgeBaseService

log = logging.getLogger(__name__)


class MetadataModal(ui.Modal, title="Knowledge Entry Metadata"):
    """Collect the five required Knowledge Base fields via a Discord modal.

    Discord modals support at most five components.  Optional metadata
    fields (scene, speaker, episode, chapter, timestamp, canon_level,
    tags) are accepted as slash-command parameters on ``/kbadd`` and
    forwarded through ``extra_metadata``.
    """

    persona = ui.TextInput(
        label="Persona ID",
        style=discord.TextStyle.short,
        required=True,
        max_length=100,
        placeholder="e.g., character_name",
    )
    source = ui.TextInput(
        label="Source",
        style=discord.TextStyle.short,
        required=True,
        max_length=200,
        placeholder="e.g., Episode 01",
    )
    source_type = ui.TextInput(
        label="Source Type",
        style=discord.TextStyle.short,
        required=True,
        max_length=20,
        placeholder=("anime, novel, manga, game, guidebook, interview, website, other"),
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
        placeholder="e.g., friendship, loyalty, humor",
    )

    def __init__(
        self,
        document: str,
        title: str | None,
        attachment_filename: str | None,
        *,
        default_persona: str = "",
        default_source: str | None = None,
        default_source_type: str = "novel",
        default_entry_type: str = "narration",
        default_topics: str = "novel, story, canon",
        extra_metadata: dict[str, Any] | None = None,
    ):
        super().__init__()
        self.document = document
        self.document_title = title or ""
        self.attachment_filename = attachment_filename
        self.extra_metadata: dict[str, Any] = extra_metadata or {}

        # Pre-fill defaults so the user doesn't have to retype them
        self.persona.default = default_persona
        self.source.default = default_source or self.document_title or "Volume 01"
        self.source_type.default = default_source_type
        self.entry_type.default = default_entry_type
        self.topics.default = default_topics

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        # Validate source_type
        source_type = self.source_type.value.strip().lower()
        if source_type not in VALID_SOURCE_TYPES:
            await interaction.followup.send(
                f"Invalid source_type. Must be one of: "
                f"{', '.join(sorted(VALID_SOURCE_TYPES))}",
                ephemeral=True,
            )
            return
        # Validate entry_type
        entry_type = self.entry_type.value.strip().lower()
        if entry_type not in VALID_ENTRY_TYPES:
            await interaction.followup.send(
                f"Invalid entry_type. Must be one of: "
                f"{', '.join(sorted(VALID_ENTRY_TYPES))}",
                ephemeral=True,
            )
            return
        # Validate canon_level from extra_metadata if provided
        canon_level = self.extra_metadata.get("canon_level")
        if canon_level and canon_level not in VALID_CANON_LEVELS:
            await interaction.followup.send(
                f"Invalid canon_level. Must be one of: "
                f"{', '.join(sorted(VALID_CANON_LEVELS))}",
                ephemeral=True,
            )
            return
        # Parse topics
        topics = [t.strip() for t in self.topics.value.split(",") if t.strip()]
        if not topics:
            await interaction.followup.send(
                "At least one topic is required.", ephemeral=True
            )
            return
        # Build metadata from the modal's required fields
        metadata: dict[str, Any] = {
            "persona": self.persona.value.strip(),
            "source": self.source.value.strip(),
            "source_type": source_type,
            "entry_type": entry_type,
            "topics": topics,
        }
        # Merge optional fields supplied via slash-command parameters
        metadata.update(self.extra_metadata)
        service = KnowledgeBaseService(get_knowledge_base_database())
        try:
            await service.initialize()
            chunks = (
                ingest_source(self.document, metadata)
                if len(self.document) > 1500
                else []
            )
            if chunks:
                total = len(chunks)
                indexed_count = 0
                title = self.document_title.strip() if self.document_title else ""
                for i, chunk_item in enumerate(chunks, start=1):
                    chunk_meta = chunk_item["metadata"].copy()
                    chapter_name = chunk_meta.get("chapter")
                    if title:
                        if chapter_name:
                            chunk_meta["title"] = (
                                f"{title} - {chapter_name} (Part {i}/{total})"
                            )
                        else:
                            chunk_meta["title"] = f"{title} (Part {i}/{total})"
                    entry = await service.ingest(
                        {
                            **chunk_meta,
                            "content": chunk_item["document"],
                        }
                    )
                    if await service.indexed_id(entry.id):
                        indexed_count += 1
                status = (
                    f"{indexed_count}/{total} fully indexed in Chroma"
                    if indexed_count
                    else "saved but not indexed (Chroma unavailable)"
                )
                label = title or metadata["source"]
                await interaction.followup.send(
                    f"Processed `{label}`: added {total} knowledge chunks "
                    f"for persona `{metadata['persona']}` ({status}).",
                    ephemeral=True,
                )
                return

            entry = await service.ingest(
                {
                    **metadata,
                    "content": self.document,
                    "title": self.document_title.strip() if self.document_title else "",
                }
            )
        except (OSError, RuntimeError, ValueError) as exc:
            log.exception("Failed to persist knowledge entry from Discord")
            await interaction.followup.send(
                f"Could not add the knowledge entry: {exc}",
                ephemeral=True,
            )
            return
        indexed = await service.indexed_id(entry.id)
        status = (
            "fully indexed in Chroma"
            if indexed
            else "saved but not indexed (Chroma unavailable)"
        )
        await interaction.followup.send(
            f"Added knowledge entry with ID `{entry.id}` for persona "
            f"`{metadata['persona']}` ({status}).",
            ephemeral=True,
        )


class MetadataReviewView(ui.View):
    """Display a confirmation button before the metadata modal opens.

    Discord interactions expire quickly, so this view keeps the modal available
    long enough for the user to review the prepared metadata before ingestion.
    """

    def __init__(self, modal: MetadataModal, author_id: int):
        super().__init__(timeout=300)
        self.modal = modal
        self.author_id = author_id

    @ui.button(
        label="Review & Confirm Metadata",
        style=discord.ButtonStyle.primary,
        emoji="📝",
    )
    async def review_metadata(
        self, interaction: discord.Interaction, button: ui.Button
    ):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "This action is only available to the author of the command.",
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(self.modal)


class ChromaCog(commands.Cog):
    """Manage the bot's ChromaDB-backed knowledge base.

    The commands in this cog expose the main knowledge-base workflow: search for
    matching passages, add text or attachments with metadata, list recent
    entries, inspect persona-specific records, and delete entries by identifier.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="kbsearch", help="Search the local knowledge base.")
    @app_commands.describe(
        query="Search query",
        persona="Optional persona to filter by",
        limit="Maximum results (default 5)",
    )
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
        try:
            matches = await asyncio.to_thread(
                query_knowledge, query, limit=limit, persona=persona
            )
        except ChromaBackendError:
            await ctx.send(
                "Knowledge base search is currently unavailable.",
                ephemeral=True,
            )
            return
        if not matches:
            await ctx.send("No knowledge base matches found.", ephemeral=True)
            return
        lines = []
        for item in matches:
            meta = item.get("metadata", {})
            persona_name = meta.get("persona", "unknown")
            source = meta.get("source", "unknown")
            entry_type = meta.get("entry_type", "unknown")
            structured_id = meta.get("structured_id", "unknown")
            snippet = item.get("document", "").strip().replace("\n", " ")
            if len(snippet) > 150:
                snippet = snippet[:147] + "..."
            lines.append(
                f"- `{structured_id}` **{persona_name}** "
                f"({entry_type}, {source}):\n    {snippet}"
            )
        response_text = "\n".join(lines)
        # Ensure text fits within Discord's 2000-character limit
        if len(response_text) > 1950:
            response_text = response_text[:1947] + "..."
        await ctx.send(response_text, ephemeral=True)

    @commands.hybrid_command(
        name="kbadd",
        help=(
            "Add a note or attached PDF, EPUB, TXT, or JSON file "
            "to the local knowledge base with metadata."
        ),
    )
    @app_commands.describe(
        title="Title for the knowledge entry (optional; auto-read from file)",
        content="Text content (optional if attaching a file)",
        attachment="File attachment (PDF, EPUB, TXT, JSON, MD)",
        persona="Optional persona identifier (default: DEFAULT_PERSONA_ID)",
        scene="Scene context (optional, e.g., rooftop conversation)",
        speaker="Speaker name (optional, e.g., Protagonist)",
        episode="Episode identifier (optional, e.g., 01)",
        chapter="Chapter identifier (optional, e.g., Chapter 12)",
        timestamp="Timestamp (optional, e.g., 2024-01-01)",
        canon_level=(
            "Canon level (optional: canon, semi-canon, non-canon, headcanon, alternate)"
        ),
        tags="Comma-separated tags (optional, e.g., canon, emotional)",
    )
    @commands.has_permissions(administrator=True)
    async def kbadd(
        self,
        ctx: commands.Context,
        title: str | None = None,
        content: str | None = None,
        attachment: discord.Attachment | None = None,
        persona: str | None = None,
        scene: str | None = None,
        speaker: str | None = None,
        episode: str | None = None,
        chapter: str | None = None,
        timestamp: str | None = None,
        canon_level: str | None = None,
        tags: str | None = None,
    ):
        await ctx.defer(ephemeral=True)
        attachment = attachment or (
            ctx.message.attachments[0]
            if getattr(ctx, "message", None) and ctx.message.attachments
            else None
        )
        text_parts: list[str] = []
        raw_bytes: bytes = b""
        if content and content.strip():
            text_parts.append(content.strip())
        if attachment is not None:
            try:
                raw_bytes = await attachment.read()
            except discord.HTTPException as exc:
                await ctx.send(f"Failed to read attachment: {exc}", ephemeral=True)
                return
            except OSError as exc:
                await ctx.send(f"Failed to read attachment: {exc}", ephemeral=True)
                return
            # Extract text off-thread for CPU-heavy parsing (PDFs, EPUBs, JSON)
            extracted = await asyncio.to_thread(
                extract_text_from_bytes,
                attachment.filename or "attachment.bin",
                raw_bytes,
            )
            if not extracted.strip():
                await ctx.send(
                    "Could not extract readable text from that file. "
                    "Supported input includes PDF, EPUB, TXT, JSON, "
                    "and MD files.",
                    ephemeral=True,
                )
                return
            text_parts.append(extracted)
        if not text_parts:
            await ctx.send(
                "Provide text or attach a supported file (PDF, EPUB, TXT, JSON, MD).",
                ephemeral=True,
            )
            return
        document = "\n\n".join(text_parts)

        # Collect optional metadata from command parameters
        extra_metadata: dict[str, Any] = {}
        book_info: dict[str, str] = {}
        if attachment is not None and raw_bytes:
            filename = attachment.filename or ""
            if filename.lower().endswith(".epub"):
                book_info = extract_epub_book_info(raw_bytes, filename)
                if book_info.get("author"):
                    extra_metadata["author"] = book_info["author"]

        # Automatically determine title from EPUB metadata, filename, or text
        if not title or not title.strip():
            if book_info.get("title"):
                resolved_title = book_info["title"]
            elif attachment and attachment.filename:
                raw_name = attachment.filename
                base_name = raw_name.rsplit(".", 1)[0] if "." in raw_name else raw_name
                resolved_title = base_name.replace("_", " ").strip()
            elif content and content.strip():
                resolved_title = content.strip().splitlines()[0][:50].strip()
            else:
                resolved_title = "Knowledge Entry"
        else:
            resolved_title = title.strip()

        if scene and scene.strip():
            extra_metadata["scene"] = scene.strip()
        if speaker and speaker.strip():
            extra_metadata["speaker"] = speaker.strip()
        if episode and episode.strip():
            extra_metadata["episode"] = episode.strip()
        if chapter and chapter.strip():
            extra_metadata["chapter"] = chapter.strip()
        if timestamp and timestamp.strip():
            extra_metadata["timestamp"] = timestamp.strip()
        if canon_level and canon_level.strip():
            extra_metadata["canon_level"] = canon_level.strip().lower()
        if tags and tags.strip():
            extra_metadata["tags"] = [t.strip() for t in tags.split(",") if t.strip()]

        # Determine smart defaults
        filename = (
            attachment.filename.lower() if attachment and attachment.filename else ""
        )
        if filename.endswith((".epub", ".mobi")):
            detected_source_type = "novel"
        elif filename.endswith((".pdf", ".txt", ".md")):
            detected_source_type = "novel"
        else:
            detected_source_type = "other"

        default_persona = (
            persona.strip() if persona and persona.strip() else get_default_persona()
        )
        # Prefer the resolved title (user-provided or auto-detected) so the
        # pre-filled Source field reflects what the user typed; fall back to
        # EPUB metadata source, then to the resolved title again.
        default_source = resolved_title or book_info.get("source")
        modal = MetadataModal(
            document,
            resolved_title,
            attachment.filename if attachment else None,
            default_persona=default_persona,
            default_source=default_source,
            default_source_type=detected_source_type,
            default_entry_type="narration",
            default_topics="novel, story, canon",
            extra_metadata=extra_metadata,
        )

        interaction = ctx.interaction
        if interaction is not None:
            view = MetadataReviewView(modal, ctx.author.id)
            msg = (
                f"📖 **{resolved_title}** prepared "
                f"({len(document):,} characters).\n"
                "Click below to review metadata and confirm ingestion:"
            )
            await ctx.send(msg, view=view, ephemeral=True)
        else:
            await ctx.send(
                "Knowledge Base ingestion requires slash commands.",
                ephemeral=True,
            )

    @commands.hybrid_command(
        name="kblist", help="List the newest knowledge base entries."
    )
    @app_commands.describe(
        persona="Optional persona to filter by",
        limit="Maximum entries to show (default 15)",
    )
    @commands.has_permissions(administrator=True)
    async def kblist(
        self,
        ctx: commands.Context,
        persona: str | None = None,
        limit: int = 15,
    ):
        await ctx.defer(ephemeral=True)
        service = KnowledgeBaseService(get_knowledge_base_database())
        await service.initialize()
        entries = (await service.list_entries(persona=persona))[:limit]
        if not entries:
            await ctx.send("No knowledge base entries found.", ephemeral=True)
            return
        lines = []
        for index, item in enumerate(entries, start=1):
            meta = item.metadata or {}
            # Fallback chain for a clean title display
            title = meta.get("title") or meta.get("filename") or item.id
            persona_name = item.persona
            source = item.source
            entry_type = item.entry_type
            # If the title is a long file path, pull just the filename
            if "/" in title or "\\" in title:
                title = title.replace("\\", "/").split("/")[-1]
            snippet = item.content.strip().replace("\n", " ")
            if len(snippet) > 80:
                snippet = snippet[:77] + "..."
            lines.append(
                f"**{index}.** [{persona_name}] {title} (`{item.id}`)\n└ {
                    entry_type
                } · {source} · *{snippet}*"
            )
        full_message = "\n".join(lines)
        # Safe pagination / length check for Discord output limit
        if len(full_message) > 1950:
            full_message = full_message[:1947] + "..."
        await ctx.send(full_message, ephemeral=True)

    @commands.hybrid_command(
        name="kbdelete", help="Delete a knowledge base entry by id."
    )
    @commands.has_permissions(administrator=True)
    async def kbdelete(self, ctx: commands.Context, entry_id: str):
        await ctx.defer(ephemeral=True)
        service = KnowledgeBaseService(get_knowledge_base_database())
        await service.initialize()
        success = await service.delete_entry(entry_id)
        if success:
            await ctx.send(f"Deleted knowledge entry `{entry_id}`.", ephemeral=True)
            return
        await ctx.send("Could not delete that knowledge entry.", ephemeral=True)

    @commands.hybrid_command(
        name="kbpersona",
        help="List all knowledge entries for a specific persona.",
    )
    @app_commands.describe(
        persona="Persona ID to list entries for",
        limit="Maximum entries to show (default 50)",
    )
    @commands.has_permissions(administrator=True)
    async def kbpersona(self, ctx: commands.Context, persona: str, limit: int = 50):
        await ctx.defer(ephemeral=True)
        service = KnowledgeBaseService(get_knowledge_base_database())
        await service.initialize()
        entries = (await service.list_entries(persona=persona))[:limit]
        if not entries:
            await ctx.send(
                f"No knowledge base entries found for persona `{persona}`.",
                ephemeral=True,
            )
            return
        lines = []
        for index, item in enumerate(entries, start=1):
            meta = item.metadata or {}
            source = item.source
            entry_type = item.entry_type
            scene = meta.get("scene", "")
            scene_str = f" · {scene}" if scene else ""
            snippet = item.content.strip().replace("\n", " ")
            if len(snippet) > 100:
                snippet = snippet[:97] + "..."
            lines.append(
                f"**{index}.** `{item.id}` [{entry_type}] "
                f"{source}{scene_str}\n└ *{snippet}*"
            )
        full_message = "\n".join(lines)
        if len(full_message) > 1950:
            full_message = full_message[:1947] + "..."
        await ctx.send(full_message, ephemeral=True)


async def setup(bot):
    await bot.add_cog(ChromaCog(bot))
