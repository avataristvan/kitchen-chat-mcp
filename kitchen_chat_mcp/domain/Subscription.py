from dataclasses import dataclass

from kitchen_chat_mcp.domain.Message import Message, MessageKind


@dataclass(frozen=True)
class Subscription:
    room: str
    kind: MessageKind | None = None

    def matches(self, message: Message) -> bool:
        return message.room == self.room and (self.kind is None or message.kind is self.kind)
