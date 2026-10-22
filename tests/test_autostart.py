"""Autostart-by-window-manager decisions and the drag reorder helper."""
import unittest

from glassdock.core import autostart as A
from glassdock.core import config as C
from glassdock.core import model as M


def cfg(**kw):
    c = C.default_config()
    for k, v in kw.items():
        C.set_path(c, k.replace("__", "."), v)
    return c


class AutostartTests(unittest.TestCase):
    def test_default_is_sway_only(self):
        self.assertTrue(A.should_start(cfg(), {"XDG_CURRENT_DESKTOP": "sway"})[0])
        self.assertTrue(A.should_start(cfg(), {"SWAYSOCK": "/run/x"})[0])
        self.assertFalse(A.should_start(cfg(), {"XDG_CURRENT_DESKTOP": "GNOME"})[0])

    def test_list_parsing_and_aliases(self):
        c = cfg(behavior__autostart_wms="Hyprland, niri ; swayfx")
        self.assertTrue(A.should_start(c, {"XDG_SESSION_DESKTOP": "hyprland"})[0])
        self.assertTrue(A.should_start(c, {"NIRI_SOCKET": "/x"})[0])
        self.assertTrue(A.should_start(c, {"DESKTOP_SESSION": "sway"})[0])
        self.assertFalse(A.should_start(c, {"XDG_CURRENT_DESKTOP": "KDE"})[0])

    def test_wildcard_off_and_empty(self):
        self.assertTrue(A.should_start(cfg(behavior__autostart_wms="*"), {})[0])
        self.assertFalse(A.should_start(cfg(behavior__autostart=False), {"SWAYSOCK": "1"})[0])
        self.assertFalse(A.should_start(cfg(behavior__autostart_wms=""), {"SWAYSOCK": "1"})[0])

    def test_colon_separated_current_desktop(self):
        c = cfg(behavior__autostart_wms="river")
        self.assertTrue(A.should_start(c, {"XDG_CURRENT_DESKTOP": "wlroots:river"})[0])


class ReorderTests(unittest.TestCase):
    L = ["a", "b", "c", "d"]

    def test_move_forward_and_back(self):
        self.assertEqual(M.reorder_items(self.L, 0, 3), ["b", "c", "a", "d"])
        self.assertEqual(M.reorder_items(self.L, 3, 1), ["a", "d", "b", "c"])

    def test_move_to_end(self):
        self.assertEqual(M.reorder_items(self.L, 1, None), ["a", "c", "d", "b"])

    def test_noops(self):
        self.assertIsNone(M.reorder_items(self.L, 1, 1))
        self.assertIsNone(M.reorder_items(self.L, 1, 2))
        self.assertIsNone(M.reorder_items(self.L, 3, None))
        self.assertIsNone(M.reorder_items(self.L, 9, 0))

    def test_input_not_mutated(self):
        before = list(self.L)
        M.reorder_items(self.L, 0, 3)
        self.assertEqual(self.L, before)


class ConfigBits(unittest.TestCase):
    def test_new_settings_exist_and_validate(self):
        for k in ("behavior.autostart", "behavior.autostart_wms", "appearance.icon_radius"):
            self.assertIn(k, C.SETTINGS)
        self.assertEqual(C.coerce(C.SETTINGS["appearance.corner_radius"], 500), 120)
        self.assertEqual(C.coerce(C.SETTINGS["appearance.icon_radius"], 500), 50)


if __name__ == "__main__":
    unittest.main()
