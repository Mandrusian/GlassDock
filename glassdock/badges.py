# Integrated GlassDock extension module.
"""Notification and progress badges via the Unity LauncherEntry D-Bus API.

Apps such as Telegram, Discord, Thunderbird, Nautilus (copy progress) and Steam already emit
com.canonical.Unity.LauncherEntry.Update. We subscribe and overlay a red count bubble and/or a progress bar
on the matching dock icon. Nothing to configure; apps without the API simply show nothing.
"""
import math

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gio  # noqa: E402

from .core import model as M  # noqa: E402
from .widgets import rrect, text  # noqa: E402


class Badges:
    def __init__(self, on_change):
        self.data, self.on_change = {}, on_change
        self.bus = None
        self.subscription_id = 0
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            subscription = bus.signal_subscribe(
                None, "com.canonical.Unity.LauncherEntry", "Update", None, None,
                Gio.DBusSignalFlags.NONE, self._update,
            )
            self.bus = bus
            self.subscription_id = subscription
        except Exception:  # noqa: BLE001
            self.bus = None
            self.subscription_id = 0

    def close(self):
        """Release the D-Bus signal subscription during dock shutdown."""
        if self.bus is not None and self.subscription_id:
            try:
                self.bus.signal_unsubscribe(self.subscription_id)
            except Exception:  # noqa: BLE001
                pass
            finally:
                self.subscription_id = 0
        self.bus = None

    def _update(self, _c, _sender, _path, _iface, _sig, params):
        try:
            uri, props = params.unpack()
            if not isinstance(uri, str) or not isinstance(props, dict):
                return
            app = uri.removeprefix("application://")
            if app.endswith(".desktop"):
                app = app[:-8]
            if not app or len(app) > 255:
                return
            cur = self.data.setdefault(app, {})
            for key in ("count", "count-visible", "progress", "progress-visible", "urgent"):
                if key in props:
                    cur[key] = props[key]
            self.on_change()
        except (TypeError, ValueError, OverflowError):
            return

    def lookup(self, item):
        ent = getattr(item, "entry", None)
        key = getattr(ent, "id", None)
        if not key:
            return None
        d = self.data.get(str(key).replace(".desktop", ""))
        if not d:
            return None
        try:
            raw_count = d.get("count", 0)
            count = int(raw_count) if d.get("count-visible") and not isinstance(raw_count, bool) else 0
        except (TypeError, ValueError, OverflowError):
            count = 0
        try:
            raw_progress = d.get("progress", 0.0)
            prog = float(raw_progress) if d.get("progress-visible") else None
            if prog is not None and not math.isfinite(prog):
                prog = None
        except (TypeError, ValueError, OverflowError):
            prog = None
        if count <= 0 and prog is None:
            return None
        return (max(0, count), max(0.0, min(1.0, prog)) if prog is not None else None)


def draw_badges(dock, cr, badges):
    """Overlay on a DockWindow (uses its own layout helpers, so it follows magnification and edge)."""
    if dock.geo is None or dock.progress < 0.02:
        return
    geo = dock.geo
    W, H = dock.area.get_allocated_width(), dock.area.get_allocated_height()
    pos, sizes, _length, m0 = dock.layout()
    off = (1.0 - dock.progress) * (geo.c0 + geo.thick + geo.shadow + 4)
    for i, it in enumerate(dock.items):
        b = badges.lookup(it) if it.kind != "separator" else None
        if not b:
            continue
        m, c, s = dock.item_rect(i, pos, sizes, m0)
        x, y, w, h = M.place(geo.edge, W, H, m, c - off, s, s)
        count, prog = b
        if prog is not None:
            cr.set_source_rgba(0, 0, 0, 0.45); rrect(cr, x + w * 0.12, y + h - 7, w * 0.76, 5, 2.5); cr.fill()
            cr.set_source_rgba(0.35, 0.8, 1, 1); rrect(cr, x + w * 0.12, y + h - 7, w * 0.76 * max(0.0, min(1.0, prog)), 5, 2.5); cr.fill()
        if count > 0:
            label = str(count) if count < 100 else "99+"
            r = max(8.0, w * 0.17)
            bw = max(2 * r, r * 0.9 + 7 * len(label))
            cx, cy = x + w - bw / 2 + r * 0.35, y + r * 0.45
            rrect(cr, cx - bw / 2, cy - r, bw, 2 * r, r); cr.set_source_rgba(1, 0.23, 0.19, 1); cr.fill_preserve()
            cr.set_source_rgba(1, 1, 1, 0.9); cr.set_line_width(1.2); cr.stroke()
            text(cr, label, cx, cy, r * 1.15, (1, 1, 1, 1), True)
