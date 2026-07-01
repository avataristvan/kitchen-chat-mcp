import os
import unittest

from kitchen_chat_mcp.infrastructure.RoomAllowlist import RoomAccessDenied, RoomAllowlist


class TestRoomAllowlist(unittest.TestCase):
    ENV_VAR = "ROOMS"

    def setUp(self):
        self._original_value = os.environ.get(self.ENV_VAR)

    def tearDown(self):
        if self._original_value is None:
            os.environ.pop(self.ENV_VAR, None)
        else:
            os.environ[self.ENV_VAR] = self._original_value

    def test_unset_env_var_allows_any_room(self):
        os.environ.pop(self.ENV_VAR, None)
        allowlist = RoomAllowlist(self.ENV_VAR)

        allowlist.ensure_allowed("kitchen")
        allowlist.ensure_allowed("anything")

    def test_empty_env_var_allows_any_room(self):
        os.environ[self.ENV_VAR] = ""
        allowlist = RoomAllowlist(self.ENV_VAR)

        allowlist.ensure_allowed("kitchen")

    def test_configured_rooms_are_allowed_others_denied(self):
        os.environ[self.ENV_VAR] = "film,security-camera"
        allowlist = RoomAllowlist(self.ENV_VAR)

        allowlist.ensure_allowed("film")
        allowlist.ensure_allowed("security-camera")
        with self.assertRaises(RoomAccessDenied):
            allowlist.ensure_allowed("other")

    def test_whitespace_around_entries_is_stripped(self):
        os.environ[self.ENV_VAR] = "film, security-camera "
        allowlist = RoomAllowlist(self.ENV_VAR)

        allowlist.ensure_allowed("film")
        allowlist.ensure_allowed("security-camera")
        with self.assertRaises(RoomAccessDenied):
            allowlist.ensure_allowed("other")


if __name__ == "__main__":
    unittest.main()
