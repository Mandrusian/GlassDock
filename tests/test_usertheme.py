"""User themes (save / import / export) and the Settings window identity fix."""
import json
import os
import tempfile
import unittest

from glassdock.core import config as C, model as M, usertheme as UT
from glassdock.core.desktop import parse_desktop_text
from glassdock.core.sway import Window
from glassdock.core.themes import THEMES

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = tmp.name
        self.dir = os.path.join(self.tmp, "themes")
        self.cfg = C.default_config({})

    def write(self, name, obj):
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(obj if isinstance(obj, str) else json.dumps(obj))
        return path

    def theme(self, **over):
        t = {"format": "glassdock-theme", "version": 1, "name": "Test",
             "values": {"appearance.bg_color": "#112233"}}
        t.update(over)
        return t


class SaveLoadTests(Base):
    def test_save_then_list_roundtrip(self):
        C.set_path(self.cfg, "appearance.bg_color", "#112233")
        C.set_path(self.cfg, "appearance.corner_radius", 30)
        name = UT.save_theme(self.cfg, "Midnight Blue", "dark and calm", self.dir)
        self.assertEqual(name, "user:midnight-blue")
        themes, problems = UT.list_user_themes(self.dir)
        self.assertEqual(problems, [])
        info = themes[name]
        self.assertEqual((info["label"], info["description"]), ("Midnight Blue", "dark and calm"))
        self.assertEqual(info["values"]["appearance.bg_color"], "#112233")
        self.assertTrue(UT.matches(self.cfg, info))

    def test_same_name_gets_a_new_slug_instead_of_overwriting(self):
        a = UT.save_theme(self.cfg, "Midnight", "", self.dir)
        b = UT.save_theme(self.cfg, "Midnight", "", self.dir)
        self.assertEqual((a, b), ("user:midnight", "user:midnight-2"))

    def test_empty_name_is_rejected(self):
        with self.assertRaises(UT.ThemeError):
            UT.save_theme(self.cfg, "   ", "", self.dir)

    def test_saved_theme_covers_exactly_the_theme_keys(self):
        UT.save_theme(self.cfg, "X", "", self.dir)
        with open(os.path.join(self.dir, "x.json")) as fh:
            data = json.load(fh)
        self.assertEqual(sorted(data["values"]), sorted(C.THEME_KEYS))

    def test_rename_and_delete(self):
        name = UT.save_theme(self.cfg, "Old", "", self.dir)
        UT.rename_theme(name, "New name", self.dir)
        self.assertEqual(UT.list_user_themes(self.dir)[0][name]["label"], "New name")
        self.assertTrue(UT.delete_theme(name, self.dir))
        self.assertFalse(UT.delete_theme(name, self.dir))
        self.assertEqual(UT.list_user_themes(self.dir)[0], {})

    def test_only_user_names_can_be_deleted_or_renamed(self):
        for bad in ("smoky-glass", "user:../../etc/passwd", "user:", "user:A B"):
            with self.assertRaises(UT.ThemeError):
                UT.delete_theme(bad, self.dir)
            with self.assertRaises(UT.ThemeError):
                UT.rename_theme(bad, "x", self.dir)

    def test_one_bad_file_does_not_hide_the_good_ones(self):
        UT.save_theme(self.cfg, "Good", "", self.dir)
        with open(os.path.join(self.dir, "broken.json"), "w") as fh:
            fh.write("{not json")
        with open(os.path.join(self.dir, "Bad Name!.json"), "w") as fh:
            fh.write("{}")
        themes, problems = UT.list_user_themes(self.dir)
        self.assertEqual(list(themes), ["user:good"])
        self.assertEqual(len(problems), 2)

    def test_missing_folder_is_just_empty(self):
        self.assertEqual(UT.list_user_themes(os.path.join(self.tmp, "nope")), ({}, []))


class ImportExportTests(Base):
    def test_builtin_theme_roundtrips_through_a_file(self):
        src = THEMES["smoky-glass"]
        path = os.path.join(self.tmp, "out.json")
        UT.export_file(src, path)
        name, info = UT.import_file(path, self.dir)
        self.assertEqual(info["ignored"], [])
        for key, value in src["values"].items():
            self.assertEqual(info["values"][key], C.coerce(C.SETTINGS[key], value))
        self.assertTrue(UT.is_user(name))

    def test_import_ignores_everything_that_is_not_appearance(self):
        evil = self.theme(values={"appearance.bg_color": "#112233",
                                  "behavior.launcher_command": "rm -rf ~",
                                  "items": [{"type": "launcher", "name": "x", "exec": "evil"}],
                                  "theme": "custom"})
        name, info = UT.import_file(self.write("evil.json", evil), self.dir)
        self.assertEqual(sorted(info["ignored"]), ["behavior.launcher_command", "items", "theme"])
        with open(os.path.join(self.dir, name[len(UT.PREFIX):] + ".json")) as fh:
            stored = fh.read()
        self.assertNotIn("rm -rf", stored)
        self.assertNotIn("evil", stored)

    def test_bad_values_are_skipped_and_out_of_range_values_clamped(self):
        t = self.theme(values={"appearance.corner_radius": 99999, "appearance.bg_opacity": "banana",
                               "appearance.bg_color": "#112233"})
        info = UT.validate_theme(t)
        self.assertIn("appearance.bg_opacity", info["ignored"])
        self.assertEqual(info["values"]["appearance.corner_radius"],
                         C.SETTINGS["appearance.corner_radius"].max)
        self.assertEqual(info["values"]["appearance.bg_opacity"], C.default_value("appearance.bg_opacity"))

    def test_missing_keys_are_filled_from_defaults(self):
        info = UT.validate_theme(self.theme())
        self.assertEqual(sorted(info["values"]), sorted(C.THEME_KEYS))

    def test_rejections_have_friendly_messages(self):
        cases = [[], "text", self.theme(format="something-else"), self.theme(version=99),
                 self.theme(version=0), self.theme(name="  "), self.theme(values=None),
                 self.theme(values={"behavior.autohide": True}), self.theme(values={})]
        for data in cases:
            with self.assertRaises(UT.ThemeError, msg=repr(data)):
                UT.validate_theme(data)

    def test_control_characters_and_length_are_cleaned(self):
        info = UT.validate_theme(self.theme(name="Evil\x1b[31m\nName" + "x" * 200,
                                            description="a\x00b" * 500))
        self.assertNotIn("\x1b", info["label"])
        self.assertNotIn("\n", info["label"])
        self.assertLessEqual(len(info["label"]), 60)
        self.assertLessEqual(len(info["description"]), 200)

    def test_oversized_and_non_json_files_are_refused(self):
        big = self.write("big.json", "x" * (UT.MAX_BYTES + 1))
        junk = self.write("junk.json", "{nope")
        for p in (big, junk, os.path.join(self.tmp, "missing.json")):
            with self.assertRaises(UT.ThemeError):
                UT.import_file(p, self.dir)

    def test_export_unwritable_path_is_a_themeerror(self):
        with self.assertRaises(UT.ThemeError):
            UT.export_file(THEMES["dark"], "/proc/definitely/not/writable.json")


class ApplyTests(Base):
    def test_apply_values_sets_name_and_matches(self):
        info = UT.validate_theme(self.theme(values={"appearance.bg_color": "#abcdef"}))
        UT.apply_values(self.cfg, info, "user:test")
        self.assertEqual(self.cfg["theme"], "user:test")
        self.assertEqual(C.get_path(self.cfg, "appearance.bg_color"), "#abcdef")
        self.assertTrue(UT.matches(self.cfg, info))

    def test_labels(self):
        user = {"user:mine": {"label": "Mine", "description": "", "values": {}, "user": True}}
        self.assertEqual(UT.label_for("user:mine", user), "Mine")
        self.assertEqual(UT.label_for("dark", user), THEMES["dark"]["label"])
        self.assertEqual(UT.label_for("custom", user), "Custom")
        self.assertEqual(UT.label_for("user:gone", user), "Custom")
        merged = UT.all_themes(user)
        self.assertEqual(list(merged)[-1], "user:mine")
        self.assertFalse(merged["dark"]["user"])

    def test_config_keeps_user_theme_names_but_not_junk(self):
        self.assertEqual(C.validate({"theme": "user:midnight"}, {})["theme"], "user:midnight")
        for junk in ("user:../../x", "user:", "user:UPPER", 5, None):
            self.assertEqual(C.validate({"theme": junk}, {})["theme"], "custom")


class WindowIdentityTests(unittest.TestCase):
    PKG = "glassdock"

    def entries(self):
        eid = "%s-settings.desktop" % self.PKG
        text = "[Desktop Entry]\nType=Application\nName=Settings\nExec=%s-settings\nIcon=/x.svg\n" % self.PKG
        return {eid: parse_desktop_text(text, eid, locales=[])}

    def test_settings_window_with_the_right_app_id_gets_its_entry_and_icon(self):
        items = M.build_items([], self.entries(), [Window(id=1, app_id="%s-settings" % self.PKG)])
        running = [i for i in items if i.windows]
        self.assertEqual(len(running), 1)
        self.assertIsNotNone(running[0].entry)
        self.assertEqual(running[0].icon, "/x.svg")

    def test_a_mismatched_app_id_is_what_causes_the_letter_tile(self):
        items = M.build_items([], self.entries(), [Window(id=1, app_id="settings.py")])
        self.assertIsNone([i for i in items if i.windows][0].entry)

    def test_settings_app_declares_its_app_id_and_icon(self):
        with open(os.path.join(ROOT, self.PKG, "settings.py"), encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn('set_prgname("%s-settings")' % self.PKG, src)
        self.assertIn('set_program_class("%s-settings")' % self.PKG, src)
        self.assertIn("_set_app_icon()", src)


if __name__ == "__main__":
    unittest.main()
