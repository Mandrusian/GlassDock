# TEST FILE — safe to delete; does not affect originals
"""Regression tests for the standalone GlassDock extension prototypes."""

import json
import math
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from badges_hotkeys_test import badge_accessible_label, badge_text, parse_binding
from dock_features_test import AnalogClock, CalendarWidget, DigitalClock, MusicWidget
from dock_folders_test import FolderStore, children_for, fan_positions, folder_item
from plugin_manager_test import PLUGIN_TEMPLATE, PluginManager, StatsAPI, write_template
from reorder_test import reorder, spring_step
from settings_test import schema, validate


class BadgeAndHotkeyTests(unittest.TestCase):
    def test_badge_empty_normal_and_capped(self):
        self.assertEqual(badge_text(0), "")
        self.assertEqual(badge_text(-5), "")
        self.assertEqual(badge_text("7"), "7")
        self.assertEqual(badge_text(100), "99+")
        self.assertEqual(badge_text(20, 20), "20")

    def test_badge_rejects_invalid_limits_and_counts(self):
        for value in (True, 1.5, "many"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                badge_text(value)
        for value in (0, -1, True, 1.5):
            with self.subTest(max_count=value), self.assertRaises(ValueError):
                badge_text(2, value)

    def test_accessible_labels(self):
        self.assertEqual(badge_accessible_label(" Browser ", 0), "Browser")
        self.assertEqual(badge_accessible_label("Browser", 3), "Browser, 3 notifications")
        with self.assertRaises(ValueError):
            badge_accessible_label("  ", 1)

    def test_keybinding_is_normalized(self):
        self.assertEqual(
            parse_binding("Super+Shift+D"),
            {"modifiers": ["Shift", "Super"], "key": "D"},
        )
        self.assertEqual(parse_binding("Ctrl+F12")["key"], "F12")
        self.assertEqual(parse_binding("Alt+Space")["key"], "Space")

    def test_invalid_keybindings_are_rejected(self):
        invalid = (
            "D", "Super+", "+D", "Super++D", "Hyper+D", "Super+Super+D",
            "Super+F13", "Super+Button1", "Super+ D", "Super+Shift+Escape+Extra", "",
        )
        for binding in invalid:
            with self.subTest(binding=binding), self.assertRaises(ValueError):
                parse_binding(binding)


class ClockAndCalendarTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 23, 13, 5, 9, 500_000, tzinfo=timezone.utc)

    def test_analog_clock_hands_and_geometry(self):
        result = AnalogClock(show_seconds=True).render(self.now, size=80)
        self.assertEqual([hand["name"] for hand in result["hands"]], ["hour", "minute", "second"])
        self.assertEqual(result["center"], (40.0, 40.0))
        self.assertAlmostEqual(result["radius"], 31.2)
        self.assertTrue(all(math.isfinite(hand["angle_radians"]) for hand in result["hands"]))

    def test_analog_clock_honours_sweep_option(self):
        sweeping = AnalogClock(True, True).render(self.now)
        stepped = AnalogClock(True, False).render(self.now)
        self.assertNotEqual(sweeping["hands"][-1]["angle_radians"], stepped["hands"][-1]["angle_radians"])
        self.assertEqual(len(AnalogClock(False).render(self.now)["hands"]), 2)

    def test_clock_rejects_invalid_sizes_and_options(self):
        for size in (0, -1, float("nan"), float("inf"), True, "64"):
            with self.subTest(size=size), self.assertRaises(ValueError):
                AnalogClock().render(self.now, size)
        with self.assertRaises(TypeError):
            AnalogClock().render("not a datetime")
        with self.assertRaises(ValueError):
            AnalogClock(show_seconds=1)

    def test_digital_clock_seconds_and_accessible_label(self):
        view = DigitalClock("%H:%M", True).render(self.now)
        self.assertEqual(view["text"], "13:05:09")
        self.assertEqual(view["accessible_label"], "Friday, 23 October 2026, 13:05:09")
        self.assertEqual(DigitalClock("%S", True).render(self.now)["text"], "09")
        self.assertEqual(DigitalClock().render(self.now)["text"], "13:05")

    def test_digital_clock_rejects_invalid_format(self):
        for fmt in ("", None, 12):
            with self.subTest(fmt=fmt), self.assertRaises(ValueError):
                DigitalClock(fmt)
        with self.assertRaises(ValueError):
            DigitalClock(show_seconds="yes")

    def test_calendar_headers_month_grid_and_toggle(self):
        widget = CalendarWidget(first_weekday=6)
        first = widget.render(2026, 10)
        self.assertEqual(first["weekday_headers"][0], "Sun")
        self.assertTrue(all(len(week) == 7 for week in first["weeks"]))
        self.assertEqual(first["accessible_label"], "October 2026")
        self.assertFalse(first["expanded"])
        self.assertTrue(widget.on_click()["expanded"])
        self.assertTrue(widget.render(2026, 10)["expanded"])
        self.assertFalse(widget.on_click()["expanded"])

    def test_calendar_validates_weekday_year_and_month(self):
        for weekday in (-1, 7, True, "Monday"):
            with self.subTest(weekday=weekday), self.assertRaises(ValueError):
                CalendarWidget(weekday)
        widget = CalendarWidget()
        for year, month in ((0, 1), (10000, 1), (True, 1), (2026, 0), (2026, 13), (2026, False)):
            with self.subTest(year=year, month=month), self.assertRaises(ValueError):
                widget.render(year, month)


class MusicWidgetTests(unittest.TestCase):
    def test_render_does_not_launch_a_process(self):
        with patch("dock_features_test.subprocess.run") as run:
            widget = MusicWidget()
            self.assertEqual(widget.render()["title"], "Nothing playing")
            widget.on_hover(True)
            self.assertTrue(widget.render()["controls_visible"])
            run.assert_not_called()

    def test_refresh_loads_metadata_and_throttles(self):
        responses = [
            subprocess.CompletedProcess([], 0, "Playing\n", ""),
            subprocess.CompletedProcess([], 0, "Artist — Song\n", ""),
            subprocess.CompletedProcess([], 0, "Playing\n", ""),
            subprocess.CompletedProcess([], 0, "Artist — Song\n", ""),
        ]
        with patch("dock_features_test.subprocess.run", side_effect=responses) as run:
            widget = MusicWidget(refresh_interval=2)
            view = widget.refresh(now=10)
            self.assertEqual(view["status"], "Playing")
            self.assertEqual(view["title"], "Artist — Song")
            widget.refresh(now=11)
            self.assertEqual(run.call_count, 2)
            widget.refresh(now=12, force=True)
            self.assertEqual(run.call_count, 4)

    def test_successful_action_is_detected_without_stdout(self):
        completed = subprocess.CompletedProcess([], 0, "", "")
        with patch("dock_features_test.subprocess.run", return_value=completed):
            result = MusicWidget().on_click("next")
        self.assertEqual(result, {"action": "next", "dispatched": True})

    def test_failed_action_and_invalid_action(self):
        completed = subprocess.CompletedProcess([], 1, "", "no player")
        with patch("dock_features_test.subprocess.run", return_value=completed):
            self.assertFalse(MusicWidget().on_click()["dispatched"])
        with self.assertRaises(ValueError):
            MusicWidget().on_click("stop")

    def test_missing_program_and_timeout_are_isolated(self):
        with patch("dock_features_test.subprocess.run", side_effect=FileNotFoundError):
            self.assertFalse(MusicWidget().on_click()["dispatched"])
        with patch("dock_features_test.subprocess.run", side_effect=subprocess.TimeoutExpired("playerctl", 1)):
            self.assertFalse(MusicWidget().refresh(force=True, now=1)["status"] == "Playing")

    def test_invalid_music_widget_configuration(self):
        for kwargs in ({"playerctl": ""}, {"timeout": 0}, {"refresh_interval": float("nan")}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                MusicWidget(**kwargs)


class FolderTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.folder = self.root / "Folder"
        self.folder.mkdir()
        (self.folder / "z-file.txt").write_text("z", encoding="utf-8")
        (self.folder / "A-folder").mkdir()
        (self.folder / ".hidden").write_text("secret", encoding="utf-8")

    def tearDown(self):
        self.temporary.cleanup()

    def test_folder_item_resolves_path_and_validates_options(self):
        item = folder_item(self.folder, name=" Documents ", icon="folder-symbolic")
        self.assertEqual(item["path"], str(self.folder.resolve()))
        self.assertEqual(item["name"], "Documents")
        for kwargs in ({"name": " "}, {"icon": 2}, {"child_icon_overrides": {"file": 8}}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                folder_item(self.folder, **kwargs)
        with self.assertRaises(ValueError):
            folder_item(self.root / "missing")

    def test_children_are_sorted_hidden_filtered_and_overrides_applied(self):
        item = folder_item(
            self.folder,
            child_icon_overrides={str(self.folder / "z-file.txt"): "text-x-generic"},
        )
        children = children_for(item)
        self.assertEqual([child["name"] for child in children], ["A-folder", "z-file.txt"])
        self.assertEqual(children[-1]["icon"], "text-x-generic")
        self.assertEqual(len(children_for(item, show_hidden=True)), 3)
        with self.assertRaises(ValueError):
            children_for(item, show_hidden="yes")
        with self.assertRaises(ValueError):
            children_for({})

    def test_folder_store_writes_valid_json_with_real_newline(self):
        store = FolderStore(self.root / "config.json")
        first = store.add(self.folder, icon="folder-symbolic")
        raw = (self.root / "config.json").read_text(encoding="utf-8")
        self.assertTrue(raw.endswith("\n"))
        self.assertFalse(raw.endswith("\\n"))
        self.assertEqual(json.loads(raw)["items"], [first])
        self.assertEqual(store.load()["items"][0]["path"], str(self.folder.resolve()))

    def test_folder_store_deduplicates_and_preserves_existing_customization(self):
        store = FolderStore(self.root / "config.json")
        first = store.add(self.folder, name="Docs", icon="special-icon")
        second = store.add(self.folder, name="Ignored duplicate")
        self.assertEqual(second, first)
        self.assertEqual(len(store.load()["items"]), 1)

    def test_folder_store_rejects_corrupt_config(self):
        config = self.root / "config.json"
        config.write_text("{broken", encoding="utf-8")
        with self.assertRaises(ValueError):
            FolderStore(config).load()
        config.write_text(json.dumps({"items": "not a list"}), encoding="utf-8")
        with self.assertRaises(ValueError):
            FolderStore(config).load()
        config.write_text(json.dumps({"items": ["not an item"]}), encoding="utf-8")
        with self.assertRaises(ValueError):
            FolderStore(config).load()

    def test_fan_positions_and_animation_parameters(self):
        self.assertEqual(fan_positions(0, (0, 0)), [])
        single = fan_positions(1, (0, 0))
        self.assertAlmostEqual(single[0]["angle"], -90)
        positions = fan_positions(5, (500, 400))
        self.assertEqual([point["delay_ms"] for point in positions], [0, 28, 56, 84, 112])
        self.assertAlmostEqual(positions[2]["x"], 500)
        self.assertAlmostEqual(positions[2]["y"], 288)
        for kwargs in (
            {"count": -1}, {"count": True}, {"radius": 0}, {"angle_degrees": 20},
            {"stagger_ms": -1}, {"stiffness": 0}, {"damping": -1}, {"radius": float("nan")},
        ):
            values = {"count": 3, "origin": (0, 0), **kwargs}
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                fan_positions(**values)
        with self.assertRaises(ValueError):
            fan_positions(2, (0,))


class PluginManagerTests(unittest.TestCase):
    PLUGIN_SOURCE = '''
class P:
    def on_load(self, context): self.context = context
    def on_click(self, item=None): return {"clicked": item}
    def render(self, context=None): return {"label": "ready"}
    def on_tick(self, now): return now
    def config_schema(self): return {"enabled": {"default": True}}
PLUGIN = P()
'''

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_allowlist_required_and_plugin_contract_works(self):
        (self.directory / "sample.py").write_text(self.PLUGIN_SOURCE, encoding="utf-8")
        (self.directory / "ignored.py").write_text(self.PLUGIN_SOURCE, encoding="utf-8")
        manager = PluginManager(self.directory)
        self.assertEqual(manager.discover(), {})
        manager = PluginManager(self.directory, allowlist=["sample"])
        self.assertIn("sample", manager.discover())
        self.assertEqual(manager.call("sample", "on_click", "dock-item"), {"clicked": "dock-item"})
        self.assertEqual(manager.call("sample", "render"), {"label": "ready"})
        self.assertEqual(manager.tick(now=42), {"sample": 42.0})

    def test_invalid_allowlist_input_is_rejected(self):
        with self.assertRaises(ValueError):
            PluginManager(self.directory, allowlist="not-a-list")

    def test_invalid_plugins_are_isolated(self):
        (self.directory / "bad.py").write_text("PLUGIN = object()\n", encoding="utf-8")
        (self.directory / "good.py").write_text(self.PLUGIN_SOURCE, encoding="utf-8")
        manager = PluginManager(self.directory, allowlist=["bad", "good"])
        self.assertEqual(set(manager.discover()), {"good"})
        self.assertIn("bad", manager.errors)

    def test_disabled_plugin_is_not_loaded(self):
        (self.directory / "sample.py").write_text(self.PLUGIN_SOURCE, encoding="utf-8")
        manager = PluginManager(self.directory, allowlist=["sample"], disabled=["sample"])
        self.assertEqual(manager.discover(), {})

    def test_runtime_errors_do_not_break_other_plugins(self):
        source = self.PLUGIN_SOURCE.replace('return {"label": "ready"}', 'raise RuntimeError("render boom")')
        (self.directory / "bad.py").write_text(source, encoding="utf-8")
        (self.directory / "good.py").write_text(self.PLUGIN_SOURCE, encoding="utf-8")
        manager = PluginManager(self.directory, allowlist=["bad", "good"])
        manager.discover()
        self.assertIsNone(manager.call("bad", "render"))
        self.assertIn("bad", manager.errors)
        self.assertEqual(manager.call("good", "render"), {"label": "ready"})
        self.assertNotIn("good", manager.errors)

    def test_non_json_render_result_is_rejected(self):
        source = self.PLUGIN_SOURCE.replace('return {"label": "ready"}', "return object()")
        (self.directory / "bad.py").write_text(source, encoding="utf-8")
        manager = PluginManager(self.directory, allowlist=["bad"])
        manager.discover()
        self.assertIsNone(manager.call("bad", "render"))
        self.assertIn("bad", manager.errors)

    def test_stats_api(self):
        stats = StatsAPI(weather_provider=lambda location: {"location": location})
        stats.record_open("browser", when=123.5)
        stats.record_open("browser", when=130)
        self.assertEqual(stats.usage_count("browser"), 2)
        self.assertEqual(stats.last_opened("browser"), 130.0)
        self.assertEqual(stats.weather("Brisbane"), {"location": "Brisbane"})
        self.assertEqual(stats.snapshot()["usage"]["browser"], 2)
        with self.assertRaises(ValueError):
            stats.record_open(" ")
        self.assertIsNone(StatsAPI(weather_provider=lambda _: 1 / 0).weather("nowhere"))

    def test_write_template_creates_parent_directory(self):
        destination = self.directory / "nested" / "plugin.py"
        write_template(destination)
        self.assertIn("def on_load(self, context):", destination.read_text(encoding="utf-8"))
        self.assertIn("{{PLUGIN_NAME}}", PLUGIN_TEMPLATE)


class ReorderAndSettingsTests(unittest.TestCase):
    def test_reorder_before_target_is_stable(self):
        items = [{"key": "a"}, {"key": "b"}, {"key": "c"}]
        self.assertEqual([item["key"] for item in reorder(items, "a", "c")], ["b", "a", "c"])
        self.assertEqual([item["key"] for item in reorder(items, "c", "a")], ["c", "a", "b"])
        self.assertEqual([item["key"] for item in items], ["a", "b", "c"])

    def test_reorder_rejects_duplicate_or_unknown_keys(self):
        with self.assertRaises(ValueError):
            reorder([{"key": "a"}, {"key": "a"}], "a", "a")
        with self.assertRaises(KeyError):
            reorder([{"key": "a"}], "missing", "a")
        with self.assertRaises(ValueError):
            reorder([{"value": "missing key"}], "a", "a")

    def test_spring_step_and_validation(self):
        position, velocity = spring_step(0, 1, 0)
        self.assertGreater(position, 0)
        self.assertGreater(velocity, 0)
        for kwargs in (
            {"dt": 0}, {"dt": 0.101}, {"stiffness": 0}, {"damping": -1},
            {"current": float("nan")}, {"velocity": float("inf")},
        ):
            arguments = {"current": 0, "target": 1, "velocity": 0}
            arguments.update(kwargs)
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                spring_step(**arguments)

    def test_schema_returns_fresh_defaults_and_nested_values_merge(self):
        original = schema()
        original["folders"]["spring"]["stiffness"] = 999
        self.assertEqual(schema()["folders"]["spring"]["stiffness"], 220)
        actual = validate({"folders": {"spring": {"damping": 17}}, "unknown_app_key": True})
        self.assertEqual(actual["folders"]["spring"], {"stiffness": 220, "damping": 17})
        self.assertNotIn("unknown_app_key", actual)

    def test_schema_rejects_out_of_range_or_wrongly_typed_values(self):
        invalid = (
            {"folders": {"fan_angle_degrees": 20}},
            {"folders": {"radius": 1}},
            {"folders": {"radius": True}},
            {"folders": {"spring": {"stiffness": 0}}},
            {"plugins": {"tick_interval_ms": 49}},
            {"widgets": {"calendar": {"first_weekday": 7}},
            {"widgets": {"enabled": ["unknown"]}},
            {"extras": {"hotkeys": {"bindings": {"toggle": "Hyper+D"}}}},
            {"extras": {"badges": {"max_count": 0}},
            {"widgets": "not an object"},
        )
        for config in invalid:
            with self.subTest(config=config), self.assertRaises((TypeError, ValueError)):
                validate(config)

    def test_schema_accepts_individual_nested_overrides(self):
        actual = validate({
            "widgets": {"analog_clock": {"show_seconds": True}},
            "plugins": {"allowlist": ["clock"], "disabled": ["weather"]},
            "extras": {"reorder": {"physics": "linear"}},
        })
        self.assertTrue(actual["widgets"]["analog_clock"]["show_seconds"])
        self.assertEqual(actual["widgets"]["analog_clock"]["format"], "12h")
        self.assertEqual(actual["plugins"]["allowlist"], ["clock"])
        self.assertEqual(actual["extras"]["reorder"]["physics"], "linear")


if __name__ == "__main__":
    unittest.main(verbosity=2)
