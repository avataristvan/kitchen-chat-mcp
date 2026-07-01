import time

from kitchen_chat_mcp.domain.Message import Message, MessageKind
from kitchen_chat_mcp.domain.MessageStore import MessageStore


class AskTimeoutError(Exception):
    pass


class AskQuestionUseCase:
    def __init__(self, store: MessageStore, poll_interval_seconds: float = 0.5):
        self._store = store
        self._poll_interval_seconds = poll_interval_seconds

    def execute(self, room: str, sender_session_id: str, question: str, timeout_seconds: float) -> Message:
        message = Message(
            room=room,
            sender_session_id=sender_session_id,
            kind=MessageKind.QUESTION,
            content=question,
        )
        self._store.append(message)

        deadline = time.monotonic() + timeout_seconds
        while True:
            answers = self._store.find_answers(room, message.id)
            if answers:
                return answers[0]
            remaining_time = deadline - time.monotonic()
            if remaining_time <= 0:
                raise AskTimeoutError(f"question {message.id} timed out after {timeout_seconds}s")
            time.sleep(min(self._poll_interval_seconds, remaining_time))
