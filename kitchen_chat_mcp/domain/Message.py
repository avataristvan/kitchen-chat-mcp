import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class MessageKind(Enum):
    BROADCAST = "broadcast"
    QUESTION = "question"
    ANSWER = "answer"
    PRESENCE = "presence"


@dataclass(frozen=True)
class Message:
    room: str
    sender_session_id: str
    kind: MessageKind
    content: str
    in_reply_to: str | None = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
