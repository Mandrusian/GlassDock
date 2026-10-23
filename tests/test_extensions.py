"""Regression tests for built-in widgets, badges, folders, media, and plugins."""
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from glassdock.core import extensions as E


class BadgeAndHotkeyTests(unittest.TestCase):
    def test_badge_text_clamps_and_formats(self):
        self.assertEqual(E.badge_text(0), "")
        self.assertEqual(E.badge_text(-1), "")
        self.assertEqual(E.badge_text(7), "7")
        self.assertEqual(E.badge_text(100, 99), "99+")
        with self.assertRaises(ValueError):
            E.badge_text(True)
        with self.assertRaises(ValueError):
            E.badge_text(4, 0)

    def test_hotkey_validation(self):
        self.assertEqual(E.parse_hotkey("Super+Shift+D"), {"modifiers": ["Shift", "Super"], "key": "D"})
        self.assertEqual(E.parse_hotkey("Ctrl+F12")["key"], "F12")
        for bad in ("D", "Super+", "Hyper+D", "Super+Super+D", "Super+F13", "Super+ Button"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                E.parse_hotkey(bad)


class WidgetDataTests(unittest.TestCase):
    def test_clock_formats(self):
        now = datetime(2026, 10, 23, 13, 5, 9, tzinfo=timezone.utc)
        self.assertEqual(E.clock_text(now, "24h"), "13:05")
        self.assertEqual(E.clock_text(now, "24h", True), "13:05:09")
        self.assertEqual(E.clock_text(now, "12h"), "1:05")
        self.assertEqual(E.clock_text(now, "12h", True), "1:05:09")
        with self.assertRaises(ValueError):
            E.clock_text(now, "invalid")

    def test_calendar_month_weeks_and_sunday_start(self):
        monday = E.calendar_month(2026, 10, 0)
        sunday = E.calendar_month(2026, 10, 6)
        self.assertEqual(monday["month_name"], "October")
        self.assertEqual(monday["headers"][0], "Mon")
        self.assertEqual(sunday["headers"][0], "Sun")
        self.assertTrue(all(len(week) == 7 for week in sunday["weeks"]))
        with self.assertRaises(ValueError):
            E.calendar_month(2026, 13, 0)
        with self.assertRaises(ValueError):
            E.calendar_month(2026, 10, 2)

    def test_folder_listing_filters_hidden_and_sorts_directories_first(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "z-file").write_text("x", encoding="utf-8")
            (root / "a-dir").mkdir()
            (root / ".hidden").write_text("x", encoding="utf-8")
            visible = E.folder_children(root)
            self.assertEqual([item["name"] for item in visible], ["a-dir", "z-file"])
            self.assertEqual(len(E.folder_children(root, True)), 3)
            with self.assertRaises(ValueError):
                E.folder_children(root, "yes")
            with self.assertRaises(ValueError):
                E.folder_children(root / "missing")

    def test_fan_positions_are_finite_and_ordered(self):
        self.assertEqual(E.fan_positions(0, (0, 0)), [])
        self.assertAlmostEqual(E.fan_positions(1, (0, 0))[0]["angle"], -90)
        points = E.fan_positions(3, (100, 200))
        self.assertEqual(len(points), 3)
        self.assertAlmostEqual(points[1]["x"], 100)
        self.assertAlmostEqual(points[1]["y"], 88)
        with self.assertRaises(ValueError):
            E.fan_positions(-1, (0, 0))
        with self.assertRaises(ValueError):
            E.fan_positions(3, (0, 0), radius=float("nan"))


class MusicControllerTests(unittest.TestCase):
    def test_refresh_and_throttling(self):
        responses = [
            subprocess.CompletedProcess([], 0, "Playing\n", ""),
            subprocess.CompletedProcess([], 0, "Artist — Song\n", ""),
        ]
        with patch("glassdock.core.extensions.subprocess.run", side_effect=responses) as run:
            controller = E.MusicController()
            self.assertEqual(controller.refresh(now=10)["status"], "Playing")
            self.assertEqual(controller.snapshot()["title"], "Artist — Song")
            controller.refresh(now=11)
            self.assertEqual(run.call_count, 2)

    def test_command_success_does_not_need_stdout(self):
        with patch("glassdock.core.extensions.subprocess.run",
                   return_value=subprocess.CompletedProcess([], 0, "", "")):
            self.assertTrue(E.MusicController().command("next"))

    def test_failed_or_missing_player_is_safe(self):
        with patch("glassdock.core.extensions.subprocess.run", side_effect=FileNotFoundError):
            controller = E.MusicController()
            self.assertFalse(controller.command("play-pause"))
            self.assertEqual(controller.refresh(force=True)["status"], "Stopped")
        with self.assertRaises(ValueError):
            E.MusicController("").command("play")
        with self.assertRaises(ValueError):
            E.MusicController().command("run-shell")


class PluginManagerTests(unittest.TestCase):
    PLUGIN = '''
class Example:
    def on_load(self, context):
        self.stats = context['stats']
    def on_click(self, item=None):
        return {'action': 'toast', 'message': 'Hello'}
    def render(self, context=None):
        return {'label': 'Example widget', 'icon': 'clock'}
    def on_tick(self, now):
        self.now = now
    def config_schema(self):
        return {'enabled': {'default': True}}
PLUGIN = Example()
'''

    def test_only_allowlisted_plugin_is_loaded(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "clock.py").write_text(self.PLUGIN, encoding="utf-8")
            (root / "ignored.py").write_text(self.PLUGIN, encoding="utf-8")
            manager = E.PluginManager(root, allowlist=["clock"])
            self.assertEqual(set(manager.discover()), {"clock"})
            self.assertEqual(manager.render("clock"), {"label": "Example widget", "icon": "clock"})
            self.assertEqual(manager.click("clock"), {"action": "toast", "message": "Hello"})
            manager.tick(now=123.0)
            self.assertNotIn("ignored", manager.plugins)

    def test_bad_plugin_is_isolated_and_invalid_names_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "broken.py").write_text("PLUGIN = object()\n", encoding="utf-8")
            manager = E.PluginManager(root, allowlist=["broken"])
            self.assertEqual(manager.discover(), {})
            self.assertIn("broken", manager.errors)
        with self.assertRaises(ValueError):
            E.PluginManager("/tmp", allowlist=["../unsafe"])

    def test_stats_api_updates_usage_without_exposing_mutable_state(self):
        stats = E.StatsAPI()
        stats.record_open("firefox", when=12.5)
        self.assertEqual(stats.usage_count("firefox"), 1)
        self.assertEqual(stats.last_opened("firefox"), 12.5)
        snapshot = stats.snapshot()
        snapshot["usage"]["firefox"] = 999
        self.assertEqual(stats.usage_count("firefox"), 1)


if __name__ == "__main__":
    unittest.main()
