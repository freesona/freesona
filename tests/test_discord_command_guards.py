import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from cogs.media.mvsep import _has_message_attachment
from cogs.tools.ping import _invocation_timestamp


class TestDiscordCommandGuards(unittest.TestCase):
    def test_ping_uses_message_timestamp_for_prefix_commands(self):
        created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        ctx = SimpleNamespace(
            message=SimpleNamespace(created_at=created_at), interaction=None
        )

        self.assertEqual(_invocation_timestamp(ctx), created_at)

    def test_ping_uses_interaction_timestamp_for_slash_commands(self):
        created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        ctx = SimpleNamespace(
            message=None, interaction=SimpleNamespace(created_at=created_at)
        )

        self.assertEqual(_invocation_timestamp(ctx), created_at)

    def test_slash_context_without_attachment_is_safe(self):
        ctx = SimpleNamespace(message=None)

        self.assertFalse(_has_message_attachment(ctx))  # type: ignore[arg-type]

    def test_prefix_context_detects_attachment(self):
        ctx = SimpleNamespace(message=SimpleNamespace(attachments=[object()]))

        self.assertTrue(_has_message_attachment(ctx))  # type: ignore[arg-type]
