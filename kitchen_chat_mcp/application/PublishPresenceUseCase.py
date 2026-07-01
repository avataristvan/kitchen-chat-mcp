from kitchen_chat_mcp.domain.Message import Message, MessageKind
from kitchen_chat_mcp.domain.MessageStore import MessageStore


class PublishPresenceUseCase:
    def __init__(self, store: MessageStore):
        self._store = store

    def execute(self, room: str, sender_session_id: str, content: str) -> Message:
        message = Message(
            room=room,
            sender_session_id=sender_session_id,
            kind=MessageKind.PRESENCE,
            content=content,
        )
        self._store.append(message)
        return message
