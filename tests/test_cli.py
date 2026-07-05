import unittest

from kitchen_chat_mcp.ui.cli import ChatScreen


class TestResolveFullId(unittest.TestCase):
    def setUp(self):
        self.screen = ChatScreen.__new__(ChatScreen)
        self.screen.known_ids = ["abc12345-full", "abc99999-full", "zzz00000-full"]

    def test_unique_prefix_resolves_to_full_id(self):
        self.assertEqual(self.screen._resolve_full_id("zzz0"), "zzz00000-full")
        self.assertEqual(self.screen._resolve_full_id("abc1"), "abc12345-full")

    def test_ambiguous_prefix_returns_none(self):
        self.assertIsNone(self.screen._resolve_full_id("abc"))

    def test_unknown_prefix_returns_none(self):
        self.assertIsNone(self.screen._resolve_full_id("nope"))


if __name__ == "__main__":
    unittest.main()
