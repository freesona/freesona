#!/usr/bin/env python3

from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cogs.ai.chroma import ChromaCog


@pytest.mark.asyncio

async def test_kbadd_opens_modal_without_prerequisite_followup_message():

    cog = ChromaCog(bot=MagicMock())

    ctx = MagicMock()

    ctx.defer = AsyncMock()

    ctx.send = AsyncMock()

    ctx.interaction = MagicMock()

    ctx.interaction.response.send_modal = AsyncMock()

    ctx.message = MagicMock(attachments=[])



    attachment = MagicMock()

    attachment.filename = "note.txt"

    attachment.read = AsyncMock(return_value=b"hello world")



    kbadd_callback = cast(Any, cog.kbadd.callback)



    with patch(

        "cogs.ai.chroma.extract_text_from_bytes",

        return_value="hello world",

    ):

        await kbadd_callback(

            cog,

            ctx,

            "Example title",

            None,

            attachment,

        )



    ctx.send.assert_not_called()

    ctx.interaction.response.send_modal.assert_awaited_once()

