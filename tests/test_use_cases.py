import threading
import time
import unittest

from kitchen_chat_mcp.application.AnswerQuestionUseCase import AnswerQuestionUseCase
from kitchen_chat_mcp.application.AskQuestionUseCase import AskQuestionUseCase, AskTimeoutError
from kitchen_chat_mcp.application.PollMessagesUseCase import PollMessagesUseCase
from kitchen_chat_mcp.application.PublishMessageUseCase import PublishMessageUseCase
from kitchen_chat_mcp.domain.Message import Message, MessageKind
from kitchen_chat_mcp.domain.Room import RoomInvariantError
from tests.fakes import InMemoryMessageStore


class TestPublishAndPoll(unittest.TestCase):
    def test_round_trip_respects_since_seq(self):
        store = InMemoryMessageStore()
        publish = PublishMessageUseCase(store)
        poll = PollMessagesUseCase(store)

        first = publish.execute("kitchen", "session-a", "Script finalisiert")
        second = publish.execute("kitchen", "session-b", "Hero-Take: ~7s")

        all_messages = poll.execute("kitchen", since_seq=0)
        self.assertEqual([msg.id for _, msg in all_messages], [first.id, second.id])

        only_second = poll.execute("kitchen", since_seq=all_messages[0][0])
        self.assertEqual([msg.id for _, msg in only_second], [second.id])


class TestAnswerQuestion(unittest.TestCase):
    def test_happy_path_then_second_answer_raises(self):
        store = InMemoryMessageStore()
        answer_use_case = AnswerQuestionUseCase(store)

        question = Message(
            room="kitchen",
            sender_session_id="session-a",
            kind=MessageKind.QUESTION,
            content="Brauchen wir OCR-Nachdreh?",
        )
        store.append(question)

        answer = answer_use_case.execute("kitchen", "session-b", question.id, "Nein, Take 2 ist sauber")
        self.assertEqual(answer.in_reply_to, question.id)
        self.assertEqual(answer.kind, MessageKind.ANSWER)

        with self.assertRaises(RoomInvariantError):
            answer_use_case.execute("kitchen", "session-c", question.id, "Doch, bitte nachdrehen")


class TestAskQuestion(unittest.TestCase):
    def test_returns_answer_delivered_by_background_thread(self):
        store = InMemoryMessageStore()
        ask_use_case = AskQuestionUseCase(store, poll_interval_seconds=0.02)
        answer_use_case = AnswerQuestionUseCase(store)

        def answer_soon():
            time.sleep(0.05)
            question = next(msg for _, msg in store.poll("kitchen", 0) if msg.kind is MessageKind.QUESTION)
            answer_use_case.execute("kitchen", "session-b", question.id, "Nein, Take 2 ist sauber")

        thread = threading.Thread(target=answer_soon)
        thread.start()

        result = ask_use_case.execute("kitchen", "session-a", "Brauchen wir OCR-Nachdreh?", timeout_seconds=1.0)
        thread.join()

        self.assertEqual(result.content, "Nein, Take 2 ist sauber")

    def test_raises_timeout_error_when_unanswered(self):
        store = InMemoryMessageStore()
        ask_use_case = AskQuestionUseCase(store, poll_interval_seconds=0.02)

        with self.assertRaises(AskTimeoutError):
            ask_use_case.execute("kitchen", "session-a", "Brauchen wir OCR-Nachdreh?", timeout_seconds=0.3)


if __name__ == "__main__":
    unittest.main()
