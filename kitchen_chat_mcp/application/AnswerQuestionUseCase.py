from kitchen_chat_mcp.domain.Message import Message, MessageKind
from kitchen_chat_mcp.domain.MessageStore import MessageStore
from kitchen_chat_mcp.domain.Room import Room


class AnswerQuestionUseCase:
    def __init__(self, store: MessageStore):
        self._store = store

    def execute(self, room: str, sender_session_id: str, question_id: str, reply: str) -> Message:
        question = self._store.get(room, question_id)
        existing_answers = self._store.find_answers(room, question_id) if question is not None else []

        Room(room).ensure_can_answer(question, existing_answers)

        answer = Message(
            room=room,
            sender_session_id=sender_session_id,
            kind=MessageKind.ANSWER,
            content=reply,
            in_reply_to=question_id,
        )
        self._store.append(answer)
        return answer
