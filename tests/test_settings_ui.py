"""Rename / change-icon overrides on pinned apps, plus static settings-UI checks."""
import os
import re
import unittest

from glassdock.core import config as C, model as M
from glassdock.core.desktop import parse_desktop_text

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def entry(eid="foot.desktop", name="Foot"):
    return parse_desktop_text("[Desktop Entry]\nType=Application\nName=%s\nExec=foot\nIcon=foot\n" % name, eid, locales=[])


def source(rel):
    with open(os.path.join(ROOT, "glassdock", rel), encoding="utf-8") as fh:
        return fh.read()


class OverrideTests(unittest.TestCase):
    def test_overrides_survive_validation(self):
        items = C.validate_items([{"type": "app", "id": "foot.desktop", "name": "  Terminal ", "icon": "utilities-terminal"}])
        self.assertEqual(items, [{"type": "app", "id": "foot.desktop", "name": "Terminal", "icon": "utilities-terminal"}])

    def test_empty_or_bad_overrides_are_dropped(self):
        items = C.validate_items([{"type": "app", "id": "foot.desktop", "name": "  ", "icon": 5}])
        self.assertEqual(items, [{"type": "app", "id": "foot.desktop"}])

    def test_overrides_are_length_limited(self):
        items = C.validate_items([{"type": "app", "id": "a.desktop", "name": "x" * 500}])
        self.assertEqual(len(items[0]["name"]), 100)

    def test_dock_item_uses_override_then_falls_back(self):
        ents = {"foot.desktop": entry()}
        custom = M.build_items([{"type": "app", "id": "foot.desktop", "name": "Terminal", "icon": "tilix"}], ents, [])
        plain = M.build_items([{"type": "app", "id": "foot.desktop"}], ents, [])
        self.assertEqual((custom[0].name, custom[0].icon), ("Terminal", "tilix"))
        self.assertEqual((plain[0].name, plain[0].icon), ("Foot", "foot"))

    def test_dock_menu_offers_rename(self):
        src = source("dock.py")
        self.assertIn("Rename / Change Icon", src)
        self.assertIn("def edit_item", src)


class SettingsUiTests(unittest.TestCase):
    def test_stylesheet_only_uses_standard_theme_colors(self):
        css = source("settings.py").split('CSS = b"""', 1)[1].split('"""', 1)[0]
        used = set(re.findall(r"@([a-z_]+)", css))
        self.assertLessEqual(used, {"theme_fg_color", "theme_bg_color", "theme_base_color",
                                    "theme_selected_bg_color", "theme_selected_fg_color"})

    def test_every_category_has_an_icon_and_blurb(self):
        src = source("settings.py")
        for cat, _label in C.CATEGORIES:
            self.assertRegex(src, r'"%s": \(' % cat)
            self.assertRegex(src, r'"%s": "' % cat)

    def test_settings_accepts_edit_flag(self):
        self.assertIn('"--edit"', source("settings.py"))


if __name__ == "__main__":
    unittest.main()
