from abc import ABC, abstractmethod

from kitchen_chat_mcp.domain.Message import Message


class MessageStore(ABC):
    @abstractmethod
    def append(self, message: Message) -> int:
        """Persist the message and return its assigned sequence number."""

    @abstractmethod
    def poll(self, room: str, since_seq: int) -> list[tuple[int, Message]]:
        """Return (seq, message) pairs for the room with seq > since_seq, in order."""

    @abstractmethod
    def get(self, room: str, message_id: str) -> Message | None:
        """Return the message with the given id in the room, or None if not found."""

    @abstractmethod
    def find_answers(self, room: str, question_id: str) -> list[Message]:
        """Return all messages in the room that reply to question_id."""
