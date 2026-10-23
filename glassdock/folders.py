# Integrated GlassDock extension module.
"""Folder-in-dock: icon shows a 2x2 preview (or a custom icon); click opens a Japanese-fan of children.

Children come from: apps (desktop ids), files (any path), path (a directory's contents). Per-child icon
overrides live in folder["child_icons"] keyed by app id or file basename. The fan is a transparent Gtk.Popover
pointing at the folder icon, so it works on any dock edge without a second layer-shell surface.
"""
import math
import os

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

from . import fan_math as F  # noqa: E402
from .widgets import Widget, rrect, surface_from_path, text, tile  # noqa: E402

MAX_CHILDREN = 14
CSS = b"""
popover.gd-fan, popover.gd-fan.background { background: transparent; border: none; box-shadow: none; padding: 0; }
popover.gd-fan arrow { min-width: 0; min-height: 0; opacity: 0; }
"""
_css_done = False


def install_fan_css():
    global _css_done
    if not _css_done:
        p = Gtk.CssProvider()
        p.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), p, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        _css_done = True


class FolderWidget(Widget):
    TYPE = "folder"

    def __init__(self, wid, fcfg, host):
        super().__init__(wid, fcfg, host)
        self._child_surface_cache = {}

    def tooltip(self):
        return self.cfg["name"]

    # ---- children -------------------------------------------------------
    def children(self):
        """[{'key','name','kind':'app'|'file','id'|'path'}]"""
        out = []
        for app_id in self.cfg.get("apps", []):
            ent = self.host.app.entries.get(app_id) or self.host.app.entries.get(app_id.replace(".desktop", ""))
            out.append({"key": app_id, "name": getattr(ent, "name", app_id), "kind": "app", "id": app_id})
        paths = list(self.cfg.get("files", []))
        d = self.cfg.get("path")
        if d and os.path.isdir(os.path.expanduser(d)):
            d = os.path.expanduser(d)
            try:
                names = sorted(os.listdir(d), key=lambda n: (not os.path.isdir(os.path.join(d, n)), n.lower()))
            except OSError:
                names = []
            paths += [os.path.join(d, n) for n in names if not n.startswith(".")]
        for p in paths:
            out.append({"key": os.path.basename(p), "name": os.path.basename(p) or p, "kind": "file", "path": p})
        return out[:MAX_CHILDREN]

    def child_surface(self, child, px, scale, window):
        override = self.cfg.get("child_icons", {}).get(child["key"], "")
        cache_key = (child.get("key"), child.get("path") or child.get("id"), override, int(px), int(scale))
        if cache_key in self._child_surface_cache:
            return self._child_surface_cache[cache_key]
        result = None
        if override:
            result = surface_from_path(os.path.expanduser(override), px, scale)
        if result is None and child["kind"] == "app":
            items = self.host.make_app_items(child["id"])
            result = self.host.app.icons.get_item(items[0], px, scale, window) if items else None
        elif result is None:
            try:
                info = Gio.File.new_for_path(child["path"]).query_info("standard::icon", 0, None)
                lookup = Gtk.IconTheme.get_default().lookup_by_gicon(
                    info.get_icon(), px, Gtk.IconLookupFlags.FORCE_SIZE)
                surf = lookup.load_surface(window) if lookup else None
                result = (surf, px, px) if surf else None
            except (GLib.Error, OSError, TypeError, ValueError):
                result = None
        # Missing icons can appear later (for example after an app install); do not cache misses.
        if result is not None:
            self._child_surface_cache[cache_key] = result
        return result

    # ---- icon -------------------------------------------------------------
    def draw(self, cr, s, pct):
        custom = self.cfg.get("icon")
        if custom:
            res = surface_from_path(os.path.expanduser(custom), int(s), 2)
            if res:
                surf, lw, lh = res
                cr.save(); cr.scale(s / lw, s / lh); cr.set_source_surface(surf, 0, 0); cr.paint(); cr.restore()
                return
        tile(cr, s, (0.82, 0.86, 0.95, 0.55), (0.55, 0.62, 0.78, 0.55), pct)
        rrect(cr, 0.5, 0.5, s - 1, s - 1, s * (pct / 100.0 if pct else 0.23))
        cr.set_source_rgba(1, 1, 1, 0.45); cr.set_line_width(1); cr.stroke()
        kids = self.children()[:4]
        cell, gap = s * 0.36, s * 0.06
        x0 = (s - (2 * cell + gap)) / 2
        for i, ch in enumerate(kids):
            res = self.child_surface(ch, int(cell), 2, None)
            x, y = x0 + (i % 2) * (cell + gap), x0 + (i // 2) * (cell + gap)
            if res and res[0] is not None:
                surf, lw, lh = res
                cr.save(); cr.translate(x, y); cr.scale(cell / lw, cell / lh); cr.set_source_surface(surf, 0, 0); cr.paint(); cr.restore()
            else:
                rrect(cr, x, y, cell, cell, cell * 0.22); cr.set_source_rgba(1, 1, 1, 0.5); cr.fill()
        if not kids:
            text(cr, "+", s / 2, s / 2, s * 0.5, (1, 1, 1, 0.8), True)

    # ---- click -> fan -----------------------------------------------------
    def on_click(self, host, dock, item, button):
        kids = self.children()
        if not kids:
            host.app_toast("Folder is empty — drop apps or files onto it")
            return None
        install_fan_css()
        return FanArea(self, dock, kids)


class FanArea(Gtk.DrawingArea):
    """Transparent drawing surface hosted by the popover (host sets class gd-fan on the popover)."""
    WANTS_FAN = True

    def __init__(self, folder, dock, kids):
        super().__init__()
        self.folder, self.dock, self.kids, self.host = folder, dock, kids, folder.host
        self.edge = dock.geo.edge
        self.icon = max(40, int(dock.geo.icon * 1.05))
        cfg = folder.cfg
        self.layout = F.fan_layout(len(kids), self.icon, cfg.get("spread", 90), cfg.get("radius", 0))
        self.length, self.half = F.fan_bounds(self.layout, self.icon)
        w, h = (self.half * 2, self.length) if self.edge in ("bottom", "top") else (self.length, self.half * 2)
        self.set_size_request(int(w), int(h))
        self.anim, self.hover, self.last = F.FanAnimator(len(kids)), None, None
        self.add_events(Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK)
        self.connect("draw", self.on_draw)
        self.connect("motion-notify-event", self.on_motion)
        self.connect("leave-notify-event", lambda *_: self.set_hover(None))
        self.connect("button-press-event", self.on_press)
        self.add_tick_callback(self.on_tick)
        self.popover = None

    def on_tick(self, w, clock):
        now = clock.get_frame_time() / 1e6
        dt = 0.016 if self.last is None else now - self.last
        self.last = now
        done = self.anim.step(dt)
        self.queue_draw()
        return not done

    def pos(self, i):
        u, v, a = self.layout[i]
        p = self.anim.p[i]
        x, y = F.to_xy(self.edge, u * p, v * p, self.length, self.half)
        return x, y, a, p

    def on_draw(self, w, cr):
        win = self.get_window()
        scale = self.get_scale_factor()
        order = sorted(range(len(self.kids)), key=lambda i: i == self.hover)
        for i in order:
            x, y, a, p = self.pos(i)
            if p <= 0.01:
                continue
            ch = self.kids[i]
            sz = self.icon * (0.5 + 0.5 * min(p, 1.12)) * (1.14 if i == self.hover else 1.0)
            res = self.folder.child_surface(ch, int(self.icon), scale, win)
            cr.save()
            cr.translate(x, y)
            cr.rotate(a * 0.7 * min(p, 1.0))
            cr.push_group()
            if res and res[0] is not None:
                surf, lw, lh = res
                cr.translate(-sz / 2, -sz / 2); cr.scale(sz / lw, sz / lh); cr.set_source_surface(surf, 0, 0); cr.paint()
            else:
                cr.translate(-sz / 2, -sz / 2); tile(cr, sz, (0.4, 0.45, 0.6, 1), (0.25, 0.3, 0.45, 1))
                text(cr, ch["name"][:1].upper(), sz / 2, sz / 2, sz * 0.5, (1, 1, 1, 1), True)
            cr.pop_group_to_source()
            cr.paint_with_alpha(min(1.0, p * 1.6))
            cr.restore()
        if self.hover is not None and self.anim.p[self.hover] > 0.8:
            x, y, _a, _p = self.pos(self.hover)
            ox, oy = F.OUTWARD[self.edge]
            lx, ly = x + ox * self.icon * 0.78, y + oy * self.icon * 0.78
            name = self.kids[self.hover]["name"][:28]
            tw = max(40, len(name) * 7 + 18)
            cr.save()
            rrect(cr, lx - tw / 2, ly - 11, tw, 22, 9); cr.set_source_rgba(0.1, 0.1, 0.12, 0.9); cr.fill()
            cr.restore()
            text(cr, name, lx, ly, 12, (1, 1, 1, 1))
        return False

    def hit(self, ex, ey):
        best, bd = None, self.icon * 0.58
        for i in range(len(self.kids)):
            x, y, _a, p = self.pos(i)
            d = math.hypot(ex - x, ey - y)
            if p > 0.5 and d < bd:
                best, bd = i, d
        return best

    def set_hover(self, i):
        if i != self.hover:
            self.hover = i
            self.queue_draw()

    def on_motion(self, w, ev):
        self.set_hover(self.hit(ev.x, ev.y))
        return False

    def on_press(self, w, ev):
        i = self.hit(ev.x, ev.y)
        if i is not None and ev.button in (1, 2):
            self.host.open_child(self.folder, self.kids[i])
            if self.popover is not None:
                self.popover.popdown()
        return True
