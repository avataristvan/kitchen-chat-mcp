from kitchen_chat_mcp.domain.Message import Message
from kitchen_chat_mcp.domain.MessageStore import MessageStore


class PollMessagesUseCase:
    def __init__(self, store: MessageStore):
        self._store = store

    def execute(self, room: str, since_seq: int) -> list[tuple[int, Message]]:
        return self._store.poll(room, since_seq)
