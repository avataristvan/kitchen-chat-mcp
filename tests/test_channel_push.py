import asyncio
import os
import tempfile
import unittest
from unittest.mock import patch

from kitchen_chat_mcp.domain.Message import MessageKind
from kitchen_chat_mcp.domain.Subscription import Subscription
from kitchen_chat_mcp.domain.SubscriptionRegistry import SubscriptionRegistry
from kitchen_chat_mcp.infrastructure.RoomAllowlist import RoomAllowlist
from kitchen_chat_mcp.infrastructure.SqliteMessageStore import SqliteMessageStore
from kitchen_chat_mcp.ui import server


class ChannelPushTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        db_path = os.path.join(self._tmp_dir.name, "test-kitchen-chat.db")
        self._store_patcher = patch.object(server, "store", SqliteMessageStore(db_path))
        self._allowlist_patcher = patch.object(server, "allowlist", RoomAllowlist())
        self._subscriptions_patcher = patch.object(server, "subscriptions", SubscriptionRegistry())
        self._watermarks_patcher = patch.object(server, "_watermarks", {})
        self._store_patcher.start()
        self._allowlist_patcher.start()
        self._subscriptions_patcher.start()
        self._watermarks_patcher.start()

    def tearDown(self):
        self._store_patcher.stop()
        self._allowlist_patcher.stop()
        self._subscriptions_patcher.stop()
        self._watermarks_patcher.stop()
        self._tmp_dir.cleanup()


class TestSeedWatermarkAndBacklog(ChannelPushTestCase):
    def test_subscription_does_not_receive_pre_existing_messages_but_does_receive_new_ones(self):
        server.publish("kitchen", "session-a", "before subscribing")

        subscription = Subscription(room="kitchen")
        first_matches = server._collect_new_matches([subscription], server.store)
        self.assertEqual(first_matches, [])

        server.publish("kitchen", "session-b", "after subscribing")
        second_matches = server._collect_new_matches([subscription], server.store)
        self.assertEqual(len(second_matches), 1)
        matched_subscription, matched_message = second_matches[0]
        self.assertEqual(matched_subscription, subscription)
        self.assertEqual(matched_message.content, "after subscribing")


class TestSubscribeToolSeedsWatermarkImmediately(ChannelPushTestCase):
    def test_message_published_right_after_subscribing_is_still_delivered(self):
        result = server.subscribe("kitchen")
        self.assertEqual(result["status"], "ok")

        published = server.publish("kitchen", "session-a", "right after subscribing")

        matches = server._collect_new_matches(server.subscriptions.all(), server.store)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0][1].id, published["message_id"])


class TestKindFiltering(ChannelPushTestCase):
    def test_kind_specific_subscription_only_receives_that_kind(self):
        subscription = Subscription(room="kitchen", kind=MessageKind.QUESTION)
        server._seed_watermark_if_new(subscription, server.store)

        server.publish("kitchen", "session-a", "just a broadcast")
        server.ask("kitchen", "session-a", "real question?", timeout_seconds=0.1)

        matches = server._collect_new_matches([subscription], server.store)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0][1].kind, MessageKind.QUESTION)

    def test_wildcard_subscription_receives_all_but_presence(self):
        subscription = Subscription(room="kitchen")
        server._seed_watermark_if_new(subscription, server.store)

        broadcast = server.publish("kitchen", "session-a", "a broadcast")
        server.ask("kitchen", "session-a", "a question?", timeout_seconds=0.1)
        server.answer("kitchen", "session-b", server.poll("kitchen")["messages"][-1]["id"], "an answer")
        server.presence("kitchen", "session-a", "still here")

        matches = server._collect_new_matches([subscription], server.store)
        kinds = {message.kind for _, message in matches}
        self.assertEqual(kinds, {MessageKind.BROADCAST, MessageKind.QUESTION, MessageKind.ANSWER})
        self.assertNotIn(MessageKind.PRESENCE, kinds)
        self.assertIn(broadcast["message_id"], [message.id for _, message in matches])

    def test_presence_subscription_receives_presence_messages(self):
        subscription = Subscription(room="kitchen", kind=MessageKind.PRESENCE)
        server._seed_watermark_if_new(subscription, server.store)

        server.presence("kitchen", "session-a", "still here")

        matches = server._collect_new_matches([subscription], server.store)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0][1].kind, MessageKind.PRESENCE)


class TestWatermarkAdvancesWithoutDuplication(ChannelPushTestCase):
    def test_second_call_with_no_new_messages_returns_empty(self):
        subscription = Subscription(room="kitchen")
        server._seed_watermark_if_new(subscription, server.store)
        server.publish("kitchen", "session-a", "one message")

        first_matches = server._collect_new_matches([subscription], server.store)
        self.assertEqual(len(first_matches), 1)

        second_matches = server._collect_new_matches([subscription], server.store)
        self.assertEqual(second_matches, [])


class TestSendChannelNotificationWithoutSession(ChannelPushTestCase):
    def test_no_op_when_no_session_captured(self):
        with patch.object(server, "_captured_session", {}):
            message = server.PublishMessageUseCase(server.store).execute("kitchen", "session-a", "hi")
            subscription = Subscription(room="kitchen")
            asyncio.run(server._send_channel_notification(subscription, message))


if __name__ == "__main__":
    unittest.main()
