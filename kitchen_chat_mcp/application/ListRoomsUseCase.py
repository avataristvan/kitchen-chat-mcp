from kitchen_chat_mcp.domain.MessageStore import MessageStore


class ListRoomsUseCase:
    def __init__(self, store: MessageStore):
        self._store = store

    def execute(self) -> list[str]:
        return self._store.list_rooms()
