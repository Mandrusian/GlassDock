"""Regression tests for the advanced extensions in the normal GlassDock app."""
import json
import os
import tempfile
import unittest
from pathlib import Path

from glassdock import fan_math as F
from glassdock import extras_store as X
from glassdock import plugin_api as P
from glassdock.stats import Stats


class ExtrasStoreTests(unittest.TestCase):
    def test_round_trip_is_atomic_and_normalized(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "extensions.json")
            data = {
                "extras": [
                    {"id": "clock1", "type": "analog_clock", "at": 2},
                    {"id": "../bad", "type": "analog_clock", "at": 0},
                    {"id": "clock1", "type": "music", "at": 0},
                    {"id": "unknown", "type": "shell", "at": 0},
                ],
                "icon_overrides": {"apps": "/tmp/apps.png", "not-allowed": "/tmp/no.png"},
                "widgets": {"clock1": {"seconds": False, "unknown": "ignored"}},
            }
            data["widgets"]["clock1"]["bad_float"] = float("nan")
            data["plugins"] = {"sample": {"enabled": False, "config": {"bad_float": float("inf"), "safe": "ok"}}}
            X.save(data, path)
            saved = json.loads(Path(path).read_text(encoding="utf-8"))
            loaded = X.load(path)
            self.assertEqual(len(saved["extras"]), 1)
            self.assertEqual(loaded["extras"][0], {"id": "clock1", "type": "analog_clock", "at": 2})
            self.assertEqual(loaded["icon_overrides"], {"apps": "/tmp/apps.png"})
            cfg = X.widget_cfg(loaded, "clock1", "analog_clock")
            self.assertIs(cfg["seconds"], False)
            self.assertNotIn("unknown", cfg)
            self.assertNotIn("bad_float", loaded["widgets"]["clock1"])
            self.assertEqual(loaded["plugins"]["sample"]["config"], {"safe": "ok"})
            self.assertEqual(sorted(os.listdir(td)), ["extensions.json"])

    def test_invalid_or_non_object_config_falls_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "extensions.json")
            Path(path).write_text("[]", encoding="utf-8")
            self.assertEqual(X.load(path), X.DEFAULTS)
            Path(path).write_text("not json", encoding="utf-8")
            self.assertEqual(X.load(path), X.DEFAULTS)

    def test_folder_config_validates_paths_and_bounds(self):
        raw = {
            "folders": {
                "folder1": {
                    "name": "  Docs  ", "path": "/tmp/docs", "spread": 900,
                    "radius": -1, "apps": ["firefox.desktop", 7],
                    "files": ["/tmp/a", None], "child_icons": {"x": "/tmp/x.png", 1: "bad"},
                }
            }
        }
        normalized = X._normalize(raw)
        folder = X.folder_cfg(normalized, "folder1")
        self.assertEqual(folder["name"], "Docs")
        self.assertEqual(folder["spread"], 160)
        self.assertEqual(folder["radius"], 0)
        self.assertEqual(folder["apps"], ["firefox.desktop"])
        self.assertEqual(folder["files"], ["/tmp/a"])
        self.assertEqual(folder["child_icons"], {"x": "/tmp/x.png"})


class FanMathTests(unittest.TestCase):
    def test_layout_is_finite_and_symmetric(self):
        layout = F.fan_layout(5, 48, spread_deg=100)
        self.assertEqual(len(layout), 5)
        self.assertAlmostEqual(layout[0][1], -layout[-1][1])
        self.assertAlmostEqual(layout[0][0], layout[-1][0])
        self.assertTrue(all(all(map(lambda n: isinstance(n, (int, float)) and abs(n) < 1e7, row))
                            for row in layout))

    def test_bad_parameters_are_rejected(self):
        for args in ((-1, 48), (15, 48), (1, float("nan")), (1, 48, 181), (1, 48, 90, -1)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                F.fan_layout(*args)
        with self.assertRaises(ValueError):
            F.FanAnimator(1).step(float("nan"))

    def test_animator_converges_and_clamps_large_steps(self):
        animator = F.FanAnimator(3)
        done = False
        for _ in range(600):
            done = animator.step(1.0)
            if done:
                break
        self.assertTrue(done)
        self.assertTrue(all(abs(p - 1.0) < 0.01 for p in animator.p))


class PluginDiscoveryTests(unittest.TestCase):
    def test_discovery_never_imports_modules_that_are_not_allowlisted(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            marker = root / "imported.txt"
            (root / "silent.py").write_text(
                "from pathlib import Path\nPath(%r).write_text('imported')\n" % str(marker),
                encoding="utf-8",
            )
            self.assertEqual(P.discover([td], allowlist=[]), ({}, {}))
            self.assertFalse(marker.exists())

    def test_allowlisted_plugin_loads_and_invalid_schema_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "good.py").write_text(
                "from glassdock.plugin_api import PluginBase\n"
                "class Good(PluginBase):\n"
                "    NAME = 'Good'\n"
                "    TICK = 0\n"
                "PLUGIN_SENTINEL = True\n",
                encoding="utf-8",
            )
            (root / "bad.py").write_text(
                "from glassdock.plugin_api import PluginBase\n"
                "class Bad(PluginBase):\n"
                "    CONFIG = {'x': {'type': 'choice', 'default': 'a', 'choices': []}}\n",
                encoding="utf-8",
            )
            classes, errors = P.discover([td], allowlist=["good", "bad"])
            self.assertIn("good", classes)
            self.assertEqual(classes["good"].TICK, 0)
            self.assertNotIn("bad", classes)
            self.assertIn("bad", errors)

    def test_plugin_names_are_validated(self):
        for invalid in ("../outside", "two-words", "", "9start"):
            with self.subTest(name=invalid), self.assertRaises(ValueError):
                P.discover([], allowlist=[invalid])


class StatsPersistenceTests(unittest.TestCase):
    def test_usage_counts_survive_restart(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "usage.json")
            stats = Stats(path)
            stats.record_launch("org.example.App")
            stats.record_launch("org.example.App")
            stats.record_launch("org.example.Other")
            loaded = Stats(path)
            self.assertEqual(loaded.usage("org.example.App")["count"], 2)
            self.assertEqual(loaded.usage_top(1)[0][0], "org.example.App")
            self.assertEqual(sorted(os.listdir(td)), ["usage.json"])

    def test_malformed_usage_store_is_ignored(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "usage.json")
            Path(path).write_text('{"bad":{"count":NaN,"last_opened":Infinity}}', encoding="utf-8")
            self.assertEqual(Stats(path).usage_top(), [])


class PackagingIntegrationTests(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1]

    def test_normal_launcher_runs_integrated_dock(self):
        source = (self.ROOT / "bin" / "glassdock").read_text(encoding="utf-8")
        self.assertIn("python3 -m glassdock.dock_extensions", source)
        self.assertNotIn('python3 -m glassdock.dock "$@"', source)

    def test_plugins_do_not_reference_test_module_names(self):
        for path in (self.ROOT / "plugins").glob("*.py"):
            with self.subTest(plugin=path.name):
                source = path.read_text(encoding="utf-8")
                self.assertNotIn("_test import", source)
                self.assertIn("from glassdock.plugin_api import PluginBase", source)

    def test_badge_dbus_subscription_is_released(self):
        source = (self.ROOT / "glassdock" / "badges.py").read_text(encoding="utf-8")
        self.assertIn("self.subscription_id = subscription", source)
        self.assertIn("self.bus.signal_unsubscribe(self.subscription_id)", source)
        self.assertIn("self.badges.close()", (self.ROOT / "glassdock" / "dock_extensions.py").read_text(encoding="utf-8"))

    def test_advanced_settings_are_embedded_in_launchers(self):
        source = (self.ROOT / "glassdock" / "settings.py").read_text(encoding="utf-8")
        self.assertIn("ExtensionsPanel()", source)
        self.assertIn("Advanced widgets, fan folders, icon overrides and plugins", source)
        self.assertNotIn("Extras (test)", source)


if __name__ == "__main__":
    unittest.main()
