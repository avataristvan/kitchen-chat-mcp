import os
import tempfile
import unittest
from unittest import mock

from kitchen_chat_mcp.infrastructure.DbConfig import DEFAULT_DB_PATH, resolve_db_path


class TestResolveDbPath(unittest.TestCase):
    def test_returns_default_path_when_env_var_unset(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("KITCHEN_CHAT_DB", None)
            self.assertEqual(resolve_db_path(), DEFAULT_DB_PATH)

    def test_env_var_override_is_used_and_its_parent_dir_is_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "nested", "custom.db")
            with mock.patch.dict(os.environ, {"KITCHEN_CHAT_DB": db_path}):
                self.assertEqual(resolve_db_path(), db_path)
                self.assertTrue(os.path.isdir(os.path.dirname(db_path)))

    def test_bare_filename_override_does_not_raise(self):
        with mock.patch.dict(os.environ, {"KITCHEN_CHAT_DB": "relative.db"}):
            self.assertEqual(resolve_db_path(), "relative.db")


if __name__ == "__main__":
    unittest.main()
