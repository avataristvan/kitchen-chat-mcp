import os
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from kitchen_chat_mcp.infrastructure.RoomAllowlist import RoomAllowlist
from kitchen_chat_mcp.infrastructure.SqliteMessageStore import SqliteMessageStore
from kitchen_chat_mcp.ui import server


class KitchenChatIntegrationTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        db_path = os.path.join(self._tmp_dir.name, "test-kitchen-chat.db")
        self._store_patcher = patch.object(server, "store", SqliteMessageStore(db_path))
        self._allowlist_patcher = patch.object(server, "allowlist", RoomAllowlist())
        self._store_patcher.start()
        self._allowlist_patcher.start()

    def tearDown(self):
        self._store_patcher.stop()
        self._allowlist_patcher.stop()
        self._tmp_dir.cleanup()


class TestPublishAndPoll(KitchenChatIntegrationTestCase):
    def test_publish_then_poll_returns_both_messages(self):
        first = server.publish("kitchen", "session-a", "Script finalisiert")
        second = server.publish("kitchen", "session-b", "Hero-Take: ~7s")
        self.assertEqual(first["status"], "ok")
        self.assertEqual(second["status"], "ok")

        result = server.poll("kitchen")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(result["messages"]), 2)
        self.assertEqual(result["messages"][0]["id"], first["message_id"])
        self.assertEqual(result["messages"][1]["id"], second["message_id"])
        self.assertEqual(result["messages"][0]["content"], "Script finalisiert")


class TestPresence(KitchenChatIntegrationTestCase):
    def test_poll_excludes_presence_by_default_but_can_include_it(self):
        broadcast = server.publish("kitchen", "session-a", "Script finalisiert")
        ping = server.presence("kitchen", "session-b", "still here, nothing new")
        self.assertEqual(ping["status"], "ok")

        default_result = server.poll("kitchen")
        self.assertEqual([msg["id"] for msg in default_result["messages"]], [broadcast["message_id"]])

        with_presence = server.poll("kitchen", include_presence=True)
        self.assertEqual(
            [msg["id"] for msg in with_presence["messages"]],
            [broadcast["message_id"], ping["message_id"]],
        )
        self.assertEqual(with_presence["messages"][1]["kind"], "presence")


class TestAskAnswerRoundTrip(KitchenChatIntegrationTestCase):
    def test_ask_is_answered_by_another_session(self):
        ask_result = {}

        def ask_in_background():
            ask_result["value"] = server.ask("kitchen", "session-a", "Brauchen wir OCR-Nachdreh?", timeout_seconds=5.0)

        thread = threading.Thread(target=ask_in_background)
        thread.start()

        time.sleep(0.1)
        polled = server.poll("kitchen")
        question = next(msg for msg in polled["messages"] if msg["kind"] == "question")

        answer_result = server.answer("kitchen", "session-b", question["id"], "Nein, Take 2 ist sauber")
        thread.join()

        self.assertEqual(answer_result["status"], "ok")
        self.assertEqual(
            ask_result["value"],
            {"status": "answered", "content": "Nein, Take 2 ist sauber", "sender_session_id": "session-b"},
        )


class TestAskTimeout(KitchenChatIntegrationTestCase):
    def test_ask_times_out_when_unanswered(self):
        result = server.ask("kitchen", "session-a", "Brauchen wir OCR-Nachdreh?", timeout_seconds=0.3)
        self.assertEqual(result, {"status": "timeout", "question": "Brauchen wir OCR-Nachdreh?"})


class TestRoomAllowlistDenial(KitchenChatIntegrationTestCase):
    def test_publish_to_room_outside_allowlist_is_denied(self):
        previous_rooms = os.environ.get("ROOMS")
        os.environ["ROOMS"] = "kitchen"
        try:
            with patch.object(server, "allowlist", RoomAllowlist()):
                result = server.publish("garage", "session-a", "Motor läuft nicht")
        finally:
            if previous_rooms is None:
                os.environ.pop("ROOMS", None)
            else:
                os.environ["ROOMS"] = previous_rooms

        self.assertEqual(result["status"], "denied")


if __name__ == "__main__":
    unittest.main()
