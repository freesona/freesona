"""Discord-independent request data for one Freesona interaction."""

from dataclasses import dataclass, field
from typing import TypedDict


class MentionData(TypedDict):
    id: int
    name: str
    mention: str


class ReplyData(TypedDict, total=False):
    author: str
    author_id: int
    content: str
    is_bot: bool
    is_webhook: bool
    role: str
    embeds: list[str]


@dataclass
class InteractionRequest:
    """Plain data required to generate one interaction response.

    Discord adapters must serialize messages and read attachments before they
    create this request. Access to external context services is injected
    separately when the runtime runs.
    """

    content: str
    current_persona: str
    channel_id: int | None = None
    guild_id: int | None = None
    user_id: int | None = None
    message_id: int | None = None
    apply_persona: bool = True
    instruction_prefix: str = ""
    username: str = ""
    attachments: list[tuple[bytes, str]] | None = None
    persona_id: str = ""
    mentions: list[MentionData] = field(default_factory=list)
    reply: ReplyData | None = None
    embeds: list[str] = field(default_factory=list)
