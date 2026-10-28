"""Dock sections (drag between pinned and running), right-side widgets and extras, Trash/Apps overrides."""
import os
import unittest
from types import SimpleNamespace

from glassdock import extras_store as XS
from glassdock.core import config as C, model as M
from glassdock.core.desktop import parse_desktop_text
from glassdock.core.dragzones import is_extra, is_slot_item, item_zone, place_extras, reorder_extras, zone_for
from glassdock.core.sway import Window

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def entry(eid, name, exec_line):
    return parse_desktop_text("[Desktop Entry]\nType=Application\nName=%s\nExec=%s\n" % (name, exec_line), eid, locales=[])


ENTRIES = {"foot.desktop": entry("foot.desktop", "Foot", "foot"), "firefox.desktop": entry("firefox.desktop", "Firefox", "firefox")}
SPANS = [(False, 0, 48), (False, 56, 104), (True, 112, 120), (True, 128, 176)]


def extra(wid, side=""):
    return SimpleNamespace(key="x:" + wid, kind="special", special="x:" + wid, cfg_index=-1, side=side)


class ZoneTests(unittest.TestCase):
    def test_zone_boundaries(self):
        self.assertEqual(zone_for(60, SPANS, 48), "left")
        self.assertEqual(zone_for(112, SPANS, 48), "right")
        self.assertEqual(zone_for(170, SPANS, 48), "right")

    def test_no_right_items_means_past_the_last_icon(self):
        left = SPANS[:2]
        self.assertEqual(zone_for(104 + 28, left, 48), "left")
        self.assertEqual(zone_for(104 + 30, left, 48), "right")
        self.assertEqual(zone_for(5, [], 48), "left")

    def test_item_zone(self):
        pinned = M.DockItem(key="a", kind="app", cfg_index=0)
        running = M.DockItem(key="b", kind="app", pinned=False)
        divider = M.DockItem(key="sep:run", kind="separator", pinned=False)
        cfg_right = M.DockItem(key="c", kind="widget", cfg_index=2, side="right")
        self.assertEqual([item_zone(i) for i in (pinned, running, divider, cfg_right)], ["left", "right", "right", "right"])
        self.assertEqual((item_zone(extra("clock-1")), item_zone(extra("clock-1", "right"))), ("left", "right"))
        self.assertTrue(is_extra(extra("a")) and not is_extra(pinned))
        self.assertTrue(is_slot_item(extra("a")) and is_slot_item(pinned) and not is_slot_item(running))


class PlaceExtrasTests(unittest.TestCase):
    def build(self, entries, out=None):
        base = out or [M.DockItem(key="app:a", kind="app", cfg_index=0),
                       M.DockItem(key="special:trash", kind="special", special="trash", cfg_index=1)]

        def divider():
            return M.DockItem(key="sep:right", kind="separator", pinned=False)
        return [i.key for i in place_extras(base, entries, lambda wid, side: extra(wid, side), divider)]

    def test_unset_goes_before_trash_like_before(self):
        self.assertEqual(self.build([(None, "w1", None)]), ["app:a", "x:w1", "special:trash"])

    def test_positions_are_honoured_in_order(self):
        self.assertEqual(self.build([(0, "w1", None), (2, "w2", None)]), ["x:w1", "app:a", "x:w2", "special:trash"])

    def test_right_extras_follow_everything_behind_a_divider(self):
        out = [M.DockItem(key="app:a", kind="app", cfg_index=0), M.DockItem(key="sep:run", kind="separator", pinned=False),
               M.DockItem(key="run:foot", kind="app", pinned=False)]
        self.assertEqual(self.build([(None, "w1", "right"), (None, "w2", "right")], out),
                         ["app:a", "sep:run", "run:foot", "sep:right", "x:w1", "x:w2"])

    def test_no_second_divider_when_one_exists(self):
        out = [M.DockItem(key="app:a", kind="app", cfg_index=0), M.DockItem(key="sep:right", kind="separator", pinned=False)]
        self.assertEqual(self.build([(None, "w1", "right")], out), ["app:a", "sep:right", "x:w1"])


class ReorderExtrasTests(unittest.TestCase):
    EXTRAS = [{"id": "a", "type": "clock", "at": 3}, {"id": "b", "type": "calendar", "at": None}, {"id": "c", "type": "music", "at": 5}]

    def test_move_within_left_reproduces_positions(self):
        out = reorder_extras(self.EXTRAS, "b", "left", {"a": 4, "b": 1, "c": 6}, [])
        self.assertEqual([(e["id"], e["at"]) for e in out], [("b", 1), ("a", 4), ("c", 6)])

    def test_move_to_right_and_back(self):
        out = reorder_extras(self.EXTRAS, "a", "right", {"b": 3, "c": 5}, ["a"])
        self.assertEqual([(e["id"], e.get("side")) for e in out], [("b", None), ("c", None), ("a", "right")])
        self.assertIsNone(out[-1]["at"])
        back = reorder_extras(out, "a", "left", {"a": 0, "b": 1, "c": 6}, [])
        self.assertEqual([(e["id"], e["at"], e.get("side")) for e in back], [("a", 0, None), ("b", 1, None), ("c", 6, None)])

    def test_right_order(self):
        extras = [{"id": "a", "type": "clock", "at": None, "side": "right"}, {"id": "b", "type": "music", "at": None}]
        out = reorder_extras(extras, "b", "right", {}, ["b", "a"])
        self.assertEqual([e["id"] for e in out], ["b", "a"])

    def test_unknown_id_changes_nothing(self):
        self.assertEqual(reorder_extras(self.EXTRAS, "zzz", "right", {}, []), self.EXTRAS)

    def test_side_survives_the_extras_store(self):
        data = XS._normalize({"extras": [{"id": "clock-1", "type": "analog_clock", "at": 2, "side": "right"},
                                         {"id": "clock-2", "type": "analog_clock", "at": 1, "side": "banana"}]})
        self.assertEqual([(e["id"], e.get("side")) for e in data["extras"]], [("clock-1", "right"), ("clock-2", None)])


class RightSideConfigTests(unittest.TestCase):
    def kinds(self, items):
        return [i.key for i in items]

    def test_side_is_kept_only_for_widgets_and_plugins(self):
        out = C.validate_items([{"type": "widget", "kind": "clock", "side": "right"},
                                {"type": "plugin", "name": "Mine", "side": "right"},
                                {"type": "plugin", "name": "Left", "side": "banana"},
                                {"type": "folder", "path": "/tmp", "side": "right"},
                                {"type": "special", "kind": "trash", "side": "right"}])
        self.assertEqual([i.get("side") for i in out], ["right", "right", None, None, None])

    def test_right_widgets_sit_after_the_running_apps(self):
        cfg = [{"type": "app", "id": "firefox.desktop"}, {"type": "widget", "kind": "clock", "side": "right"},
               {"type": "special", "kind": "trash"}]
        items = M.build_items(cfg, ENTRIES, [Window(id=1, app_id="foot")])
        self.assertEqual(self.kinds(items), ["app:firefox.desktop", "special:trash", "sep:run", "run:foot.desktop",
                                             "sep:right", "widget:clock"])
        self.assertEqual((items[-1].side, items[-1].cfg_index), ("right", 1))

    def test_right_widgets_without_running_apps_get_a_divider(self):
        cfg = [{"type": "app", "id": "firefox.desktop"}, {"type": "widget", "kind": "clock", "side": "right"}]
        self.assertEqual(self.kinds(M.build_items(cfg, ENTRIES, [])), ["app:firefox.desktop", "sep:right", "widget:clock"])

    def test_without_side_nothing_changes(self):
        cfg = [{"type": "widget", "kind": "clock"}, {"type": "app", "id": "firefox.desktop"}]
        self.assertEqual(self.kinds(M.build_items(cfg, ENTRIES, [])), ["widget:clock", "app:firefox.desktop"])


class SpecialOverrideTests(unittest.TestCase):
    def test_name_and_icon_overrides(self):
        items = C.validate_items([{"type": "special", "kind": "trash", "name": " Bin ", "icon": "user-trash-full"},
                                  {"type": "special", "kind": "apps", "name": 7}])
        self.assertEqual(items[0], {"type": "special", "kind": "trash", "name": "Bin", "icon": "user-trash-full"})
        self.assertEqual(items[1], {"type": "special", "kind": "apps"})
        built = M.build_items(items, {}, [])
        self.assertEqual((built[0].name, built[0].icon, built[0].custom_icon), ("Bin", "user-trash-full", True))
        self.assertEqual((built[1].name, built[1].custom_icon), ("Applications", False))


class WiringTests(unittest.TestCase):
    def src(self, name):
        with open(os.path.join(ROOT, "glassdock", name), encoding="utf-8") as fh:
            return fh.read()

    def test_dock(self):
        s = self.src("dock.py")
        for needle in ("DZ.zone_for(", "def drop_item", "def drop_kind", "def slot_at", "def drop_extra", "def pin_at", "def set_side",
                       "DZ.is_extra(it)", 'not getattr(it, "custom_icon", False)', "# Trash/Apps can be customized",
                       "self.drag_marker_ok()", "self.drag_marker_pos()"):
            self.assertIn(needle, s, needle)

    def test_extensions(self):
        s = self.src("dock_extensions.py")
        for needle in ("DZ.place_extras(", "def move_extra", "DZ.reorder_extras(", "side=side"):
            self.assertIn(needle, s, needle)

    def test_settings(self):
        s = self.src("settings.py")
        for needle in ("SimpleNamespace", 'spec["type"] == "special"', "right side"):
            self.assertIn(needle, s, needle)


if __name__ == "__main__":
    unittest.main()
