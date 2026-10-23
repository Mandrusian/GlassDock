import os
import tempfile
import unittest

from glassdock.core import model as M
from glassdock.core import control
from glassdock.core.desktop import parse_desktop_text
from glassdock.core.sway import Window


def entry(eid, name, exec_line, wm=""):
    text = "[Desktop Entry]\nType=Application\nName=%s\nExec=%s\n" % (name, exec_line)
    if wm:
        text += "StartupWMClass=%s\n" % wm
    return parse_desktop_text(text, eid, locales=[])


def win(i, app_id="", cls="", focused=False, **kw):
    return Window(id=i, app_id=app_id, wm_class=cls, focused=focused, **kw)


ENTRIES = {
    "org.mozilla.firefox.desktop": entry("org.mozilla.firefox.desktop", "Firefox", "firefox %u"),
    "org.gnome.Nautilus.desktop": entry("org.gnome.Nautilus.desktop", "Files", "nautilus --new-window"),
    "steam.desktop": entry("steam.desktop", "Steam", "/usr/bin/steam %U", wm="Steam"),
    "foot.desktop": entry("foot.desktop", "Foot", "foot"),
    "code.desktop": entry("code.desktop", "Visual Studio Code", "/usr/share/code/code %F", wm="Code"),
}

CFG_ITEMS = [
    {"type": "special", "kind": "apps"},
    {"type": "app", "id": "org.mozilla.firefox.desktop"},
    {"type": "app", "id": "org.gnome.Nautilus.desktop"},
    {"type": "app", "id": "missing.desktop"},
    {"type": "launcher", "name": "My Tool", "exec": "/opt/tool/run --x", "match": "mytool"},
    {"type": "separator"},
    {"type": "special", "kind": "trash"},
]


class MatchTests(unittest.TestCase):
    def test_pinned_matching_and_missing_hidden(self):
        wins = [win(1, "firefox"), win(2, "firefox", focused=True), win(3, "org.gnome.Nautilus"),
                win(4, "MyTool")]
        items = M.build_items(CFG_ITEMS, ENTRIES, wins)
        keys = [i.key for i in items]
        self.assertNotIn("app:missing.desktop", keys)
        ff = next(i for i in items if i.key == "app:org.mozilla.firefox.desktop")
        self.assertEqual(len(ff.windows), 2)
        self.assertTrue(ff.active)
        self.assertEqual(len(next(i for i in items if i.kind == "launcher").windows), 1)
        self.assertEqual(len(next(i for i in items if i.key.endswith("Nautilus.desktop")).windows), 1)
        self.assertFalse(any(i.key.startswith("run:") for i in items))

    def test_unclaimed_grouped_and_separated(self):
        wins = [win(1, "foot"), win(2, "foot"), win(3, cls="Steam"), win(4, "weird-app"),
                win(5, "weird-app")]
        items = M.build_items(CFG_ITEMS, ENTRIES, wins)
        tail = items[-4:]
        self.assertEqual(tail[0].kind, "separator")   # divider between pinned and running-only
        self.assertEqual(items[-5].special, "trash")  # last pinned item sits before the divider
        run = [i for i in items if i.key.startswith("run:")]
        self.assertEqual({i.key for i in run}, {"run:foot.desktop", "run:steam.desktop", "run:weird-app"})
        self.assertEqual(len(next(i for i in run if i.key == "run:foot.desktop").windows), 2)
        self.assertFalse(any(i.pinned for i in run))
        generic = next(i for i in run if i.key == "run:weird-app")
        self.assertEqual(generic.icon, "weird-app")
        self.assertEqual(len(generic.windows), 2)
        self.assertEqual(items[[i.key for i in items].index("run:foot.desktop") - 1].kind, "separator")

    def test_hide_unpinned(self):
        items = M.build_items(CFG_ITEMS, ENTRIES, [win(1, "foot")], show_unpinned=False)
        self.assertFalse(any(i.key.startswith("run:") for i in items))

    def test_reverse_dns_and_case(self):
        items = M.build_items([{"type": "app", "id": "org.mozilla.firefox.desktop"}], ENTRIES,
                              [win(1, "Firefox")])
        self.assertEqual(len(items[0].windows), 1)
        items = M.build_items([{"type": "app", "id": "code.desktop"}], ENTRIES, [win(1, cls="Code")])
        self.assertEqual(len(items[0].windows), 1)

    def test_strong_beats_weak(self):
        ents = {"a.desktop": entry("a.desktop", "foo", "x"), "b.desktop": entry("b.desktop", "other", "foo")}
        items = M.build_items([{"type": "app", "id": "b.desktop"}, {"type": "app", "id": "a.desktop"}], ents,
                              [win(1, "a")])
        self.assertEqual([len(i.windows) for i in items], [0, 1])

    def test_extension_item_models_and_badges(self):
        specs = [
            {"type": "folder", "path": "/tmp", "name": "Temp", "badge_count": 3},
            {"type": "widget", "kind": "clock"},
            {"type": "widget", "kind": "calendar"},
            {"type": "widget", "kind": "music"},
            {"type": "plugin", "name": "sample"},
            {"type": "launcher", "name": "Alerts", "exec": "true", "badge_count": 7},
        ]
        items = M.build_items(specs, ENTRIES, [])
        self.assertEqual([item.kind for item in items], ["folder", "widget", "widget", "widget", "plugin", "launcher"])
        self.assertEqual(items[0].path, "/tmp")
        self.assertEqual(items[0].badge_count, 3)
        self.assertEqual([item.extension for item in items[1:4]], ["clock", "calendar", "music"])
        self.assertEqual(items[4].extension, "sample")
        self.assertEqual(items[5].badge_count, 7)

    def test_no_windows(self):
        items = M.build_items(CFG_ITEMS, ENTRIES, [])
        self.assertTrue(all(not i.running for i in items))


class MagnifyTests(unittest.TestCase):
    def test_curve(self):
        self.assertEqual(M.magnify_scale(0, 1.0, 2), 1.0)
        self.assertAlmostEqual(M.magnify_scale(0, 1.6, 2), 1.6)
        self.assertEqual(M.magnify_scale(2, 1.6, 2), 1.0)
        self.assertEqual(M.magnify_scale(5, 1.6, 2), 1.0)
        vals = [M.magnify_scale(d / 10, 1.6, 2) for d in range(0, 21)]
        self.assertEqual(vals, sorted(vals, reverse=True))

    def test_target_scales_skip_separators(self):
        kinds = ["app", "separator", "app"]
        sc = M.target_scales(kinds, 0.5, 1.5, 2.0)
        self.assertAlmostEqual(sc[0], 1.5)
        self.assertEqual(sc[1], 1.0)
        self.assertEqual(M.target_scales(kinds, None, 1.5, 2.0), [1.0] * 3)
        self.assertEqual(M.target_scales(kinds, 0.5, 1.5, 2.0, enabled=False), [1.0] * 3)

    def test_pointer_slot(self):
        sizes = [50, 50, 10, 50]
        pos, total = M.base_layout(sizes, 8)
        self.assertEqual(total, 50 * 3 + 10 + 8 * 3)
        self.assertAlmostEqual(M.pointer_slot(25, pos, sizes), 0.5)
        self.assertAlmostEqual(M.pointer_slot(pos[3] + 25, pos, sizes), 3.5)
        self.assertLess(M.pointer_slot(-10, pos, sizes), 0)
        self.assertGreater(M.pointer_slot(total + 10, pos, sizes), 4)
        self.assertIsNone(M.pointer_slot(0, [], []))

    def test_max_length_bounds(self):
        kinds = ["app"] * 6
        base = M.dock_length(kinds, 50, 8, 10)
        mx = M.max_dock_length(kinds, 50, 8, 10, 1.5, 2.0, True)
        self.assertGreater(mx, base)
        self.assertLess(mx, base + 50 * 0.5 * 6)
        self.assertEqual(M.max_dock_length(kinds, 50, 8, 10, 1.5, 2.0, False), base)
        # every sampled pointer position fits
        for k in range(0, 60):
            sc = M.target_scales(kinds, k / 10 - 0.5, 1.5, 2.0)
            self.assertLessEqual(M.dock_length(kinds, 50, 8, 10, sc), mx + 1e-6)


class GeometryTests(unittest.TestCase):
    def geo(self, **kw):
        kinds = kw.pop("kinds", ["app"] * 5)
        args = dict(icon=52, spacing=8, padding=10, margin=10, shadow_size=18, edge="bottom",
                    alignment="center", indicator_size=4, indicator_style="dot", magnify=True,
                    factor=1.5, reach=2.0, bounce=True, labels=True)
        args.update(kw)
        return M.compute_geometry(kinds, **args)

    def test_basic(self):
        g = self.geo()
        self.assertEqual(g.thick, 52 + 20 + 8)
        self.assertEqual(g.c0, 10)
        self.assertEqual(g.layer_margin, 0)
        self.assertGreater(g.win_main, g.base_len)
        w, h = g.win_size
        self.assertEqual((w, h), (g.win_main, g.win_cross))
        self.assertGreaterEqual(g.win_cross, g.c0 + g.thick + 52 * 0.5)

    def test_big_margin_uses_layer_margin(self):
        g = self.geo(margin=40)
        self.assertEqual(g.c0, 18)
        self.assertEqual(g.layer_margin, 22)
        self.assertEqual(g.c0 + g.layer_margin, 40)

    def test_vertical_swaps_size(self):
        g = self.geo(edge="left")
        self.assertEqual(g.win_size, (g.win_cross, g.win_main))

    def test_no_indicator_no_room(self):
        self.assertEqual(self.geo(indicator_style="none").ind_room, 0)

    def test_origin(self):
        g = self.geo()
        self.assertAlmostEqual(M.dock_origin(g, g.base_len), (g.win_main - g.base_len) / 2)
        self.assertEqual(M.dock_origin(self.geo(alignment="start"), 100), 10)
        g2 = self.geo(alignment="end")
        self.assertEqual(M.dock_origin(g2, 100), g2.win_main - 10 - 100)

    def test_long_dock_is_fitted_to_available_main_axis(self):
        kinds = ["app"] * 15 + ["separator"] + ["widget"] * 5
        raw = self.geo(kinds=kinds, icon=96)
        fitted = self.geo(kinds=kinds, icon=96, max_main=760)
        self.assertGreater(raw.win_main, 760)
        self.assertLessEqual(fitted.win_main, 760)
        self.assertLess(fitted.icon, raw.icon)
        self.assertLess(fitted.base_len, raw.base_len)
        self.assertEqual(fitted.n_kinds, len(kinds))

    def test_fitting_preserves_requested_size_when_it_already_fits(self):
        ordinary = self.geo()
        fitted = self.geo(max_main=ordinary.win_main + 100)
        self.assertEqual(fitted.icon, ordinary.icon)
        self.assertEqual(fitted.spacing, ordinary.spacing)
        self.assertEqual(fitted.padding, ordinary.padding)
        self.assertEqual(fitted.win_main, ordinary.win_main)

    def test_very_large_icon_configuration_cannot_exceed_main_axis_budget(self):
        for edge in ("bottom", "top", "left", "right"):
            with self.subTest(edge=edge):
                fitted = self.geo(kinds=["app"] * 12, icon=128, edge=edge, max_main=540)
                self.assertLessEqual(fitted.win_main, 540)
                self.assertGreater(fitted.icon, 0)

    def test_exclusive_zone(self):
        g = self.geo()
        self.assertEqual(M.exclusive_zone(g, True, "off"), int(g.c0 + g.thick))
        self.assertEqual(M.exclusive_zone(g, True, "always"), 0)
        self.assertEqual(M.exclusive_zone(g, False, "off"), 0)

    def test_place_roundtrip(self):
        W, H = 400, 120
        for edge in ("bottom", "top", "left", "right"):
            x, y, w, h = M.place(edge, W, H, 30, 10, 50, 40)
            self.assertGreaterEqual(x, 0)
            self.assertGreaterEqual(y, 0)
            m, c = M.unplace(edge, W, H, x + w / 2, y + h / 2)
            self.assertAlmostEqual(m, 30 + 25)
            self.assertAlmostEqual(c, 10 + 20)
        self.assertEqual(M.place("bottom", W, H, 0, 0, 10, 10), (0, 110, 10, 10))   # touches bottom edge
        self.assertEqual(M.place("top", W, H, 0, 0, 10, 10), (0, 0, 10, 10))
        self.assertEqual(M.place("left", W, H, 0, 0, 10, 10), (0, 0, 10, 10))
        self.assertEqual(M.place("right", W, H, 0, 0, 10, 10), (390, 0, 10, 10))

    def test_global_rect(self):
        out = (100, 50, 1000, 600)
        self.assertEqual(M.dock_global_rect(out, "bottom", "center", 10, 200, 80), (500, 560, 200, 80))
        self.assertEqual(M.dock_global_rect(out, "top", "start", 10, 200, 80), (110, 60, 200, 80))
        self.assertEqual(M.dock_global_rect(out, "left", "end", 10, 200, 80), (110, 440, 80, 200))
        self.assertEqual(M.dock_global_rect(out, "right", "center", 10, 200, 80), (1010, 250, 80, 200))


class VisibilityTests(unittest.TestCase):
    def vis(self, **kw):
        a = dict(mode="off", fullscreen=False, hide_on_fullscreen=True, overlapping=False,
                 pointer_inside=False, menu_open=False)
        a.update(kw)
        return M.decide_visibility(**a)

    def test_matrix(self):
        self.assertTrue(self.vis())
        self.assertFalse(self.vis(fullscreen=True))
        self.assertTrue(self.vis(fullscreen=True, hide_on_fullscreen=False))
        self.assertFalse(self.vis(mode="always"))
        self.assertTrue(self.vis(mode="always", pointer_inside=True))
        self.assertTrue(self.vis(mode="always", menu_open=True))
        self.assertTrue(self.vis(mode="overlap"))
        self.assertFalse(self.vis(mode="overlap", overlapping=True))
        self.assertTrue(self.vis(mode="overlap", overlapping=True, pointer_inside=True))
        self.assertFalse(self.vis(mode="always", pointer_inside=True, fullscreen=True))

    def test_overlap_detection(self):
        dock = (400, 500, 300, 80)
        wins = [win(1, "a", output="eDP-1", visible=True, rect=(0, 0, 800, 520)),
                win(2, "b", output="eDP-1", visible=False, rect=(0, 0, 800, 600)),
                win(3, "c", output="DP-1", visible=True, rect=(0, 0, 800, 600))]
        self.assertTrue(M.overlapping_windows(dock, wins, "eDP-1"))
        self.assertFalse(M.overlapping_windows(dock, wins[1:2], "eDP-1"))   # hidden workspace
        self.assertFalse(M.overlapping_windows(dock, wins[2:], "eDP-1"))    # other output
        wins[0].rect = (0, 0, 800, 400)
        self.assertFalse(M.overlapping_windows(dock, wins[:1], "eDP-1"))
        wins[0].rect = (0, 0, 800, 600)
        wins[0].fullscreen = True
        self.assertFalse(M.overlapping_windows(dock, wins[:1], "eDP-1"))

    def test_indicators(self):
        self.assertEqual(M.indicator_layout(0, False, "dot"), [])
        self.assertEqual(M.indicator_layout(2, True, "dot"), ["active", "normal"])
        self.assertEqual(M.indicator_layout(9, False, "dot"), ["normal"] * 3)
        self.assertEqual(M.indicator_layout(3, True, "line"), ["active"])
        self.assertEqual(M.indicator_layout(3, True, "none"), [])

    def test_easing(self):
        for name in ("linear", "ease-out", "ease-in-out"):
            self.assertEqual(M.ease(name, 0), 0)
            self.assertEqual(M.ease(name, 1), 1)
            self.assertEqual(M.ease(name, 5), 1)
        self.assertGreater(M.ease("ease-out", 0.5), 0.5)


class ControlSocketTests(unittest.TestCase):
    def test_roundtrip_and_single_instance(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "c.sock")
            srv = control.ControlServer(lambda m: {"ok": True, "echo": m.get("cmd")}, p)
            srv.bind()
            srv.start()
            self.assertEqual(control.send_command({"cmd": "ping"}, p), {"ok": True, "echo": "ping"})
            with self.assertRaises(control.AlreadyRunning):
                control.ControlServer(lambda m: {}, p).bind()
            srv.stop()
            self.assertIsNone(control.send_command({"cmd": "ping"}, p, timeout=0.3))

    def test_stale_socket_replaced(self):
        import socket
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "c.sock")
            s = socket.socket(socket.AF_UNIX)
            s.bind(p)
            s.close()  # leaves a stale file with no listener
            srv = control.ControlServer(lambda m: {"ok": True}, p)
            srv.bind()
            srv.stop()


if __name__ == "__main__":
    unittest.main()
