#!/usr/bin/env python3
"""GlassDock: floating dock for Wayland (Sway/SwayFX) using GTK3 + gtk-layer-shell.

All dock-facing settings are read through the getter `g(<dotted key>)` so that
tests/test_coverage.py can verify every schema setting is consumed here.
"""
import colorsys
import math
import os
import shlex
import shutil
import signal
import subprocess
import sys
import time

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
try:
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import GtkLayerShell
except (ValueError, ImportError):  # reported at startup with install hint
    GtkLayerShell = None
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk, Pango, PangoCairo  # noqa: E402

import cairo  # noqa: E402

from . import __version__  # noqa: E402
from .core import config as C  # noqa: E402
from .core import control, extensions as E, model as M, sway  # noqa: E402
from .core.envutil import child_env  # noqa: E402
from .core.colors import parse_color, with_alpha  # noqa: E402
from .core.desktop import expand_exec, load_entries  # noqa: E402
from .core.icons import candidate_names, find_icon_file, icon_roots  # noqa: E402

NAMESPACE = "glassdock"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def getter(cfg):
    return lambda key: C.get_path(cfg, key)


def log(*a):
    print("[glassdock]", *a, file=sys.stderr, flush=True)


# ------------------------------------------------------------------ drawing

def rrect(cr, x, y, w, h, r):
    r = max(0.0, min(r, w / 2.0, h / 2.0))
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


def _tile(cr, x, y, s, top, bottom, pct=None):
    rrect(cr, x, y, s, s, s * (pct / 100.0 if pct else 0.23))
    pat = cairo.LinearGradient(x, y, x, y + s)
    pat.add_color_stop_rgb(0, *top)
    pat.add_color_stop_rgb(1, *bottom)
    cr.set_source(pat)
    cr.fill()


def draw_builtin(cr, kind, x, y, s, pct=None):
    """Built-in glyph icons so special items never depend on the icon theme."""
    if kind == "apps":
        _tile(cr, x, y, s, (0.36, 0.40, 0.46), (0.22, 0.25, 0.30), pct)
        cell = s * 0.16
        gap = s * 0.085
        start = x + (s - (3 * cell + 2 * gap)) / 2
        cr.set_source_rgba(1, 1, 1, 0.95)
        for i in range(3):
            for j in range(3):
                rrect(cr, start + i * (cell + gap), y + (s - (3 * cell + 2 * gap)) / 2 + j * (cell + gap),
                      cell, cell, cell * 0.3)
                cr.fill()
    elif kind == "trash":
        _tile(cr, x, y, s, (0.50, 0.54, 0.62), (0.32, 0.36, 0.43), pct)
        cr.set_source_rgba(1, 1, 1, 0.95)
        bw, bh = s * 0.36, s * 0.38
        bx, by = x + (s - bw) / 2, y + s * 0.38
        cr.move_to(bx, by)
        cr.line_to(bx + bw, by)
        cr.line_to(bx + bw * 0.88, by + bh)
        cr.line_to(bx + bw * 0.12, by + bh)
        cr.close_path()
        cr.fill()
        rrect(cr, bx - s * 0.05, by - s * 0.07, bw + s * 0.10, s * 0.05, s * 0.02)
        cr.fill()
        rrect(cr, bx + bw * 0.32, by - s * 0.12, bw * 0.36, s * 0.05, s * 0.02)
        cr.fill()



def draw_extension_icon(cr, kind, x, y, s, pct=None):
    """Draw dependency-free glyphs for the built-in widgets and folders."""
    top, bottom = (0.40, 0.50, 0.68), (0.20, 0.27, 0.40)
    if kind == "calendar":
        top, bottom = (0.42, 0.52, 0.66), (0.19, 0.25, 0.37)
    elif kind == "music":
        top, bottom = (0.51, 0.40, 0.72), (0.27, 0.20, 0.43)
    elif kind == "folder":
        top, bottom = (0.83, 0.67, 0.36), (0.61, 0.42, 0.18)
    _tile(cr, x, y, s, top, bottom, pct)
    cr.save()
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    cr.set_source_rgba(1, 1, 1, 0.94)
    if kind == "clock":
        cx, cy, r = x + s / 2, y + s / 2, s * 0.30
        cr.set_line_width(max(1.5, s * 0.045))
        cr.arc(cx, cy, r, 0, 2 * math.pi)
        cr.stroke()
        cr.move_to(cx, cy)
        cr.line_to(cx, cy - r * 0.64)
        cr.move_to(cx, cy)
        cr.line_to(cx + r * 0.52, cy + r * 0.12)
        cr.stroke()
    elif kind == "calendar":
        bx, by, bw, bh = x + s * 0.21, y + s * 0.22, s * 0.58, s * 0.56
        rrect(cr, bx, by, bw, bh, s * 0.06)
        cr.set_line_width(max(1.0, s * 0.035))
        cr.stroke()
        cr.move_to(bx, by + bh * 0.22)
        cr.line_to(bx + bw, by + bh * 0.22)
        cr.stroke()
        for row in range(2):
            for col in range(3):
                cx = bx + bw * (0.23 + col * 0.27)
                cy = by + bh * (0.42 + row * 0.25)
                cr.rectangle(cx, cy, s * 0.045, s * 0.045)
                cr.fill()
        for cx in (bx + bw * 0.28, bx + bw * 0.72):
            cr.move_to(cx, by - s * 0.035)
            cr.line_to(cx, by + bh * 0.11)
        cr.stroke()
    elif kind == "music":
        cr.set_line_width(max(2.0, s * 0.06))
        cr.move_to(x + s * 0.61, y + s * 0.27)
        cr.line_to(x + s * 0.61, y + s * 0.63)
        cr.line_to(x + s * 0.42, y + s * 0.68)
        cr.stroke()
        cr.move_to(x + s * 0.61, y + s * 0.29)
        cr.line_to(x + s * 0.77, y + s * 0.25)
        cr.line_to(x + s * 0.77, y + s * 0.60)
        cr.stroke()
        cr.arc(x + s * 0.38, y + s * 0.68, s * 0.085, 0, 2 * math.pi)
        cr.fill()
        cr.arc(x + s * 0.73, y + s * 0.61, s * 0.085, 0, 2 * math.pi)
        cr.fill()
    elif kind == "folder":
        cr.move_to(x + s * 0.18, y + s * 0.34)
        cr.line_to(x + s * 0.44, y + s * 0.34)
        cr.line_to(x + s * 0.52, y + s * 0.43)
        cr.line_to(x + s * 0.80, y + s * 0.43)
        cr.line_to(x + s * 0.75, y + s * 0.72)
        cr.line_to(x + s * 0.22, y + s * 0.72)
        cr.close_path()
        cr.fill()
    cr.restore()


def draw_letter_tile(cr, name, x, y, s, pct=None):
    h = (sum(ord(ch) for ch in name) % 360) / 360.0
    top = colorsys.hls_to_rgb(h, 0.58, 0.55)
    bottom = colorsys.hls_to_rgb(h, 0.40, 0.55)
    _tile(cr, x, y, s, top, bottom, pct)
    layout = PangoCairo.create_layout(cr)
    layout.set_font_description(Pango.FontDescription("Sans Bold %d" % max(8, int(s * 0.34 * 0.75))))
    layout.set_text((name.strip()[:1] or "?").upper(), -1)
    tw, th = layout.get_pixel_size()
    cr.set_source_rgba(1, 1, 1, 0.95)
    cr.move_to(x + (s - tw) / 2, y + (s - th) / 2)
    PangoCairo.show_layout(cr, layout)


class IconCache:
    """Loads crisp icon surfaces at the largest size needed and caches them.

    Lookup order for every candidate name (see core.icons.candidate_names):
    absolute path -> Gtk icon theme -> our own scan of user/flatpak/snap/pixmaps
    directories. Failed lookups are retried after a while, so an icon that
    appears later (app installed, theme changed) is picked up.
    """

    RETRY = 30.0

    def __init__(self):
        self.cache = {}
        theme = Gtk.IconTheme.get_default()
        try:
            have = set(theme.get_search_path())
            for root in icon_roots()[0]:
                if os.path.isdir(root) and root not in have:
                    theme.append_search_path(root)
                    have.add(root)
        except (GLib.Error, TypeError):
            pass
        theme.connect("changed", lambda *_: self.cache.clear())

    def _cached(self, key, loader):
        hit = self.cache.get(key)
        if hit is not None:
            res, stamp = hit
            if res is not None or time.monotonic() - stamp < self.RETRY:
                return res
        res = loader()
        self.cache[key] = (res, time.monotonic())
        return res

    def get(self, icon, px, scale, window):
        return self._cached((icon, px, scale), lambda: self._load(icon, px, scale, window))

    def get_item(self, it, px, scale, window):
        sig = tuple(sorted({(w.app_id or "", w.wm_class or "") for w in it.windows}))
        key = ("item", it.key, it.icon, sig, px, scale)

        def load():
            for name in candidate_names(it.icon, it.entry, it.windows, it.name):
                res = self.get(name, px, scale, window)
                if res is not None:
                    return res
            return None
        return self._cached(key, load)

    def _load(self, icon, px, scale, window):
        if not icon:
            return None
        surf = None
        path = None
        if os.path.isabs(icon):
            if os.path.exists(icon):
                path = icon
            else:
                icon = os.path.basename(icon)
        if path is None:
            name = icon
            for ext in IconCacheExts:
                if name.lower().endswith(ext):
                    name = name[:-len(ext)]
            theme = Gtk.IconTheme.get_default()
            for cand in (name, name.lower()):
                try:
                    if theme.has_icon(cand):
                        surf = theme.load_surface(cand, px, scale, window, Gtk.IconLookupFlags.FORCE_SIZE)
                except GLib.Error:
                    surf = None
                if surf is not None:
                    break
            if surf is None:
                path = find_icon_file(icon)
        if surf is None and path:
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file_at_size(path, px * scale, px * scale)
                surf = Gdk.cairo_surface_create_from_pixbuf(pb, scale, window)
            except GLib.Error:
                surf = None
        if surf is None:
            return None
        return (surf, surf.get_width() / float(scale), surf.get_height() / float(scale))


IconCacheExts = (".png", ".svg", ".xpm", ".svgz")


# ------------------------------------------------------------------ launching

def toast(msg):
    log(msg)
    if shutil.which("notify-send"):
        try:
            subprocess.Popen(["notify-send", "-a", "GlassDock", "GlassDock", msg],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass


def spawn(argv):
    try:
        subprocess.Popen(argv, cwd=os.path.expanduser("~"), start_new_session=True, env=child_env(),
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except (OSError, ValueError) as exc:
        toast("Could not start %s: %s" % (argv[0] if argv else "?", exc))
        return False


# ------------------------------------------------------------------ dock window

class DockWindow(Gtk.Window):
    def __init__(self, app, output):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.app = app
        self.output = output
        self.items = []
        self.cfg = None
        self.g = None
        self.geo = None
        self.scale_cur = {}
        self.targets = {}
        self.pointer = None
        self.pointer_inside = False
        self.menu_open = False
        self.fullscreen = False
        self.overlapping = False
        self.manual = None            # None = automatic; True/False = forced by ctl
        self.vis_target = True
        self.vis_pending = None
        self.vis_timer = None
        self.progress = 1.0
        self.prog_anim = None         # [from, to, start_time or None]
        self.bounce = {}
        self.hover_key = None
        self.press_key = None
        self.press_item = None
        self.press_m = 0.0
        self.press_grab = 0.0
        self.drag = None
        self.tick_id = None
        self.last_tick = None
        self.region_sig = None

        self.set_title("GlassDock")
        self.set_decorated(False)
        self.set_app_paintable(True)
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual is not None:
            self.set_visual(visual)
        self.get_style_context().add_class("glassdock")

        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_namespace(self, NAMESPACE)
        if hasattr(GtkLayerShell, "set_keyboard_mode"):
            GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.NONE)
        else:
            GtkLayerShell.set_keyboard_interactivity(self, False)
        mon = app.find_gdk_monitor(output["rect"])
        if mon is not None:
            GtkLayerShell.set_monitor(self, mon)

        self.area = Gtk.DrawingArea()
        self.area.add_events(Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.ENTER_NOTIFY_MASK
                             | Gdk.EventMask.LEAVE_NOTIFY_MASK | Gdk.EventMask.BUTTON_PRESS_MASK
                             | Gdk.EventMask.BUTTON_RELEASE_MASK)
        self.area.connect("draw", self.on_draw)
        self.area.connect("motion-notify-event", self.on_motion)
        self.area.connect("enter-notify-event", self.on_enter)
        self.area.connect("leave-notify-event", self.on_leave)
        self.area.connect("button-press-event", self.on_press)
        self.area.connect("button-release-event", self.on_release)
        self.add(self.area)
        self.connect("realize", lambda *_: self.update_region(force=True))

    # ---------------------------------------------------------- configuration
    def apply(self, cfg, items, windows, fullscreen):
        first = self.cfg is None
        self.cfg = cfg
        self.g = g = getter(cfg)
        self.items = items
        self.fullscreen = fullscreen
        kinds = [i.kind for i in items]
        shadow = g("appearance.shadow_size") if g("appearance.shadow") else 0
        self.geo = geo = M.compute_geometry(
            kinds, icon=g("size.icon_size"), spacing=g("size.spacing"), padding=g("size.padding"),
            margin=g("size.margin"), shadow_size=shadow, edge=g("position.edge"),
            alignment=g("position.alignment"), indicator_size=g("indicators.size"),
            indicator_style=g("indicators.style"), magnify=g("animation.magnify"),
            factor=g("animation.magnify_factor"), reach=g("animation.magnify_range"),
            bounce=g("animation.launch_bounce"), labels=g("appearance.show_labels"))

        L = GtkLayerShell
        L.set_layer(self, L.Layer.OVERLAY if g("behavior.layer") == "overlay" else L.Layer.TOP)
        edge = geo.edge
        edges = {"bottom": L.Edge.BOTTOM, "top": L.Edge.TOP, "left": L.Edge.LEFT, "right": L.Edge.RIGHT}
        for e in edges.values():
            L.set_anchor(self, e, False)
            L.set_margin(self, e, 0)
        L.set_anchor(self, edges[edge], True)
        L.set_margin(self, edges[edge], geo.layer_margin)
        if geo.alignment != "center":
            if M.is_horizontal(edge):
                side = L.Edge.LEFT if geo.alignment == "start" else L.Edge.RIGHT
            else:
                side = L.Edge.TOP if geo.alignment == "start" else L.Edge.BOTTOM
            L.set_anchor(self, side, True)
            L.set_margin(self, side, geo.side_margin)

        w, h = geo.win_size
        self.set_size_request(w, h)
        self.set_default_size(w, h)
        if self.get_realized():
            self.resize(w, h)
        L.set_exclusive_zone(self, M.exclusive_zone(geo, g("behavior.exclusive_zone"), g("behavior.autohide")))

        # drop animation state of items that vanished
        keys = {i.key for i in items}
        self.scale_cur = {k: v for k, v in self.scale_cur.items() if k in keys}
        for it in items:  # a launching app stops bouncing once its window appears
            if it.running and it.key in self.bounce:
                del self.bounce[it.key]

        # overlap (intellihide) uses the resting dock rectangle in global coordinates
        rect = M.dock_global_rect(self.output["rect"], edge, geo.alignment, geo.margin, geo.base_len, geo.thick)
        self.overlapping = M.overlapping_windows(rect, windows, self.output["name"])

        self.update_targets()
        if first:
            self.show_all()
            self.vis_target = self.compute_want()
            self.progress = 1.0 if self.vis_target else 0.0
        self.reevaluate()
        self.update_region(force=True)
        self.ensure_tick()
        self.queue_draw()

    # ------------------------------------------------------------- visibility
    def compute_want(self):
        g = self.g
        if self.manual is not None:
            return self.manual
        return M.decide_visibility(
            mode=g("behavior.autohide"), fullscreen=self.fullscreen,
            hide_on_fullscreen=g("behavior.hide_on_fullscreen"), overlapping=self.overlapping,
            pointer_inside=self.pointer_inside, menu_open=self.menu_open)

    def reevaluate(self):
        if self.g is None:
            return
        want = self.compute_want()
        if self.vis_pending is not None and self.vis_pending != want:
            if self.vis_timer:
                GLib.source_remove(self.vis_timer)
            self.vis_timer, self.vis_pending = None, None
        if want == self.vis_target or self.vis_pending == want:
            return
        g = self.g
        instant = (self.manual is not None or g("behavior.autohide") == "off"
                   or (self.fullscreen and g("behavior.hide_on_fullscreen")))
        delay = 0 if instant else (g("behavior.show_delay") if want else g("behavior.hide_delay"))
        if delay <= 0:
            self.set_visible_target(want)
        else:
            self.vis_pending = want
            self.vis_timer = GLib.timeout_add(delay, self._vis_fire, want)

    def _vis_fire(self, want):
        self.vis_timer, self.vis_pending = None, None
        self.set_visible_target(want)
        return False

    def set_visible_target(self, want):
        self.vis_target = want
        dur = self.g("animation.duration")
        if dur <= 0:
            self.progress = 1.0 if want else 0.0
            self.prog_anim = None
        else:
            self.prog_anim = [self.progress, 1.0 if want else 0.0, None]
        self.update_region(force=True)
        self.ensure_tick()
        self.queue_draw()

    # ----------------------------------------------------------------- layout
    def layout(self):
        geo = self.geo
        kinds = [i.kind for i in self.items]
        scales = [self.scale_cur.get(i.key, 1.0) for i in self.items]
        sizes = M.slot_sizes(kinds, geo.icon, scales)
        pos, total = M.base_layout(sizes, geo.spacing)
        length = 2 * geo.padding + total
        return pos, sizes, length, M.dock_origin(geo, length)

    def update_targets(self):
        g, geo = self.g, self.geo
        kinds = [i.kind for i in self.items]
        base_sizes = M.slot_sizes(kinds, geo.icon)
        pos, total = M.base_layout(base_sizes, geo.spacing)
        slot = None
        if self.pointer is not None and self.progress > 0.99 and self.drag is None:
            m0 = M.dock_origin(geo, 2 * geo.padding + total)
            slot = M.pointer_slot(self.pointer[0] - (m0 + geo.padding), pos, base_sizes)
        scales = M.target_scales(kinds, slot, g("animation.magnify_factor"), g("animation.magnify_range"),
                                 g("animation.magnify"))
        self.targets = {it.key: sc for it, sc in zip(self.items, scales)}

    def item_rect(self, idx, pos, sizes, m0):
        """Canonical rect (m, c, size) of icon idx (before slide offset)."""
        geo = self.geo
        m = m0 + geo.padding + pos[idx]
        c = geo.c0 + geo.padding + geo.ind_room
        return m, c, sizes[idx]

    def item_at(self, m, c):
        geo = self.geo
        pos, sizes, length, m0 = self.layout()
        for i, it in enumerate(self.items):
            if it.kind == "separator":
                continue
            mm, cc, s = self.item_rect(i, pos, sizes, m0)
            lo = mm - geo.spacing / 2.0
            hi = mm + s + geo.spacing / 2.0
            top = max(geo.c0 + geo.thick, cc + s)
            if lo <= m < hi and 0 <= c <= top:
                return it
        return None

    # -------------------------------------------------------- input region
    def update_region(self, force=False):
        win = self.get_window()
        if win is None or self.geo is None:
            return
        geo, g = self.geo, self.g
        W, H = self.get_size()
        rects = []
        hidden = (not self.vis_target) and self.progress <= 0.001
        if hidden:
            if g("behavior.autohide") != "off" and self.manual is None and not (
                    self.fullscreen and g("behavior.hide_on_fullscreen")):
                pos, sizes, length, m0 = self.layout()
                rects.append(M.place(geo.edge, W, H, m0, 0, length, 3))
        else:
            pos, sizes, length, m0 = self.layout()
            rects.append(M.place(geo.edge, W, H, m0, geo.c0, length, geo.thick))
            for i, it in enumerate(self.items):
                sc = self.scale_cur.get(it.key, 1.0)
                if it.kind != "separator" and sc > 1.001:
                    m, c, s = self.item_rect(i, pos, sizes, m0)
                    rects.append(M.place(geo.edge, W, H, m, c, s, s))
        ints = [(int(math.floor(x)), int(math.floor(y)), int(math.ceil(w)) + 1, int(math.ceil(h)) + 1)
                for x, y, w, h in rects]
        sig = (tuple(ints), W, H)
        if sig == self.region_sig and not force:
            return
        self.region_sig = sig
        region = cairo.Region()
        for x, y, w, h in ints:
            region.union(cairo.RectangleInt(x, y, w, h))
        win.input_shape_combine_region(region, 0, 0)

    # --------------------------------------------------------------- animation
    def ensure_tick(self):
        if self.tick_id is None:
            self.last_tick = None
            self.tick_id = self.add_tick_callback(self.on_tick)

    def on_tick(self, widget, clock):
        now = clock.get_frame_time() / 1e6
        dt = 0.0 if self.last_tick is None else min(0.1, now - self.last_tick)
        self.last_tick = now
        g = self.g
        busy = False
        dur = g("animation.duration") / 1000.0
        tau = max(dur / 4.0, 1e-3)
        for it in self.items:
            cur = self.scale_cur.get(it.key, 1.0)
            tgt = self.targets.get(it.key, 1.0)
            if dur <= 0:
                new = tgt
            else:
                new = cur + (tgt - cur) * (1.0 - math.exp(-dt / tau))
            if abs(new - tgt) < 0.002:
                new = tgt
            else:
                busy = True
            self.scale_cur[it.key] = new
        if self.prog_anim is not None:
            frm, to, start = self.prog_anim
            if start is None:
                self.prog_anim[2] = start = now
            t = (now - start) / dur if dur > 0 else 1.0
            self.progress = frm + (to - frm) * M.ease(g("animation.easing"), t)
            if t >= 1.0:
                self.progress = to
                self.prog_anim = None
                self.update_targets()
            else:
                busy = True
        for key in list(self.bounce):
            if now - self.bounce[key] > 4.0 and self.bounce[key] > 0:
                del self.bounce[key]
        if self.bounce:
            busy = True
        self.update_region()
        self.queue_draw()
        if not busy:
            self.tick_id = None
            self.last_tick = None
            return False
        return True

    def start_bounce(self, key):
        self.bounce[key] = -1.0  # real start time is stamped on the next draw
        self.ensure_tick()

    def bounce_offset(self, key, now):
        start = self.bounce.get(key)
        if start is None:
            return 0.0
        if start < 0:
            self.bounce[key] = start = now
        phase = now - start
        return self.geo.icon * 0.40 * abs(math.sin(phase * math.pi * 1.6)) * max(0.0, 1.0 - phase / 4.0)

    # -------------------------------------------------------------------- draw
    def on_draw(self, widget, cr):
        if self.geo is None or self.g is None:
            return False
        g, geo = self.g, self.geo
        W, H = widget.get_allocated_width(), widget.get_allocated_height()
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        if self.progress <= 0.001 and not self.vis_target:
            return False
        now = GLib.get_monotonic_time() / 1e6
        edge = geo.edge
        off = (1.0 - self.progress) * (geo.c0 + geo.thick + geo.shadow + 4)
        pos, sizes, length, m0 = self.layout()
        px, py, pw, ph = M.place(edge, W, H, m0, geo.c0 - off, length, geo.thick)
        radius = g("appearance.corner_radius")
        icon_pct = g("appearance.icon_radius")

        # shadow (stacked translucent layers, clipped so it never tints the glass)
        S = geo.shadow
        if g("appearance.shadow") and S > 0:
            cr.save()
            cr.rectangle(0, 0, W, H)
            rrect(cr, px, py, pw, ph, radius)
            cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
            cr.clip()
            peak = min(0.95, g("appearance.shadow_opacity"))
            a = 1.0 - (1.0 - peak) ** (1.0 / S)
            for k in range(S, 0, -1):
                rrect(cr, px - k, py - k, pw + 2 * k, ph + 2 * k, radius + k)
                cr.set_source_rgba(0, 0, 0, a)
                cr.fill()
            cr.restore()

        # panel
        rrect(cr, px, py, pw, ph, radius)
        c1 = with_alpha(parse_color(g("appearance.bg_color")), g("appearance.bg_opacity"))
        if g("appearance.bg_gradient"):
            c2 = with_alpha(parse_color(g("appearance.bg_color2")), g("appearance.bg_opacity"))
            d = g("appearance.gradient_direction")
            if d == "horizontal":
                pat = cairo.LinearGradient(px, py, px + pw, py)
            elif d == "diagonal":
                pat = cairo.LinearGradient(px, py, px + pw, py + ph)
            else:
                pat = cairo.LinearGradient(px, py, px, py + ph)
            pat.add_color_stop_rgba(0, *c1)
            pat.add_color_stop_rgba(1, *c2)
            cr.set_source(pat)
        else:
            cr.set_source_rgba(*c1)
        cr.fill()
        bw = g("appearance.border_width")
        if bw > 0:
            rrect(cr, px + bw / 2, py + bw / 2, pw - bw, ph - bw, max(0, radius - bw / 2))
            cr.set_source_rgba(*with_alpha(parse_color(g("appearance.border_color")),
                                           g("appearance.border_opacity")))
            cr.set_line_width(bw)
            cr.stroke()

        if self.progress < 0.02:
            return False
        scale_dev = self.get_scale_factor()
        max_px = int(math.ceil(geo.icon * (g("animation.magnify_factor") if g("animation.magnify") else 1.0)))
        icons = self.app.icons
        ind_style = g("indicators.style")
        hover_item = None

        for i, it in self.draw_order():
            m, c, s = self.item_rect(i, pos, sizes, m0)
            c -= off
            if self.drag is not None and it.key == self.drag["key"]:
                m = self.drag_m(m0, pos, sizes)
            if it.kind == "separator":
                x, y, w, h = M.place(edge, W, H, m + s / 2 - 0.75, c + geo.icon * 0.12, 1.5, geo.icon * 0.76)
                cr.set_source_rgba(*with_alpha(parse_color(g("appearance.border_color")), 0.35))
                cr.rectangle(x, y, w, h)
                cr.fill()
                continue
            lift = self.bounce_offset(it.key, now)
            x, y, w, h = M.place(edge, W, H, m, c + lift, s, s)
            if it.special in ("apps", "trash"):
                draw_builtin(cr, it.special, x, y, s, icon_pct)
            elif it.kind == "widget":
                draw_extension_icon(cr, it.extension, x, y, s, icon_pct)
            elif it.kind == "folder" and it.icon in ("", "folder", "folder-symbolic"):
                draw_extension_icon(cr, "folder", x, y, s, icon_pct)
            else:
                res = icons.get_item(it, max_px, scale_dev, self.get_window())
                if res is not None:
                    surf, lw, lh = res
                    cr.save()
                    if icon_pct > 0:
                        rrect(cr, x, y, s, s, s * icon_pct / 100.0)
                        cr.clip()
                    cr.translate(x, y)
                    cr.scale(s / lw, s / lh)
                    cr.set_source_surface(surf, 0, 0)
                    cr.paint()
                    cr.restore()
                else:
                    draw_letter_tile(cr, it.name, x, y, s, icon_pct)
            if g("extensions.badges_enabled") and it.badge_count > 0:
                badge = E.badge_text(it.badge_count, g("extensions.badge_max_count"))
                if badge:
                    layout_badge = PangoCairo.create_layout(cr)
                    layout_badge.set_font_description(Pango.FontDescription(
                        "Sans Bold %d" % max(7, int(s * 0.17))))
                    layout_badge.set_text(badge, -1)
                    tw, th = layout_badge.get_pixel_size()
                    bw, bh = max(s * 0.28, tw + s * 0.14), max(s * 0.25, th + s * 0.08)
                    bx, by = x + s * 0.58, y + s * 0.02
                    rrect(cr, bx, by, bw, bh, bh / 2.0)
                    cr.set_source_rgba(0.92, 0.20, 0.27, 1.0)
                    cr.fill()
                    cr.set_source_rgba(1, 1, 1, 1)
                    cr.move_to(bx + (bw - tw) / 2.0, by + (bh - th) / 2.0)
                    PangoCairo.show_layout(cr, layout_badge)
            if it.key == self.hover_key:
                hover_text = it.extension_text if it.extension_text else it.name
                hover_item = (it, m + s / 2.0, c + s, hover_text)

            # running indicators
            marks = M.indicator_layout(len(it.windows), it.active, ind_style)
            if marks:
                isz = g("indicators.size")
                col_n = parse_color(g("indicators.color"))
                col_a = parse_color(g("indicators.active_color"))
                base_c = geo.c0 + geo.padding + (geo.ind_room - isz) / 2.0 - off - 1
                mid = m + s / 2.0
                if ind_style == "line":
                    lw_ = max(8.0, geo.icon * (0.5 if marks[0] == "active" else 0.3))
                    rx, ry, rw, rh = M.place(edge, W, H, mid - lw_ / 2, base_c, lw_, isz)
                    rrect(cr, rx, ry, rw, rh, min(rw, rh) / 2.0)
                    cr.set_source_rgba(*(col_a if marks[0] == "active" else col_n))
                    cr.fill()
                else:
                    gap = isz + 3
                    start = mid - (len(marks) - 1) * gap / 2.0
                    for k, mk in enumerate(marks):
                        rx, ry, rw, rh = M.place(edge, W, H, start + k * gap - isz / 2.0, base_c, isz, isz)
                        cr.arc(rx + rw / 2.0, ry + rh / 2.0, isz / 2.0, 0, 2 * math.pi)
                        col = (1.0, 0.35, 0.35, 1.0) if it.urgent else (col_a if mk == "active" else col_n)
                        cr.set_source_rgba(*col)
                        cr.fill()

        if self.drag is not None:
            _, lm = self.drop_target(self.drag["pm"], self.drag["key"])
            mx, my, mw, mh = M.place(edge, W, H, lm - 1.0, geo.c0 + geo.padding + geo.ind_room - off,
                                     2.0, geo.icon)
            cr.set_source_rgba(*parse_color(g("indicators.active_color")))
            rrect(cr, mx, my, mw, mh, 1.0)
            cr.fill()

        if hover_item is not None and g("appearance.show_labels") and self.progress > 0.95 \
                and self.drag is None:
            self.draw_label(cr, W, H, hover_item[3], hover_item[1], hover_item[2])
        return False

    # ------------------------------------------------------------ drag & drop
    def draw_order(self):
        """Items in paint order: the one being dragged is painted last (on top)."""
        order = list(enumerate(self.items))
        if self.drag is not None:
            order.sort(key=lambda p: p[1].key == self.drag["key"])
        return order

    def drag_m(self, m0, pos, sizes):
        d = self.drag
        lo = m0 + self.geo.padding
        end = (pos[-1] + sizes[-1]) if pos else 0.0
        hi = max(lo, lo + end - d["size"])
        return max(lo, min(hi, d["pm"] - d["grab"]))

    def drop_target(self, pm, key):
        """-> (config index to insert before or None for 'at the end', marker position)."""
        geo = self.geo
        pos, sizes, length, m0 = self.layout()
        base = m0 + geo.padding
        last_end = None
        for i, it in enumerate(self.items):
            if it.key == key or it.cfg_index < 0:
                continue
            start = base + pos[i]
            if pm < start + sizes[i] / 2.0:
                return it.cfg_index, start - geo.spacing / 2.0
            last_end = start + sizes[i]
        return None, (last_end if last_end is not None else base) + geo.spacing / 2.0

    def update_drag(self, ev):
        if self.press_item is None or self.pointer is None:
            return
        if not (ev.state & Gdk.ModifierType.BUTTON1_MASK):
            if self.drag is not None:
                self.cancel_drag()
            return
        if self.drag is None:
            it = self.press_item
            if abs(self.pointer[0] - self.press_m) < 8 or it.cfg_index < 0 or \
                    it.kind == "separator" or self.menu_open:
                return
            self.drag = {"key": it.key, "grab": self.press_grab, "pm": self.pointer[0],
                         "size": self.geo.icon}
        else:
            self.drag["pm"] = self.pointer[0]

    def cancel_drag(self):
        self.drag = None
        self.press_key = None
        self.press_item = None
        self.update_targets()
        self.queue_draw()

    def finish_drag(self, pm):
        d = self.drag
        self.drag = None
        self.press_key = None
        self.press_item = None
        if d is not None:
            before, _ = self.drop_target(pm, d["key"])
            cur = next((i for i in self.items if i.key == d["key"]), None)
            if cur is not None and cur.cfg_index >= 0:
                self.app.move_item(cur.cfg_index, before)
        self.update_targets()
        self.ensure_tick()
        self.queue_draw()

    def draw_label(self, cr, W, H, text, mid, top_c):
        g, geo = self.g, self.geo
        layout = PangoCairo.create_layout(cr)
        layout.set_font_description(Pango.FontDescription("Sans 10"))
        layout.set_width(240 * Pango.SCALE)
        layout.set_ellipsize(Pango.EllipsizeMode.END)
        layout.set_text(text, -1)
        tw, th = layout.get_pixel_size()
        bw_, bh_ = tw + 20, th + 12
        horiz = M.is_horizontal(geo.edge)
        mlen, clen = (bw_, bh_) if horiz else (bh_, bw_)
        m = mid - mlen / 2.0
        m = max(0.0, min(m, (W if horiz else H) - mlen))
        x, y, w, h = M.place(geo.edge, W, H, m, top_c + 10, mlen, clen)
        rrect(cr, x, y, w, h, 9)
        cr.set_source_rgba(*with_alpha(parse_color(g("appearance.label_bg")), 0.92))
        cr.fill_preserve()
        cr.set_source_rgba(1, 1, 1, 0.14)
        cr.set_line_width(1)
        cr.stroke()
        cr.set_source_rgba(*parse_color(g("appearance.label_color")))
        cr.move_to(x + 10, y + 6)
        PangoCairo.show_layout(cr, layout)

    # ------------------------------------------------------------------ events
    def canon(self, ev):
        W, H = self.area.get_allocated_width(), self.area.get_allocated_height()
        return M.unplace(self.geo.edge, W, H, ev.x, ev.y)

    def on_enter(self, w, ev):
        self.pointer_inside = True
        self.pointer = self.canon(ev)
        self.after_pointer()
        self.reevaluate()
        return False

    def on_motion(self, w, ev):
        self.pointer_inside = True
        self.pointer = self.canon(ev)
        self.update_drag(ev)
        self.after_pointer()
        return False

    def on_leave(self, w, ev):
        if self.menu_open or self.drag is not None:
            return False
        self.pointer_inside = False
        self.pointer = None
        self.after_pointer()
        self.reevaluate()
        return False

    def after_pointer(self):
        if self.geo is None:
            return
        self.update_targets()
        it = self.item_at(*self.pointer) if self.pointer else None
        key = it.key if (it and self.drag is None) else None
        if key != self.hover_key:
            self.hover_key = key
        self.ensure_tick()
        self.queue_draw()

    def on_press(self, w, ev):
        if self.geo is None:
            return True
        m, c = self.canon(ev)
        it = self.item_at(m, c)
        if ev.button == 3:
            self.show_menu(it, ev)
        elif ev.button in (1, 2):
            self.press_key = it.key if it else None
            self.press_item = it
            self.drag = None
            if it is not None:
                pos, sizes, length, m0 = self.layout()
                mm, _cc, _ss = self.item_rect(self.items.index(it), pos, sizes, m0)
                self.press_m = m
                self.press_grab = m - mm
        return True

    def on_release(self, w, ev):
        if self.geo is None or ev.button not in (1, 2):
            return True
        if self.drag is not None:
            self.finish_drag(self.canon(ev)[0])
            return True
        it = self.item_at(*self.canon(ev))
        if it is not None and it.key == self.press_key:
            if it.kind == "folder":
                self.show_folder_menu(it, ev)
            elif it.kind == "widget" and it.extension in ("clock", "calendar"):
                self.show_calendar_menu(it, ev)
            else:
                new = ev.button == 2 or bool(ev.state & Gdk.ModifierType.SHIFT_MASK)
                self.app.activate(it, new_instance=new, dock=self)
        self.press_key = None
        self.press_item = None
        return True

    # -------------------------------------------------------------------- menu
    def show_menu(self, item, ev):
        menu = Gtk.Menu()

        def add(label, cb, sensitive=True):
            mi = Gtk.MenuItem(label=label)
            mi.set_sensitive(sensitive)
            mi.connect("activate", lambda *_: cb())
            menu.append(mi)
            return mi

        def sep():
            menu.append(Gtk.SeparatorMenuItem())

        if item is not None and item.kind in ("app", "launcher"):
            for win in item.windows[:8]:
                title = (win.title or item.name)
                title = title if len(title) <= 48 else title[:47] + "…"
                add(title, lambda wid=win.id: self.app.focus_window(wid))
            if item.windows:
                sep()
            add("New Window" if item.windows else "Open", lambda: self.app.activate(item, True, self))
            if item.entry is not None:
                for act in item.entry.actions:
                    add(act.name, lambda a=act: self.app.launch_action(item, a))
            sep()
            if item.pinned:
                add("Remove from Dock", lambda: self.app.unpin(item))
                add("Rename / Change Icon…", lambda: self.app.edit_item(item))
            elif item.entry is not None:
                add("Keep in Dock", lambda: self.app.pin(item))
            if item.windows:
                add("Close All Windows", lambda: self.app.close_windows(item))
            sep()
        elif item is not None and item.kind == "special":
            add("Open", lambda: self.app.activate(item, False, self))
            add("Remove from Dock", lambda: self.app.unpin(item))
            sep()
        add("Dock Settings…", self.app.open_settings)
        add("Quit Dock", Gtk.main_quit)
        menu.show_all()
        self.menu_open = True
        menu.connect("deactivate", self._menu_closed)
        menu.attach_to_widget(self.area, None)
        anchors = {"bottom": (Gdk.Gravity.NORTH, Gdk.Gravity.SOUTH), "top": (Gdk.Gravity.SOUTH, Gdk.Gravity.NORTH),
                   "left": (Gdk.Gravity.EAST, Gdk.Gravity.WEST), "right": (Gdk.Gravity.WEST, Gdk.Gravity.EAST)}
        try:
            r = Gdk.Rectangle()
            r.x, r.y, r.width, r.height = int(ev.x) - 1, int(ev.y) - 1, 2, 2
            if item is not None:
                pos, sizes, length, m0 = self.layout()
                idx = self.items.index(item)
                m, c, s = self.item_rect(idx, pos, sizes, m0)
                W, H = self.area.get_allocated_width(), self.area.get_allocated_height()
                x, y, w, h = M.place(self.geo.edge, W, H, m, c, s, s)
                r.x, r.y, r.width, r.height = int(x), int(y), int(w), int(h)
            menu.popup_at_rect(self.area.get_window(), r, anchors[self.geo.edge][0],
                               anchors[self.geo.edge][1], ev)
        except Exception:  # fall back to plain pointer popup
            menu.popup_at_pointer(ev)

    def _menu_closed(self, menu):
        self.menu_open = False
        self.reevaluate()
        GLib.timeout_add(1500, lambda: (menu.destroy(), False)[1])


# ------------------------------------------------------------------- application

class DockApp:
    def __init__(self):
        self.cfg = None
        self.entries = {}
        self.ipc = None
        self.windows = []
        self.outputs = []
        self.workspaces = []
        self.fullscreen_outs = set()
        self.items = []
        self.docks = {}
        self.refresh_id = None
        self.reload_id = None
        self.blur_state = "off"
        self.blur_applied = None
        self.sway_ok = False
        self.icons = None
        self.control = None
        self.listener = None
        self.last_self_write = 0.0

    # ------------------------------------------------------------ lifecycle
    def run(self):
        display = Gdk.Display.get_default()
        if display is None:
            log("No display: run this inside your Sway session (WAYLAND_DISPLAY must be set).")
            return 1
        if GtkLayerShell is None:
            log("GtkLayerShell typelib not found. Install it with: sudo dnf install gtk-layer-shell")
            return 1
        if not GtkLayerShell.is_supported():
            log("This compositor does not support wlr-layer-shell (or GDK is not using Wayland). "
                "GlassDock needs Sway/SwayFX on Wayland. If GDK_BACKEND=x11 is set, unset it.")
            return 1

        self.control = control.ControlServer(self.handle_control)
        try:
            self.control.bind()
        except control.AlreadyRunning:
            log("GlassDock is already running.")
            return 1
        self.control.start()

        provider = Gtk.CssProvider()
        provider.load_from_data(b"window.glassdock, window.glassdock > * { background: transparent; }")
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider,
                                                 Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.icons = IconCache()
        self.entries = load_entries()
        self.cfg = C.load_config(entries=self.entries)
        if not os.path.exists(C.config_path()):
            C.save_config(self.cfg)

        try:
            self.ipc = sway.SwayIPC()
            self.ipc.connect()
            self.sway_ok = True
        except sway.SwayError as exc:
            log("Sway IPC unavailable (%s): running without window indicators." % exc)
            self.ipc = None
        if self.ipc is not None:
            self.listener = sway.EventListener(self.on_sway_event)
            self.listener.start()

        self.watch_config()
        self.refresh_state()
        for sig in (signal.SIGINT, signal.SIGTERM):
            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, sig, self.quit)
        log("running (v%s)" % __version__)
        Gtk.main()
        self.shutdown()
        return 0

    def quit(self, *_):
        Gtk.main_quit()
        return False

    def shutdown(self):
        if self.listener:
            self.listener.stop()
        if self.control:
            self.control.stop()

    # --------------------------------------------------------------- sway state
    def on_sway_event(self, name, payload):
        if name == "window" and isinstance(payload, dict) and payload.get("change") == "title":
            return
        if name in ("window", "workspace", "output", "connected"):
            GLib.idle_add(self.schedule_refresh)

    def schedule_refresh(self):
        if self.refresh_id is None:
            self.refresh_id = GLib.timeout_add(60, self._refresh_now)
        return False

    def _refresh_now(self):
        self.refresh_id = None
        self.refresh_state()
        return False

    def refresh_state(self):
        if self.ipc is not None:
            try:
                tree = self.ipc.get_tree()
                outs = self.ipc.get_outputs()
                self.workspaces = self.ipc.get_workspaces()
                self.windows = sway.parse_tree(tree)
                self.outputs = sway.parse_outputs(outs)
                self.fullscreen_outs = sway.fullscreen_outputs(self.windows, self.workspaces)
                self.sway_ok = True
            except (sway.SwayError, OSError) as exc:
                if self.sway_ok:
                    log("Sway IPC error: %s" % exc)
                self.sway_ok = False
                self.windows = []
                self.fullscreen_outs = set()
        self.rebuild()

    def fallback_outputs(self):
        display = Gdk.Display.get_default()
        outs = []
        for i in range(display.get_n_monitors()):
            geo = display.get_monitor(i).get_geometry()
            outs.append({"name": "monitor-%d" % i, "rect": (geo.x, geo.y, geo.width, geo.height),
                         "scale": 1.0, "focused": i == 0})
        return outs

    def find_gdk_monitor(self, rect):
        display = Gdk.Display.get_default()
        for i in range(display.get_n_monitors()):
            mon = display.get_monitor(i)
            geo = mon.get_geometry()
            if (geo.x, geo.y, geo.width, geo.height) == tuple(int(v) for v in rect):
                return mon
        return None

    # ------------------------------------------------------------------ build
    def rebuild(self):
        g = getter(self.cfg)
        self.items = M.build_items(self.cfg["items"], self.entries, self.windows,
                                   g("behavior.show_running_unpinned"))
        outs = self.outputs or self.fallback_outputs()
        wanted = {o["name"]: o for o in outs if C.monitor_enabled(self.cfg, o["name"])}
        for name in list(self.docks):
            dock = self.docks[name]
            if name not in wanted or tuple(dock.output["rect"]) != tuple(wanted[name]["rect"]):
                dock.destroy()
                del self.docks[name]
        for name, out in wanted.items():
            dock = self.docks.get(name)
            if dock is None:
                dock = DockWindow(self, out)
                self.docks[name] = dock
            dock.apply(C.effective(self.cfg, name), self.items, self.windows, name in self.fullscreen_outs)
        self.apply_blur()

    def apply_blur(self):
        want = bool(getter(self.cfg)("appearance.blur"))
        if want == self.blur_applied:
            return
        if self.ipc is None:
            self.blur_state = "unavailable (no Sway IPC)" if want else "off"
            self.blur_applied = want
            return
        effects = "blur enable; blur_ignore_transparent enable" if want else \
                  "blur disable; blur_ignore_transparent disable"
        ok, err = self.ipc.command_ok('layer_effects %s "%s"' % (NAMESPACE, effects))
        if want:
            self.blur_state = "applied via SwayFX layer_effects" if ok else \
                "not supported by this compositor (%s); plain transparency in use" % err
        else:
            self.blur_state = "off"
        self.blur_applied = want

    def reload_config(self):
        self.entries = load_entries()
        self.cfg = C.load_config(entries=self.entries)
        self.blur_applied = None
        self.rebuild()
        return False

    def watch_config(self):
        d = C.config_dir()
        os.makedirs(d, exist_ok=True)
        self.monitor = Gio.File.new_for_path(d).monitor_directory(Gio.FileMonitorFlags.NONE, None)
        self.monitor.connect("changed", self.on_config_file_changed)

    def on_config_file_changed(self, mon, f, other, event):
        if not f.get_basename() == "config.json":
            return
        if time.monotonic() - self.last_self_write < 0.5:
            return
        if self.reload_id is None:
            self.reload_id = GLib.timeout_add(200, self._reload_debounced)

    def _reload_debounced(self):
        self.reload_id = None
        return self.reload_config()

    # ----------------------------------------------------------------- control
    def handle_control(self, msg):
        cmd = msg.get("cmd")
        if cmd == "ping":
            return {"ok": True, "version": __version__}
        if cmd == "reload":
            GLib.idle_add(self.reload_config)
            return {"ok": True}
        if cmd in ("toggle", "show", "hide", "auto"):
            GLib.idle_add(self.set_manual, cmd)
            return {"ok": True}
        if cmd == "launch":
            try:
                n = int(msg.get("index"))
            except (TypeError, ValueError):
                return {"ok": False, "error": "launch needs a numeric index (1-based)"}
            GLib.idle_add(self.launch_index, n)
            return {"ok": True}
        if cmd == "status":
            return {"ok": True, "version": __version__, "sway_ipc": self.sway_ok,
                    "outputs": sorted(list(self.docks)), "blur": self.blur_state,
                    "items": len(self.items), "windows": len(self.windows),
                    "theme": (self.cfg or {}).get("theme"),
                    "autostart": getter(self.cfg)("behavior.autostart") if self.cfg else None,
                    "autostart_wms": getter(self.cfg)("behavior.autostart_wms") if self.cfg else None}
        if cmd == "quit":
            GLib.idle_add(self.quit)
            return {"ok": True}
        return {"ok": False, "error": "unknown command %r" % cmd}

    def set_manual(self, cmd):
        for dock in self.docks.values():
            if cmd == "auto":
                dock.manual = None
            elif cmd == "toggle":
                dock.manual = not dock.vis_target
            else:
                dock.manual = cmd == "show"
            dock.reevaluate()
            dock.update_region(force=True)
        return False

    def launch_index(self, n):
        usable = [i for i in self.items if i.kind != "separator"]
        if 1 <= n <= len(usable):
            self.activate(usable[n - 1], False, None)
        return False

    # ----------------------------------------------------------------- actions
    def terminal_prefix(self):
        try:
            return shlex.split(getter(self.cfg)("behavior.terminal_command")) + ["-e"]
        except ValueError:
            return ["foot", "-e"]

    def activate(self, item, new_instance=False, dock=None):
        if item.kind == "separator":
            return
        if item.kind == "special":
            if item.special == "apps":
                try:
                    argv = shlex.split(getter(self.cfg)("behavior.launcher_command"))
                except ValueError:
                    argv = []
                if argv:
                    spawn(argv)
            elif item.special == "trash":
                spawn(["gio", "open", "trash:///"])
            return
        if item.windows and not new_instance:
            self.focus_item(item)
            return
        self.launch(item, dock)

    def focus_window(self, wid):
        if self.ipc is not None:
            ok, err = self.ipc.command_ok("[con_id=%d] focus" % wid)
            if not ok:
                log("focus failed: %s" % err)

    def focus_item(self, item):
        wins = item.windows
        idx = 0
        for i, w in enumerate(wins):
            if w.focused:
                idx = (i + 1) % len(wins)
                break
        self.focus_window(wins[idx].id)

    def close_windows(self, item):
        if self.ipc is not None:
            for w in item.windows:
                self.ipc.command_ok("[con_id=%d] kill" % w.id)

    def launch(self, item, dock=None):
        argv = None
        if item.kind == "launcher":
            argv = list(item.argv or [])
        elif item.entry is not None:
            argv = expand_exec(item.entry.exec, item.entry)
            if item.entry.terminal:
                argv = self.terminal_prefix() + argv
        if not argv:
            toast("%s cannot be launched from here" % (item.name or "This item"))
            return
        if spawn(argv) and not item.windows and dock is not None and \
                getter(dock.cfg)("animation.launch_bounce"):
            for d in self.docks.values():
                d.start_bounce(item.key)

    def launch_action(self, item, action):
        argv = expand_exec(action.exec, item.entry)
        if item.entry.terminal:
            argv = self.terminal_prefix() + argv
        spawn(argv)

    def save_cfg(self):
        self.last_self_write = time.monotonic()
        C.save_config(self.cfg)
        self.rebuild()

    def pin(self, item):
        if item.entry is not None:
            self.cfg["items"].append({"type": "app", "id": item.entry.id})
            self.save_cfg()

    def unpin(self, item):
        idx = item.cfg_index
        if 0 <= idx < len(self.cfg["items"]):
            del self.cfg["items"][idx]
            self.save_cfg()

    def move_item(self, src, before):
        new = M.reorder_items(self.cfg["items"], src, before)
        if new is not None:
            self.cfg["items"] = new
            self.save_cfg()

    def edit_item(self, item):
        """Open Settings > Launchers with this pinned item's editor showing."""
        try:
            pkg = (__package__ or "glassdock").split(".")[0]
            subprocess.Popen([sys.executable, "-m", pkg + ".settings", "--edit", str(item.cfg_index)],
                             cwd=ROOT, env=child_env(), start_new_session=True)
        except OSError as exc:
            toast("Could not open settings: %s" % exc)

    def open_settings(self):
        try:
            subprocess.Popen([os.path.join(ROOT, "bin", "glassdock-settings")], cwd=ROOT, env=child_env(),
                             start_new_session=True)
        except OSError as exc:
            toast("Could not open settings: %s" % exc)


def main():
    sys.exit(DockApp().run())


if __name__ == "__main__":
    main()
