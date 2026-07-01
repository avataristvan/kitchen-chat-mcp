import unittest

from kitchen_chat_mcp.domain.Message import Message, MessageKind
from kitchen_chat_mcp.domain.Room import Room, RoomInvariantError


class TestRoomEnsureCanAnswer(unittest.TestCase):
    def setUp(self):
        self.room = Room("kitchen")
        self.question = Message(
            room="kitchen",
            sender_session_id="session-a",
            kind=MessageKind.QUESTION,
            content="Brauchen wir OCR-Nachdreh?",
        )

    def test_succeeds_for_open_question_with_no_existing_answers(self):
        self.room.ensure_can_answer(self.question, [])

    def test_raises_when_question_is_none(self):
        with self.assertRaises(RoomInvariantError):
            self.room.ensure_can_answer(None, [])

    def test_raises_when_question_already_answered(self):
        answer = Message(
            room="kitchen",
            sender_session_id="session-b",
            kind=MessageKind.ANSWER,
            content="Nein, Take 2 ist sauber",
            in_reply_to=self.question.id,
        )
        with self.assertRaises(RoomInvariantError):
            self.room.ensure_can_answer(self.question, [answer])

    def test_raises_when_question_room_does_not_match(self):
        other_room = Room("garage")
        with self.assertRaises(RoomInvariantError):
            other_room.ensure_can_answer(self.question, [])

    def test_raises_when_message_is_not_a_question(self):
        broadcast = Message(
            room="kitchen",
            sender_session_id="session-a",
            kind=MessageKind.BROADCAST,
            content="Script finalisiert",
        )
        with self.assertRaises(RoomInvariantError):
            self.room.ensure_can_answer(broadcast, [])


if __name__ == "__main__":
    unittest.main()
