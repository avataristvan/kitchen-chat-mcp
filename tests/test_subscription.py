import unittest

from kitchen_chat_mcp.domain.Message import Message, MessageKind
from kitchen_chat_mcp.domain.Subscription import Subscription
from kitchen_chat_mcp.domain.SubscriptionRegistry import SubscriptionRegistry


class TestSubscriptionMatches(unittest.TestCase):
    def test_matches_same_room_and_kind(self):
        subscription = Subscription(room="kitchen", kind=MessageKind.QUESTION)
        message = Message(
            room="kitchen",
            sender_session_id="session-a",
            kind=MessageKind.QUESTION,
            content="Brauchen wir OCR-Nachdreh?",
        )

        self.assertTrue(subscription.matches(message))

    def test_matches_same_room_with_wildcard_kind(self):
        subscription = Subscription(room="kitchen", kind=None)
        message = Message(
            room="kitchen",
            sender_session_id="session-a",
            kind=MessageKind.BROADCAST,
            content="Script finalisiert",
        )

        self.assertTrue(subscription.matches(message))

    def test_does_not_match_different_room(self):
        subscription = Subscription(room="kitchen", kind=None)
        message = Message(
            room="living-room",
            sender_session_id="session-a",
            kind=MessageKind.BROADCAST,
            content="Script finalisiert",
        )

        self.assertFalse(subscription.matches(message))

    def test_does_not_match_different_kind(self):
        subscription = Subscription(room="kitchen", kind=MessageKind.ANSWER)
        message = Message(
            room="kitchen",
            sender_session_id="session-a",
            kind=MessageKind.QUESTION,
            content="Brauchen wir OCR-Nachdreh?",
        )

        self.assertFalse(subscription.matches(message))


class TestSubscriptionRegistry(unittest.TestCase):
    def test_all_returns_added_subscriptions_in_order(self):
        registry = SubscriptionRegistry()
        first = Subscription(room="kitchen", kind=MessageKind.QUESTION)
        second = Subscription(room="living-room", kind=None)

        registry.add(first)
        registry.add(second)

        self.assertEqual(registry.all(), [first, second])


if __name__ == "__main__":
    unittest.main()
