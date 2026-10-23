import json
import tempfile
import unittest
from pathlib import Path

from glassdock.core import config as C
from glassdock.core import usertheme as UT


class UserThemeTests(unittest.TestCase):
    def test_validation_only_accepts_theme_keys(self):
        data = {
            "format": UT.FORMAT,
            "version": UT.VERSION,
            "name": "Safe theme",
            "description": "test",
            "values": {
                "appearance.bg_color": "#123456",
                "behavior.launcher_command": "touch /tmp/should-not-be-applied",
                "extensions.plugins_enabled": False,
            },
        }
        result = UT.validate_theme(data)
        self.assertEqual(result["values"]["appearance.bg_color"], "#123456")
        self.assertNotIn("behavior.launcher_command", result["values"])
        self.assertNotIn("extensions.plugins_enabled", result["values"])
        self.assertIn("behavior.launcher_command", result["ignored"])
        self.assertIn("extensions.plugins_enabled", result["ignored"])

    def test_invalid_theme_inputs_are_rejected(self):
        for data in (
            [],
            {"name": "", "values": {"appearance.bg_color": "#123456"}},
            {"name": "Bad", "values": {"appearance.bg_color": "not-a-color"}},
            {"format": "not-glassdock", "name": "Bad", "values": {"appearance.bg_color": "#123456"}},
        ):
            with self.subTest(data=data), self.assertRaises(UT.ThemeError):
                UT.validate_theme(data)

    def test_save_import_export_apply_and_delete(self):
        with tempfile.TemporaryDirectory() as td:
            themes_dir = Path(td) / "themes"
            cfg = C.default_config()
            C.set_path(cfg, "appearance.bg_color", "#123456")
            name = UT.save_theme(cfg, "My Theme", "a short description", str(themes_dir))
            self.assertEqual(name, "user:my-theme")
            self.assertTrue((themes_dir / "my-theme.json").is_file())

            listed, problems = UT.list_user_themes(str(themes_dir))
            self.assertFalse(problems)
            self.assertIn(name, listed)
            self.assertEqual(listed[name]["values"]["appearance.bg_color"], "#123456")

            export_path = Path(td) / "export.json"
            UT.export_file(listed[name], str(export_path))
            imported, info = UT.import_file(str(export_path), str(themes_dir))
            self.assertEqual(imported, "user:my-theme-2")
            self.assertEqual(info["values"]["appearance.bg_color"], "#123456")

            fresh = C.default_config()
            UT.apply_values(fresh, listed[name], name)
            self.assertEqual(C.get_path(fresh, "appearance.bg_color"), "#123456")
            self.assertTrue(UT.matches(fresh, listed[name]))
            self.assertTrue(UT.delete_theme(imported, str(themes_dir)))
            self.assertTrue(UT.delete_theme(name, str(themes_dir)))
            self.assertFalse(UT.delete_theme(name, str(themes_dir)))

    def test_saved_theme_file_contains_only_theme_values(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = C.default_config()
            C.set_path(cfg, "appearance.bg_color", "#334455")
            UT.save_theme(cfg, "Clean", directory=td)
            saved = json.loads((Path(td) / "clean.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["format"], UT.FORMAT)
            self.assertEqual(set(saved["values"]), set(C.THEME_KEYS))
            self.assertNotIn("extensions.plugins_enabled", saved["values"])

    def test_rename_theme_cleans_label_without_changing_values(self):
        with tempfile.TemporaryDirectory() as td:
            name = UT.save_theme(C.default_config(), "Original", directory=td)
            original = json.loads((Path(td) / "original.json").read_text(encoding="utf-8"))
            UT.rename_theme(name, "  New\n Name  ", directory=td)
            updated = json.loads((Path(td) / "original.json").read_text(encoding="utf-8"))
            self.assertEqual(updated["name"], "New Name")
            self.assertEqual(updated["values"], original["values"])


if __name__ == "__main__":
    unittest.main()
