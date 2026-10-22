"""GTK/layer-shell smoke test. Skipped unless run inside a Wayland session that
supports wlr-layer-shell (for example your Sway/SwayFX session)."""
import os
import unittest

try:
    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import Gdk, Gtk, GtkLayerShell
    HAVE_GTK = True
except Exception:  # missing typelibs/bindings
    HAVE_GTK = False


def _supported():
    if not HAVE_GTK or not os.environ.get("WAYLAND_DISPLAY"):
        return False
    display = Gdk.Display.get_default()
    return display is not None and GtkLayerShell.is_supported()


def pump(n=40):
    for _ in range(n):
        while Gtk.events_pending():
            Gtk.main_iteration()


@unittest.skipUnless(_supported(), "needs a Wayland session with wlr-layer-shell (run inside Sway)")
class GtkSmoke(unittest.TestCase):
    def setUp(self):
        import cairo
        from moderndock import dock
        from moderndock.core import config as C, model as M
        from moderndock.core.desktop import load_entries
        self.cairo, self.dock, self.C, self.M = cairo, dock, C, M
        self.entries = load_entries()
        self.app = dock.DockApp()
        self.app.icons = dock.IconCache()

    def render(self, win):
        w, h = win.geo.win_size
        surf = self.cairo.ImageSurface(self.cairo.FORMAT_ARGB32, w, h)
        cr = self.cairo.Context(surf)
        win.area.set_size_request(w, h)
        win.on_draw(win.area, cr)
        surf.flush()
        return surf

    def test_every_edge_and_alignment_renders(self):
        C, M = self.C, self.M
        out = self.app.fallback_outputs()[0]
        for edge in ("bottom", "top", "left", "right"):
            for align in ("start", "center", "end"):
                cfg = C.default_config(self.entries)
                C.set_path(cfg, "position.edge", edge)
                C.set_path(cfg, "position.alignment", align)
                win = self.dock.DockWindow(self.app, out)
                items = M.build_items(cfg["items"], self.entries, [], True)
                win.apply(cfg, items, [], False)
                pump()
                surf = self.render(win)
                self.assertTrue(any(surf.get_data()), "%s/%s drew nothing" % (edge, align))
                win.destroy()

    def test_hover_magnification_and_hide(self):
        C, M = self.C, self.M
        out = self.app.fallback_outputs()[0]
        cfg = C.default_config(self.entries)
        C.set_path(cfg, "behavior.autohide", "always")
        C.set_path(cfg, "animation.duration", 0)
        win = self.dock.DockWindow(self.app, out)
        items = M.build_items(cfg["items"], self.entries, [], True)
        win.apply(cfg, items, [], False)
        pump()
        self.assertFalse(win.vis_target, "auto-hide 'always' should start hidden")
        win.pointer_inside = True
        win.reevaluate()
        self.assertTrue(win.vis_target)
        win.pointer = (win.geo.win_main / 2.0, win.geo.c0 + 20)
        win.update_targets()
        self.assertTrue(any(v > 1.0 for v in win.targets.values()))
        win.destroy()


if __name__ == "__main__":
    unittest.main()
