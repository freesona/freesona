#!/usr/bin/env python3
import os
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cogs.ai.chroma import ChromaCog, MetadataModal, MetadataReviewView


@pytest.mark.anyio
async def test_kbadd_bridges_modal_with_review_view():
    cog = ChromaCog(bot=MagicMock())
    ctx = MagicMock()
    ctx.defer = AsyncMock()
    ctx.send = AsyncMock()
    ctx.interaction = MagicMock()
    ctx.author = MagicMock(id=12345)
    ctx.message = MagicMock(attachments=[])
    attachment = MagicMock()
    attachment.filename = "novel.epub"
    attachment.read = AsyncMock(return_value=b"hello book content")
    kbadd_callback = cast(Any, cog.kbadd.callback)
    with (
        patch(
            "cogs.ai.chroma.extract_text_from_bytes",
            return_value="hello book content",
        ),
        patch.dict(os.environ, {"DEFAULT_PERSONA_ID": "persona"}),
    ):
        await kbadd_callback(
            cog,
            ctx,
            "Volume 01",
            None,
            attachment,
        )
    ctx.defer.assert_awaited_once_with(ephemeral=True)
    ctx.send.assert_awaited_once()
    view = ctx.send.call_args.kwargs.get("view")
    assert isinstance(view, MetadataReviewView)
    assert view.modal.source.default == "Volume 01"
    assert view.modal.source_type.default == "novel"
    assert view.modal.persona.default == "persona"

    # Verify button interaction opens the modal
    button_interaction = MagicMock()
    button_interaction.user.id = 12345
    button_interaction.response.send_modal = AsyncMock()
    await view.review_metadata.callback(button_interaction)
    button_interaction.response.send_modal.assert_awaited_once_with(view.modal)


@pytest.mark.anyio
async def test_kbadd_auto_detects_title_from_epub_filename():
    cog = ChromaCog(bot=MagicMock())
    ctx = MagicMock()
    ctx.defer = AsyncMock()
    ctx.send = AsyncMock()
    ctx.interaction = MagicMock()
    ctx.author = MagicMock(id=12345)
    ctx.message = MagicMock(attachments=[])
    attachment = MagicMock()
    attachment.filename = "Too_Many_Losing_Heroines_Volume_1.epub"
    attachment.read = AsyncMock(return_value=b"some bytes")
    kbadd_callback = cast(Any, cog.kbadd.callback)
    with (
        patch(
            "cogs.ai.chroma.extract_text_from_bytes",
            return_value="sample book content",
        ),
        patch(
            "cogs.ai.chroma.extract_epub_book_info",
            return_value={
                "title": "Too Many Losing Heroines! Volume 1",
                "author": "Takibi Amamori",
            },
        ),
    ):
        await kbadd_callback(
            cog,
            ctx,
            None,  # No title provided by user!
            None,
            attachment,
        )
    ctx.defer.assert_awaited_once_with(ephemeral=True)
    ctx.send.assert_awaited_once()
    view = ctx.send.call_args.kwargs.get("view")
    assert isinstance(view, MetadataReviewView)
    assert view.modal.source.default == "Too Many Losing Heroines! Volume 1"
    assert view.modal.source_type.default == "novel"
    assert view.modal.extra_metadata.get("author") == "Takibi Amamori"


@pytest.mark.anyio
async def test_metadata_modal_auto_chunks_large_documents():
    # Long text with paragraphs exceeding 1500 characters
    paragraphs = [
        f"Paragraph {i}: " + ("This is narrative text about the world. " * 15)
        for i in range(10)
    ]
    doc = "\n\n".join(paragraphs)
    assert len(doc) > 3000

    modal = MetadataModal(
        document=doc,
        title="Epic Novel",
        attachment_filename="novel.epub",
    )
    modal.persona._value = "persona"
    modal.source._value = "Volume 01"
    modal.source_type._value = "novel"
    modal.entry_type._value = "narration"
    modal.topics._value = "food, summer"

    interaction = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()

    mock_service = MagicMock()
    mock_service.initialize = AsyncMock()
    mock_service.ingest = AsyncMock(return_value=MagicMock(id="entry-123"))
    mock_service.indexed_id = AsyncMock(return_value="chroma-123")

    with patch("cogs.ai.chroma.KnowledgeBaseService", return_value=mock_service):
        await modal.on_submit(interaction)

    interaction.response.defer.assert_awaited_once_with(ephemeral=True)
    assert mock_service.ingest.await_count > 1
    interaction.followup.send.assert_awaited_once()
    msg = interaction.followup.send.call_args[0][0]
    assert "added" in msg and "chunks" in msg
