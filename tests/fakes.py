from kitchen_chat_mcp.domain.Message import Message
from kitchen_chat_mcp.domain.MessageStore import MessageStore


class InMemoryMessageStore(MessageStore):
    def __init__(self):
        self._entries: list[tuple[int, Message]] = []
        self._next_seq = 1

    def append(self, message: Message) -> int:
        seq = self._next_seq
        self._next_seq += 1
        self._entries.append((seq, message))
        return seq

    def poll(self, room: str, since_seq: int) -> list[tuple[int, Message]]:
        return [(seq, msg) for seq, msg in self._entries if msg.room == room and seq > since_seq]

    def get(self, room: str, message_id: str) -> Message | None:
        for _, msg in self._entries:
            if msg.room == room and msg.id == message_id:
                return msg
        return None

    def find_answers(self, room: str, question_id: str) -> list[Message]:
        return [msg for _, msg in self._entries if msg.room == room and msg.in_reply_to == question_id]
