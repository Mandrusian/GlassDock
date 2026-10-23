# Integrated GlassDock extension module.
"""Native dock widgets: analog clock, digital clock, calendar, music (MPRIS), plugin wrapper.

Each widget renders itself to a cairo surface (render_surface) so the original dock paints it like any icon.
Contract:  draw(cr, s, pct)  |  tick()  |  tooltip()  |  on_click(host, dock, item, button) -> Gtk widget | list[str] | None
"""
import math
import time

import cairo

try:
    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    gi.require_version("Pango", "1.0")
    gi.require_version("PangoCairo", "1.0")
    from gi.repository import Gio, GLib, GdkPixbuf, Gdk, Gtk, Pango, PangoCairo
    HAVE_GI = True
except (ImportError, ValueError):
    HAVE_GI = False



# ------------------------------------------------------------------ drawing helpers
def hexrgba(s, alpha=None):
    s = (s or "#000000").lstrip("#")
    if len(s) in (3, 4):
        s = "".join(ch * 2 for ch in s)
    try:
        r, g, b = (int(s[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
        a = int(s[6:8], 16) / 255.0 if len(s) >= 8 else 1.0
    except ValueError:
        r, g, b, a = 0, 0, 0, 1
    return (r, g, b, a if alpha is None else alpha)


def rrect(cr, x, y, w, h, r):
    r = max(0.0, min(r, w / 2.0, h / 2.0))
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


def tile(cr, s, top, bottom, pct=None):
    rrect(cr, 0, 0, s, s, s * (pct / 100.0 if pct else 0.23))
    pat = cairo.LinearGradient(0, 0, 0, s)
    pat.add_color_stop_rgba(0, *top)
    pat.add_color_stop_rgba(1, *bottom)
    cr.set_source(pat)
    cr.fill()


def text(cr, s, x, y, px, color, bold=False, font="Sans"):
    """Centered text at (x, y). No-op without PangoCairo (headless tests)."""
    if not HAVE_GI:
        return
    layout = PangoCairo.create_layout(cr)
    fd = Pango.FontDescription("%s%s" % (font, " Bold" if bold else ""))
    fd.set_absolute_size(max(1.0, px) * Pango.SCALE)
    layout.set_font_description(fd)
    layout.set_text(s, -1)
    tw, th = layout.get_pixel_size()
    cr.set_source_rgba(*color)
    cr.move_to(x - tw / 2.0, y - th / 2.0)
    PangoCairo.show_layout(cr, layout)


def surface_from_path(path, px, scale=1):
    """Image file -> (surface, w, h) or None."""
    if not HAVE_GI or not path:
        return None
    try:
        pb = GdkPixbuf.Pixbuf.new_from_file_at_size(path, int(px * scale), int(px * scale))
        return (Gdk.cairo_surface_create_from_pixbuf(pb, scale, None), pb.get_width() / float(scale),
                pb.get_height() / float(scale))
    except (GLib.Error, OSError, TypeError, ValueError):
        return None


# ------------------------------------------------------------------ base
class Widget:
    TYPE = ""
    TICK = 0.0                 # seconds between tick() calls (0 = never)

    def __init__(self, wid, cfg, host):
        self.id, self.cfg, self.host = wid, cfg, host
        self.hover, self.fx, self.fy = False, 0.5, 0.5     # pointer state, set by the dock subclass
        self.failed = False

    def wants_fast_redraw(self):
        return False

    def tick(self):
        pass

    def tooltip(self):
        return self.TYPE

    def draw(self, cr, s, pct):
        raise NotImplementedError

    def on_click(self, host, dock, item, button):
        return None

    def render_surface(self, px, scale=1, pct=None):
        n = int(math.ceil(px * scale))
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, n, n)
        surf.set_device_scale(scale, scale)
        cr = cairo.Context(surf)
        try:
            self.draw(cr, float(px), pct if pct is not None else getattr(self.host, "icon_pct", 23))
        except Exception as exc:  # noqa: BLE001
            if not self.failed:
                print("[glassdock] widget %s draw failed: %s" % (self.id, exc))
            self.failed = True
            cr.save(); cr.identity_matrix(); cr.set_operator(cairo.OPERATOR_SOURCE); cr.paint(); cr.restore()
            tile(cr, px, (0.5, 0.1, 0.1, 1), (0.3, 0.05, 0.05, 1))
            text(cr, "!", px / 2, px / 2, px * 0.5, (1, 1, 1, 1), True)
        return (surf, float(px), float(px))


# ------------------------------------------------------------------ clocks
class AnalogClock(Widget):
    TYPE = "analog_clock"

    def wants_fast_redraw(self):
        return bool(self.cfg["seconds"] and self.cfg["smooth"])

    def tooltip(self):
        return time.strftime("%A %H:%M")

    def draw(self, cr, s, pct):
        c = self.cfg
        face = hexrgba(c["face_color"])
        tile(cr, s, face, tuple(max(0, v - 0.12) for v in face[:3]) + (face[3],), pct)
        cx = cy = s / 2.0
        r = s * 0.42
        ink = hexrgba(c["hand_color"])
        cr.set_source_rgba(*ink)
        dial = c["dial"]
        for i in range(12):
            a = i * math.pi / 6 - math.pi / 2
            if dial == "roman":
                text(cr, ("XII", "I", "II", "III", "IIII", "V", "VI", "VII", "VIII", "IX", "X", "XI")[i],
                     cx + math.cos(a) * r * 0.82, cy + math.sin(a) * r * 0.82, s * 0.095, ink, True, "Serif")
            elif dial == "ticks" or i % 3 == 0:
                big = i % 3 == 0
                cr.set_line_width(s * (0.028 if big else 0.016))
                cr.set_line_cap(cairo.LINE_CAP_ROUND)
                r0 = r * (0.80 if big else 0.88)
                cr.move_to(cx + math.cos(a) * r0, cy + math.sin(a) * r0)
                cr.line_to(cx + math.cos(a) * r * 0.97, cy + math.sin(a) * r * 0.97)
                cr.stroke()
        t = time.time()
        lt = time.localtime(t)
        sec = lt.tm_sec + ((t % 1.0) if c["smooth"] else 0.0)
        mn = lt.tm_min + sec / 60.0
        hr = (lt.tm_hour % 12) + mn / 60.0
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        for frac, length, width in ((hr / 12.0, 0.52, 0.060), (mn / 60.0, 0.78, 0.040)):
            a = frac * 2 * math.pi - math.pi / 2
            cr.set_source_rgba(*ink)
            cr.set_line_width(s * width)
            cr.move_to(cx, cy)
            cr.line_to(cx + math.cos(a) * r * length, cy + math.sin(a) * r * length)
            cr.stroke()
        if c["seconds"]:
            a = sec / 60.0 * 2 * math.pi - math.pi / 2
            cr.set_source_rgba(*hexrgba(c["second_color"]))
            cr.set_line_width(s * 0.016)
            cr.move_to(cx - math.cos(a) * r * 0.18, cy - math.sin(a) * r * 0.18)
            cr.line_to(cx + math.cos(a) * r * 0.86, cy + math.sin(a) * r * 0.86)
            cr.stroke()
            cr.arc(cx, cy, s * 0.032, 0, 2 * math.pi)
            cr.fill()
        else:
            cr.set_source_rgba(*ink)
            cr.arc(cx, cy, s * 0.03, 0, 2 * math.pi)
            cr.fill()


class DigitalClock(Widget):
    TYPE = "digital_clock"
    TICK = 1.0

    def tooltip(self):
        return time.strftime("%A, %d %B %Y")

    def draw(self, cr, s, pct):
        c = self.cfg
        bg = hexrgba(c["bg_color"])
        tile(cr, s, tuple(min(1, v + 0.08) for v in bg[:3]) + (bg[3],), bg, pct)
        fg = hexrgba(c["text_color"])
        try:
            now = time.strftime(c["format"])
        except ValueError:
            now = "??:??"
        n = max(len(now), 3)
        size = min(s * 0.34, s * 0.86 / (n * 0.56))
        text(cr, now, s / 2, s * (0.40 if c["show_date"] else 0.5), size, fg, True, c["font"])
        if c["show_date"]:
            text(cr, time.strftime(c["date_format"]), s / 2, s * 0.72, s * 0.13, fg[:3] + (0.7,), False, c["font"])


class CalendarWidget(Widget):
    TYPE = "calendar"
    TICK = 30.0

    def tooltip(self):
        return time.strftime("%A, %d %B %Y")

    def draw(self, cr, s, pct):
        tile(cr, s, (1, 1, 1, 1), (0.93, 0.93, 0.95, 1), pct)
        acc = hexrgba(self.cfg["accent"])
        cr.save()
        rrect(cr, 0, 0, s, s, s * (pct / 100.0 if pct else 0.23))
        cr.clip()
        cr.set_source_rgba(*acc)
        cr.rectangle(0, 0, s, s * 0.30)
        cr.fill()
        cr.restore()
        text(cr, time.strftime("%a").upper(), s / 2, s * 0.15, s * 0.15, (1, 1, 1, 0.95), True)
        text(cr, str(int(time.strftime("%d"))), s / 2, s * 0.63, s * 0.46, (0.1, 0.1, 0.12, 1), True)

    def on_click(self, host, dock, item, button):
        if not HAVE_GI:
            return None
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for side in ("start", "end", "top", "bottom"):
            getattr(box, "set_margin_" + side)(10)
        title = Gtk.Label(label=time.strftime("%A, %d %B %Y"))
        title.get_style_context().add_class("title-3")
        cal = Gtk.Calendar()
        cal.set_property("show-week-numbers", bool(self.cfg["show_week_numbers"]))
        today = Gtk.Button(label="Today")
        t = time.localtime()
        today.connect("clicked", lambda *_: (cal.select_month(t.tm_mon - 1, t.tm_year), cal.select_day(t.tm_mday)))
        for w in (title, cal, today):
            box.pack_start(w, False, False, 0)
        return box


# ------------------------------------------------------------------ music (MPRIS)
MPRIS = "org.mpris.MediaPlayer2."
PLAYER_IFACE = "org.mpris.MediaPlayer2.Player"


class MusicWidget(Widget):
    TYPE = "music"
    TICK = 2.0

    def __init__(self, *args):
        super().__init__(*args)
        self.bus, self.player, self.st = None, None, {}
        self.art, self.art_url = None, None
        self._refresh_busy = False
        self._refresh_lock = __import__("threading").Lock()
        self.last_error = ""

    @staticmethod
    def _call(bus, dest, path, iface, method, params=None, rtype=None):
        return bus.call_sync(dest, path, iface, method, params, rtype,
                             Gio.DBusCallFlags.NONE, 250, None)

    def tick(self):
        """Refresh MPRIS metadata off the GTK loop so a stuck player cannot freeze the dock."""
        if not HAVE_GI:
            return
        with self._refresh_lock:
            if self._refresh_busy:
                return
            self._refresh_busy = True
        import threading
        threading.Thread(target=self._refresh_worker, daemon=True,
                         name="glassdock-mpris-refresh").start()

    def _refresh_worker(self):
        result = (None, None, {}, None, "")
        bus = None
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            names = self._call(bus, "org.freedesktop.DBus", "/org/freedesktop/DBus",
                               "org.freedesktop.DBus", "ListNames", None,
                               GLib.VariantType("(as)")).unpack()[0]
            preferred = (self.cfg.get("player") or "").lower()
            candidates = [name for name in sorted(names)
                          if name.startswith(MPRIS) and (not preferred or preferred in name.lower())][:8]
            best = None
            for name in candidates:
                props = self._call(bus, name, "/org/mpris/MediaPlayer2",
                                   "org.freedesktop.DBus.Properties", "GetAll",
                                   GLib.Variant("(s)", (PLAYER_IFACE,)),
                                   GLib.VariantType("(a{sv})")).unpack()[0]
                if best is None or props.get("PlaybackStatus") == "Playing":
                    best = (name, props)
                if props.get("PlaybackStatus") == "Playing":
                    break
            player, state = best if best else (None, {})
            metadata = state.get("Metadata", {}) if state else {}
            art_url = metadata.get("mpris:artUrl") if isinstance(metadata, dict) else None
            result = (bus, player, state, art_url, "")
        except Exception as exc:  # a missing or misbehaving player is a normal state
            result = (bus, None, {}, None, str(exc))
        GLib.idle_add(self._apply_refresh, result)

    def _apply_refresh(self, result):
        self.bus, self.player, self.st, art_url, self.last_error = result
        if art_url != self.art_url:
            self.art_url, self.art = art_url, None
            if art_url and self.cfg.get("show_art", True) and art_url.startswith("file://"):
                try:
                    path = Gio.File.new_for_uri(art_url).get_path()
                    self.art = surface_from_path(path, 160) if path else None
                except (GLib.Error, TypeError, ValueError):
                    self.art = None
        with self._refresh_lock:
            self._refresh_busy = False
        self.host.redraw()
        return False

    def meta(self):
        metadata = (self.st or {}).get("Metadata", {})
        artist = metadata.get("xesam:artist") if isinstance(metadata, dict) else ""
        artist = ", ".join(artist) if isinstance(artist, list) else (artist or "")
        title = metadata.get("xesam:title", "") if isinstance(metadata, dict) else ""
        return title, artist

    def progress(self):
        try:
            position = float((self.st or {})["Position"])
            length = float(self.st["Metadata"]["mpris:length"])
            if not math.isfinite(position) or not math.isfinite(length) or length <= 0:
                return 0.0
            return max(0.0, min(1.0, position / length))
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            return 0.0

    def playing(self):
        return (self.st or {}).get("PlaybackStatus") == "Playing"

    def tooltip(self):
        title, artist = self.meta()
        return "%s — %s" % (title, artist) if title and artist else (title or "No music playing")

    def control(self, method):
        if not self.bus or not self.player:
            self.tick()
            return
        methods = {"Previous", "PlayPause", "Next", "Stop", "Play", "Pause"}
        if method not in methods:
            return
        try:
            self.bus.call(self.player, "/org/mpris/MediaPlayer2", PLAYER_IFACE, method,
                          None, None, Gio.DBusCallFlags.NONE, 300, None,
                          self._control_finished, method)
        except (GLib.Error, TypeError) as exc:
            self.last_error = str(exc)
            self.host.redraw()

    def _control_finished(self, connection, result, method):
        try:
            connection.call_finish(result)
            self.last_error = ""
        except GLib.Error as exc:
            self.last_error = str(exc)
        GLib.timeout_add(250, self._refresh_after_control)

    def _refresh_after_control(self):
        self.tick()
        return False

    def draw(self, cr, s, pct):
        rad = s * (pct / 100.0 if pct else 0.23)
        if self.art:
            surf, lw, lh = self.art
            cr.save()
            rrect(cr, 0, 0, s, s, rad); cr.clip()
            cr.scale(s / lw, s / lh); cr.set_source_surface(surf, 0, 0); cr.paint()
            cr.restore()
        else:
            tile(cr, s, (0.95, 0.30, 0.45, 1), (0.55, 0.15, 0.35, 1), pct)
            text(cr, "♪", s / 2, s / 2, s * 0.55, (1, 1, 1, 0.95), True)
        prog = self.progress()
        if prog > 0:
            cr.set_source_rgba(0, 0, 0, 0.35); rrect(cr, s * 0.1, s * 0.88, s * 0.8, s * 0.05, s * 0.025); cr.fill()
            cr.set_source_rgba(1, 1, 1, 0.95); rrect(cr, s * 0.1, s * 0.88, s * 0.8 * prog, s * 0.05, s * 0.025); cr.fill()
        if self.hover and self.cfg.get("hover_controls", True):
            cr.save(); rrect(cr, 0, 0, s, s, rad); cr.clip()
            cr.set_source_rgba(0, 0, 0, 0.5); cr.paint(); cr.restore()
            cy, u = s / 2, s * 0.12
            zone = 0 if self.fx < 0.33 else (2 if self.fx > 0.66 else 1)
            for k, cx in enumerate((s * 0.18, s * 0.5, s * 0.82)):
                cr.set_source_rgba(1, 1, 1, 1.0 if k == zone else 0.7)
                if k == 1:
                    if self.playing():
                        rrect(cr, cx - u * 0.8, cy - u, u * 0.6, u * 2, 2)
                        rrect(cr, cx + u * 0.2, cy - u, u * 0.6, u * 2, 2)
                    else:
                        cr.move_to(cx - u * 0.7, cy - u); cr.line_to(cx + u * 0.9, cy); cr.line_to(cx - u * 0.7, cy + u); cr.close_path()
                else:
                    direction = -1 if k == 0 else 1
                    tip, base, bx = cx + direction * u * 0.8, cx - direction * u * 0.1, cx + direction * u * 0.85
                    cr.move_to(base, cy - u * 0.9); cr.line_to(tip, cy); cr.line_to(base, cy + u * 0.9); cr.close_path()
                    cr.rectangle(bx if direction == 1 else bx - u * 0.25, cy - u * 0.9, u * 0.25, u * 1.8)
                cr.fill()

    def on_click(self, host, dock, item, button):
        if self.player is None:
            self.tick()
        if button == 2:
            self.control("Next")
            return None
        if self.cfg.get("hover_controls", True):
            self.control("Previous" if self.fx < 0.33 else ("Next" if self.fx > 0.66 else "PlayPause"))
            return None
        return self.popup()

    def popup(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for side in ("start", "end", "top", "bottom"):
            getattr(box, "set_margin_" + side)(12)
        title, artist = self.meta()
        heading = Gtk.Label(label=title or "Nothing playing")
        heading.get_style_context().add_class("title-4")
        box.pack_start(heading, False, False, 0)
        box.pack_start(Gtk.Label(label=artist), False, False, 0)
        bar = Gtk.ProgressBar(); bar.set_fraction(self.progress()); box.pack_start(bar, False, False, 0)
        row = Gtk.Box(spacing=6, halign=Gtk.Align.CENTER)
        for icon, method in (("media-skip-backward-symbolic", "Previous"),
                             ("media-playback-start-symbolic", "PlayPause"),
                             ("media-skip-forward-symbolic", "Next")):
            button = Gtk.Button.new_from_icon_name(icon, Gtk.IconSize.BUTTON)
            button.connect("clicked", lambda _button, m=method: self.control(m))
            row.pack_start(button, False, False, 0)
        box.pack_start(row, False, False, 0)
        return box


# ------------------------------------------------------------------ plugin wrapper
class PluginWidget(Widget):
    TYPE = "plugin"

    def __init__(self, wid, inst, host):
        super().__init__(wid, {}, host)
        self.inst = inst
        tick = float(inst.cls.TICK)
        self.TICK = 0.0 if tick == 0 else max(0.2, tick)

    def tick(self):
        self.inst.call("on_tick")

    def tooltip(self):
        return str(self.inst.call("tooltip", default=self.inst.cls.NAME))

    def draw(self, cr, s, pct):
        if not self.inst.cls.TRANSPARENT:
            tile(cr, s, (0.20, 0.21, 0.25, 1), (0.10, 0.10, 0.13, 1), pct)
        if self.inst.disabled:
            text(cr, "!", s / 2, s / 2, s * 0.5, (1, 0.4, 0.4, 1), True)
            return
        self.inst.call("render", cr, s, s)

    def on_click(self, host, dock, item, button):
        res = self.inst.call("on_click", button)
        self.host.redraw()
        if isinstance(res, (list, tuple)) and HAVE_GI:
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            for side in ("start", "end", "top", "bottom"):
                getattr(box, "set_margin_" + side)(10)
            for line in res:
                box.pack_start(Gtk.Label(label=str(line), xalign=0), False, False, 0)
            return box
        return None


WIDGET_TYPES = {"analog_clock": AnalogClock, "digital_clock": DigitalClock, "calendar": CalendarWidget, "music": MusicWidget}
LABELS = {"analog_clock": "Analog clock", "digital_clock": "Digital clock", "calendar": "Calendar", "music": "Music",
          "folder": "Folder (fan)"}
