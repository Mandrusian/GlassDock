import contextlib
import io
import unittest
from unittest.mock import patch

from glassdock import ctl


class ControlCliTests(unittest.TestCase):
    def test_badge_command_sends_index_and_count(self):
        with patch("glassdock.ctl.control.send_command", return_value={"ok": True}) as send:
            self.assertEqual(ctl.main(["badge", "3", "9"]), 0)
        send.assert_called_once_with({"cmd": "badge", "index": "3", "count": "9"})

    def test_badge_command_requires_two_arguments(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            self.assertEqual(ctl.main(["badge", "3"]), 2)
        self.assertIn("badge needs an item index", stderr.getvalue())

    def test_unknown_or_unavailable_commands_fail_cleanly(self):
        with patch("glassdock.ctl.control.send_command", return_value=None):
            self.assertEqual(ctl.main(["toggle"]), 1)


if __name__ == "__main__":
    unittest.main()
