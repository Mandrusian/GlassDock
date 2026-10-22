import json
import os
import tempfile
import unittest

from moderndock.core import config as C
from moderndock.core.colors import normalize_color, parse_color, is_valid_color
from moderndock.core.themes import THEMES, CUSTOM


class ColorTests(unittest.TestCase):
    def test_parse_forms(self):
        self.assertEqual(parse_color("#fff"), (1.0, 1.0, 1.0, 1.0))
        self.assertAlmostEqual(parse_color("#00000080")[3], 128 / 255)
        self.assertEqual(parse_color("rgb(255, 0, 0)"), (1.0, 0.0, 0.0, 1.0))
        self.assertEqual(parse_color("rgba(0,0,0,0.5)")[3], 0.5)
        self.assertEqual(normalize_color("#ABC"), "#aabbcc")

    def test_invalid(self):
        for bad in ("", "red!", "#12", "rgb(1,2)", 5, None):
            self.assertFalse(is_valid_color(bad), bad)


class ConfigTests(unittest.TestCase):
    def test_defaults_are_valid_and_stable(self):
        d = C.default_config()
        self.assertEqual(C.validate(d), d)

    def test_every_setting_default_coerces(self):
        for s in C.SCHEMA:
            self.assertEqual(C.coerce(s, s.default), s.default, s.key)

    def test_clamping_and_fallback(self):
        cfg = C.default_config()
        C.set_path(cfg, "size.icon_size", 9999)
        C.set_path(cfg, "appearance.bg_opacity", -3)
        C.set_path(cfg, "position.edge", "diagonal")
        C.set_path(cfg, "appearance.bg_color", "not a color")
        C.set_path(cfg, "animation.magnify", "off")
        v = C.validate(cfg)
        self.assertEqual(C.get_path(v, "size.icon_size"), 128)
        self.assertEqual(C.get_path(v, "appearance.bg_opacity"), 0.0)
        self.assertEqual(C.get_path(v, "position.edge"), "bottom")
        self.assertEqual(C.get_path(v, "appearance.bg_color"), C.default_value("appearance.bg_color"))
        self.assertIs(C.get_path(v, "animation.magnify"), False)

    def test_nan_rejected(self):
        with self.assertRaises(ValueError):
            C.coerce(C.SETTINGS["size.icon_size"], float("nan"))

    def test_items_validation(self):
        items = [
            {"type": "app", "id": "a.desktop"}, {"type": "app", "id": "a.desktop"},
            {"type": "app"}, {"type": "launcher", "name": "X", "exec": "x --y"},
            {"type": "launcher", "name": "", "exec": "x"}, {"type": "separator"},
            {"type": "special", "kind": "trash"}, {"type": "special", "kind": "bogus"}, "junk",
        ]
        out = C.validate_items(items)
        self.assertEqual([i["type"] for i in out], ["app", "launcher", "separator", "special"])

    def test_migration_v0(self):
        old = {"icon_size": 64, "edge": "left", "autohide": True, "pinned": ["firefox.desktop"]}
        v = C.validate(C.migrate(old))
        self.assertEqual(C.get_path(v, "size.icon_size"), 64)
        self.assertEqual(C.get_path(v, "position.edge"), "left")
        self.assertEqual(C.get_path(v, "behavior.autohide"), "always")
        self.assertEqual(v["items"], [{"type": "app", "id": "firefox.desktop"}])
        self.assertEqual(v["version"], C.CONFIG_VERSION)

    def test_migration_v1_autohide_bool(self):
        v = C.validate(C.migrate({"version": 1, "behavior": {"autohide": False}}))
        self.assertEqual(C.get_path(v, "behavior.autohide"), "off")

    def test_save_load_roundtrip_and_corrupt(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "sub", "config.json")
            cfg = C.default_config()
            C.set_path(cfg, "size.spacing", 14)
            C.save_config(cfg, p)
            self.assertEqual(C.get_path(C.load_config(p), "size.spacing"), 14)
            with open(p, "w") as fh:
                fh.write("{ not json")
            self.assertEqual(C.load_config(p), C.default_config())
            self.assertTrue(any(f.startswith("config.json.corrupt-") for f in os.listdir(os.path.dirname(p))))

    def test_monitor_overrides(self):
        cfg = C.default_config()
        cfg["monitors"] = C.validate_monitors({"DP-1": {"position.edge": "left", "enabled": False,
                                                        "size.icon_size": 9000, "bogus": 1}})
        self.assertEqual(cfg["monitors"]["DP-1"]["size.icon_size"], 128)
        self.assertNotIn("bogus", cfg["monitors"]["DP-1"])
        eff = C.effective(cfg, "DP-1")
        self.assertEqual(C.get_path(eff, "position.edge"), "left")
        self.assertEqual(C.get_path(cfg, "position.edge"), "bottom")
        self.assertFalse(C.monitor_enabled(cfg, "DP-1"))
        self.assertTrue(C.monitor_enabled(cfg, "eDP-1"))

    def test_default_items_use_installed_apps(self):
        class E:  # entries only need membership
            pass
        entries = {"firefox.desktop": E(), "foot.desktop": E()}
        items = C.default_items(entries)
        ids = [i.get("id") for i in items if i["type"] == "app"]
        self.assertEqual(ids, ["firefox.desktop", "foot.desktop"])
        self.assertEqual(items[0], {"type": "special", "kind": "apps"})

    def test_schema_depends_reference_real_keys(self):
        for s in C.SCHEMA:
            if s.depends:
                self.assertIn(s.depends[0], C.SETTINGS)

    def test_choice_defaults_and_ranges(self):
        for s in C.SCHEMA:
            if s.type == "choice":
                self.assertIn(s.default, [c[0] for c in s.choices])
            if s.type in ("int", "float"):
                self.assertLessEqual(s.min, s.default)
                self.assertGreaterEqual(s.max, s.default)


class ThemeTests(unittest.TestCase):
    def test_theme_values_are_valid_schema_values(self):
        for name, t in THEMES.items():
            for key, val in t["values"].items():
                self.assertIn(key, C.SETTINGS, (name, key))
                self.assertEqual(C.coerce(C.SETTINGS[key], val), val if C.SETTINGS[key].type != "color" else val.lower(), (name, key))

    def test_all_themes_set_same_keys(self):
        keysets = {frozenset(t["values"]) for t in THEMES.values()}
        self.assertEqual(len(keysets), 1)

    def test_apply_and_match(self):
        cfg = C.default_config()
        for name in THEMES:
            C.apply_theme(cfg, name)
            self.assertEqual(cfg["theme"], name)
            self.assertTrue(C.matches_theme(cfg, name))
        C.apply_theme(cfg, CUSTOM)
        self.assertEqual(cfg["theme"], CUSTOM)

    def test_default_theme_matches_schema_defaults(self):
        self.assertTrue(C.matches_theme(C.default_config(), "smoky-glass"))


if __name__ == "__main__":
    unittest.main()
