import os
import tempfile
import threading
import unittest

from kitchen_chat_mcp.domain.Message import Message, MessageKind
from kitchen_chat_mcp.domain.Room import RoomInvariantError
from kitchen_chat_mcp.infrastructure.SqliteMessageStore import SqliteMessageStore


class TestSqliteMessageStore(unittest.TestCase):
    def setUp(self):
        self._tempdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self._tempdir.name, "messages.db")
        self.store = SqliteMessageStore(self.db_path)

    def tearDown(self):
        self._tempdir.cleanup()

    def test_append_then_get_round_trips_fields(self):
        message = Message(
            room="kitchen",
            sender_session_id="session-a",
            kind=MessageKind.QUESTION,
            content="Brauchen wir OCR-Nachdreh?",
        )
        self.store.append(message)

        fetched = self.store.get("kitchen", message.id)

        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.id, message.id)
        self.assertEqual(fetched.room, message.room)
        self.assertEqual(fetched.sender_session_id, message.sender_session_id)
        self.assertEqual(fetched.kind, message.kind)
        self.assertEqual(fetched.content, message.content)
        self.assertEqual(fetched.in_reply_to, message.in_reply_to)
        self.assertEqual(fetched.created_at, message.created_at)

    def test_poll_returns_messages_in_seq_order_since_seq(self):
        first = Message(room="kitchen", sender_session_id="session-a", kind=MessageKind.BROADCAST, content="first")
        second = Message(room="kitchen", sender_session_id="session-b", kind=MessageKind.BROADCAST, content="second")
        other_room = Message(room="living-room", sender_session_id="session-c", kind=MessageKind.BROADCAST, content="other")

        self.store.append(first)
        self.store.append(second)
        self.store.append(other_room)

        all_messages = self.store.poll("kitchen", since_seq=0)
        self.assertEqual([msg.id for _, msg in all_messages], [first.id, second.id])

        last_seq = all_messages[-1][0]
        no_new_messages = self.store.poll("kitchen", since_seq=last_seq)
        self.assertEqual(no_new_messages, [])

    def test_find_answers_filters_by_room_and_in_reply_to(self):
        # Each question gets its own id, since in_reply_to is now globally unique
        # (at most one answer per question, enforced at the storage layer) —
        # two answers replying to the *same* question id is not a valid scenario.
        question = Message(room="kitchen", sender_session_id="session-a", kind=MessageKind.QUESTION, content="q")
        other_room_question = Message(
            room="living-room", sender_session_id="session-c", kind=MessageKind.QUESTION, content="other q"
        )
        self.store.append(question)
        self.store.append(other_room_question)

        matching_answer = Message(
            room="kitchen",
            sender_session_id="session-b",
            kind=MessageKind.ANSWER,
            content="matching answer",
            in_reply_to=question.id,
        )
        other_room_answer = Message(
            room="living-room",
            sender_session_id="session-c",
            kind=MessageKind.ANSWER,
            content="other room answer",
            in_reply_to=other_room_question.id,
        )
        unrelated_answer = Message(
            room="kitchen",
            sender_session_id="session-d",
            kind=MessageKind.ANSWER,
            content="unrelated answer",
            in_reply_to="some-other-question-id",
        )
        self.store.append(matching_answer)
        self.store.append(other_room_answer)
        self.store.append(unrelated_answer)

        answers = self.store.find_answers("kitchen", question.id)

        self.assertEqual([msg.id for msg in answers], [matching_answer.id])

    def test_get_returns_none_for_nonexistent_message(self):
        self.assertIsNone(self.store.get("kitchen", "does-not-exist"))

    def test_concurrent_append_from_multiple_threads_is_safe(self):
        errors: list[Exception] = []

        def append_many(sender: str):
            try:
                for i in range(20):
                    message = Message(
                        room="kitchen",
                        sender_session_id=sender,
                        kind=MessageKind.BROADCAST,
                        content=f"{sender}-{i}",
                    )
                    self.store.append(message)
            except Exception as exc:  # noqa: BLE001 - captured for assertion in main thread
                errors.append(exc)

        threads = [
            threading.Thread(target=append_many, args=("session-a",)),
            threading.Thread(target=append_many, args=("session-b",)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(errors, [])

        all_messages = self.store.poll("kitchen", since_seq=0)
        self.assertEqual(len(all_messages), 40)

        seqs = [seq for seq, _ in all_messages]
        self.assertEqual(len(seqs), len(set(seqs)))

    def test_second_answer_to_same_question_is_rejected_even_without_a_precheck(self):
        # Regression test for the check-then-append race: simulates two processes
        # that both skip AnswerQuestionUseCase's read-validate step and append
        # competing answers directly. The storage layer alone must still enforce
        # "at most one answer per question" via the unique partial index.
        question = Message(room="kitchen", sender_session_id="session-a", kind=MessageKind.QUESTION, content="q")
        self.store.append(question)

        first_answer = Message(
            room="kitchen", sender_session_id="session-b", kind=MessageKind.ANSWER,
            content="first", in_reply_to=question.id,
        )
        second_answer = Message(
            room="kitchen", sender_session_id="session-c", kind=MessageKind.ANSWER,
            content="second", in_reply_to=question.id,
        )

        self.store.append(first_answer)
        with self.assertRaises(RoomInvariantError):
            self.store.append(second_answer)

        answers = self.store.find_answers("kitchen", question.id)
        self.assertEqual([msg.id for msg in answers], [first_answer.id])

    def test_broadcasts_and_questions_are_unaffected_by_the_unique_index(self):
        # in_reply_to is NULL for broadcasts/questions — the partial unique index
        # must not limit how many of those can exist.
        for i in range(3):
            self.store.append(
                Message(room="kitchen", sender_session_id="session-a", kind=MessageKind.BROADCAST, content=f"b{i}")
            )
        all_messages = self.store.poll("kitchen", since_seq=0)
        self.assertEqual(len(all_messages), 3)

    def test_list_rooms_returns_distinct_rooms_most_recently_active_first(self):
        self.store.append(Message(room="kitchen", sender_session_id="a", kind=MessageKind.BROADCAST, content="1"))
        self.store.append(Message(room="living-room", sender_session_id="a", kind=MessageKind.BROADCAST, content="2"))
        self.store.append(Message(room="kitchen", sender_session_id="a", kind=MessageKind.BROADCAST, content="3"))

        self.assertEqual(self.store.list_rooms(), ["kitchen", "living-room"])

    def test_list_rooms_is_empty_when_no_messages_exist(self):
        self.assertEqual(self.store.list_rooms(), [])


if __name__ == "__main__":
    unittest.main()
