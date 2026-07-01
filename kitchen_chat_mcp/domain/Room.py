from kitchen_chat_mcp.domain.Message import Message, MessageKind


class RoomInvariantError(Exception):
    pass


class Room:
    def __init__(self, name: str):
        self.name = name

    def ensure_can_answer(self, question: Message | None, existing_answers: list[Message]) -> None:
        if question is None:
            raise RoomInvariantError("no such question in room")
        if question.room != self.name:
            raise RoomInvariantError(f"question {question.id} does not belong to room '{self.name}'")
        if question.kind is not MessageKind.QUESTION:
            raise RoomInvariantError(f"message {question.id} is not a question")
        if existing_answers:
            raise RoomInvariantError(f"question {question.id} is already answered")
