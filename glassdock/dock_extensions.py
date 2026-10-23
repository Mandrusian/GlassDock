# Integrated GlassDock extension module.
"""Normal GlassDock dock runtime with integrated extension widgets and plugins.

    python3 -m glassdock.dock_extensions

Adds: native widgets, fan folders, icon overrides, live trash, plugins, badges, drop-onto-app-to-open,
drop-folder-to-pin, drop-onto-trash. Extras live in ~/.config/glassdock/extensions.json.
"""
import os
import sys
import time
from types import SimpleNamespace

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

from . import dock as D  # noqa: E402
from . import extras_store as X  # noqa: E402
from . import plugin_api as P  # noqa: E402
from .badges import Badges, draw_badges  # noqa: E402
from .core import config as C  # noqa: E402
from .core import model as M  # noqa: E402
from .core.colors import parse_color  # noqa: E402
from .folders import FolderWidget  # noqa: E402
from .stats import Stats  # noqa: E402
from .widgets import WIDGET_TYPES, PluginWidget, rrect, surface_from_path  # noqa: E402

PLUGIN_DIRS = [os.path.join(D.ROOT, "plugins"), X.USER_PLUGIN_DIR]
HOST = [None]


def plugin_search_dirs(cfg=None):
    """Resolve project, standard user, and optional user-selected plugin directories."""
    dirs = list(PLUGIN_DIRS)
    if isinstance(cfg, dict):
        try:
            custom = C.get_path(cfg, "extensions.plugin_directory").strip()
        except (KeyError, AttributeError, TypeError):
            custom = ""
        if custom:
            dirs.append(os.path.expanduser(custom))
    clean, seen = [], set()
    for directory in dirs:
        full = os.path.abspath(os.path.expanduser(directory))
        if full not in seen:
            seen.add(full)
            clean.append(full)
    return clean


class WItem(SimpleNamespace):
    """Dock item for an extra. Looks like a 'special' item to the original code (never draggable: cfg_index -1)."""

    @property
    def name(self):
        return self.widget.tooltip()


def make_item(wid, widget):
    return WItem(key="x:" + wid, kind="special", special="x:" + wid, icon=None, entry=None, windows=[], running=False,
                 active=False, urgent=False, pinned=False, cfg_index=-1, argv=None, widget=widget, gd_widget=True)


# ------------------------------------------------------------------ host
class ExtrasHost:
    def __init__(self, app):
        self.app, self.stats = app, Stats()
        self.data, self.widgets, self.plugin_insts = X.load(), {}, {}
        self.plugin_classes, self.plugin_errors = {}, {}
        self.icon_pct, self.overrides_cache = 23, {}
        self.badges = Badges(self.redraw)
        self.trash = TrashState(self.redraw)
        self.timer, self.timer_ms, self.last_tick = None, 0, {}
        self.popover = None
        self.reload(rebuild=False)

    def shutdown(self):
        if self.timer is not None:
            try:
                GLib.source_remove(self.timer)
            except GLib.Error:
                pass
            self.timer = None
        self.badges.close()
        self.trash.close()
        if self.popover is not None:
            self.popover.popdown()
            self.popover = None

    # ---- state
    def reload(self, rebuild=True):
        self.data = X.load()
        self.overrides_cache.clear()
        enabled = [name for name, conf in self.data["plugins"].items()
                   if isinstance(conf, dict) and conf.get("enabled") is True]
        self.plugin_classes, self.plugin_errors = P.discover(plugin_search_dirs(self.app.cfg), allowlist=enabled)
        old, self.widgets = self.widgets, {}
        for e in self.data["extras"]:
            wid, t = e.get("id"), e.get("type")
            if t in WIDGET_TYPES:
                prev = old.get(wid)
                w = prev if prev is not None and prev.TYPE == t else WIDGET_TYPES[t](wid, X.widget_cfg(self.data, wid, t), self)
                w.cfg = X.widget_cfg(self.data, wid, t)
                self.widgets[wid] = w
            elif t == "folder":
                self.widgets[wid] = FolderWidget(wid, X.folder_cfg(self.data, wid), self)
        active_plugins = set()
        for name, conf in self.data["plugins"].items():
            cls = self.plugin_classes.get(name)
            if cls is None or not conf.get("enabled"):
                self.plugin_insts.pop(name, None)
                continue
            active_plugins.add(name)
            inst = self.plugin_insts.get(name)
            if inst is None or inst.cls is not cls:
                inst = P.PluginInstance(name, cls, self.stats, conf.get("config", {}), self)
                self.plugin_insts[name] = inst
            else:
                inst.plugin.ctx._config.update(conf.get("config", {}))
            self.widgets["plugin:" + name] = PluginWidget("plugin:" + name, inst, self)
        for stale in set(self.plugin_insts) - active_plugins:
            self.plugin_insts.pop(stale, None)
        self.restart_timer()
        if rebuild:
            self.app.rebuild()

    def inject(self, items):
        """Attach advanced plugin views to normal launcher items and insert configured extras."""
        out = list(items)
        for item in out:
            if getattr(item, "kind", None) == "plugin":
                plugin_name = getattr(item, "extension", "") or getattr(item, "name", "")
                widget = self.widgets.get("plugin:" + plugin_name)
                if widget is not None:
                    item.widget = widget
                    item.gd_widget = True

        entries = [(entry.get("at"), entry["id"]) for entry in self.data["extras"]
                   if entry.get("id") in self.widgets and entry.get("type") != "plugin"]
        for at, wid in entries:
            item = make_item(wid, self.widgets[wid])
            if isinstance(at, int) and not isinstance(at, bool) and 0 <= at <= len(out):
                out.insert(at, item)
            else:
                # Re-evaluate the trash index after every insertion to keep order stable.
                trash_i = next((i for i, existing in enumerate(out)
                                if getattr(existing, "special", None) == "trash"), len(out))
                out.insert(trash_i, item)
        return out

    # ---- timers / redraw
    def restart_timer(self):
        fast = any(w.wants_fast_redraw() for w in self.widgets.values())
        want = 66 if fast else 500
        if self.timer is not None and want == self.timer_ms:
            return
        if self.timer is not None:
            GLib.source_remove(self.timer)
        self.timer_ms = want
        self.timer = GLib.timeout_add(want, self._tick)

    def _tick(self):
        now = time.monotonic()
        for wid, w in self.widgets.items():
            if w.TICK and now - self.last_tick.get(wid, 0) >= w.TICK:
                self.last_tick[wid] = now
                try:
                    w.tick()
                except Exception as exc:  # noqa: BLE001
                    D.log("widget %s tick failed: %s" % (wid, exc))
        self.redraw()
        return True

    def redraw(self):
        for dock in self.app.docks.values():
            if dock.progress > 0.02 and dock.get_visible():
                dock.queue_draw()

    # ---- services for widgets / plugins
    def colors(self):
        g = D.getter(self.app.cfg)
        try:
            return {"accent": parse_color(g("indicators.active_color")), "fg": (1, 1, 1, 0.95),
                    "bg": parse_color(g("appearance.bg_color")), "warn": (1, 0.27, 0.23, 1), "ok": (0.2, 0.84, 0.4, 1)}
        except Exception:  # noqa: BLE001
            return dict(P.DEFAULT_COLORS)

    def notify(self, msg):
        D.toast(msg)

    app_toast = notify

    def terminal_prefix(self):
        return self.app.terminal_prefix()

    def make_app_items(self, app_id):
        try:
            return M.build_items([{"type": "app", "id": app_id}], self.app.entries, [], False)
        except Exception:  # noqa: BLE001
            return []

    def open_child(self, folder, child):
        if child["kind"] == "app":
            its = self.make_app_items(child["id"])
            if its:
                self.stats.record_launch(child["id"])
                self.app.activate(its[0], False, None)
        else:
            D.spawn(["xdg-open", child["path"]])

    # ---- icon overrides
    def override_surface(self, key, s):
        path = self.data["icon_overrides"].get(key)
        if not path:
            return None
        if key not in self.overrides_cache:
            self.overrides_cache[key] = surface_from_path(os.path.expanduser(path), 256, 1)
        return self.overrides_cache[key]

    # ---- popovers
    def item_rect(self, dock, item):
        pos, sizes, _l, m0 = dock.layout()
        m, c, s = dock.item_rect(dock.items.index(item), pos, sizes, m0)
        W, H = dock.area.get_allocated_width(), dock.area.get_allocated_height()
        x, y, w, h = M.place(dock.geo.edge, W, H, m, c, s, s)
        r = Gdk.Rectangle()
        r.x, r.y, r.width, r.height = int(x), int(y), int(w), int(h)
        return r

    def show_popover(self, dock, item, content):
        if self.popover is not None:
            self.popover.popdown()
        pop = Gtk.Popover.new(dock.area)
        pop.set_pointing_to(self.item_rect(dock, item))
        pop.set_position({"bottom": Gtk.PositionType.TOP, "top": Gtk.PositionType.BOTTOM,
                          "left": Gtk.PositionType.RIGHT, "right": Gtk.PositionType.LEFT}[dock.geo.edge])
        pop.set_modal(True)
        if getattr(content, "WANTS_FAN", False):
            pop.get_style_context().add_class("gd-fan")
            content.popover = pop
        pop.add(content)
        content.show_all()
        dock.menu_open = True                      # keeps auto-hide from hiding the dock while the popover is open
        pop.connect("closed", lambda *_: self._popover_closed(dock))
        self.popover = pop
        pop.popup()

    def _popover_closed(self, dock):
        dock.menu_open, dock.pointer_inside, dock.pointer, dock.hover_key = False, False, None, None
        dock.after_pointer()
        dock.reevaluate()
        self.popover = None

    def widget_click(self, item, w, dock, button):
        content = w.on_click(self, dock, item, button)
        if content is not None and dock is not None:
            self.show_popover(dock, item, content)

    def update_hover(self, dock):
        for it in dock.items:
            w = getattr(it, "widget", None)
            if w is None:
                continue
            w.hover = it.key == dock.hover_key
            if w.hover and dock.pointer:
                pos, sizes, _l, m0 = dock.layout()
                m, c, s = dock.item_rect(dock.items.index(it), pos, sizes, m0)
                w.fx = max(0.0, min(1.0, (dock.pointer[0] - m) / max(s, 1.0)))
                w.fy = max(0.0, min(1.0, (dock.pointer[1] - c) / max(s, 1.0)))

    # ---- trash helpers
    def empty_trash(self):
        D.spawn(["gio", "trash", "--empty"])
        GLib.timeout_add(800, lambda: (self.trash.refresh(), False)[1])

    # ---- drag & drop
    def handle_drop(self, dock, item, uris):
        paths = []
        for u in uris:
            p = Gio.File.new_for_uri(u).get_path()
            if p:
                paths.append(p)
        if not paths:
            return False
        w = getattr(item, "widget", None)
        if isinstance(w, FolderWidget):                       # add into an existing fan folder
            fc = self.data["folders"].setdefault(w.id, X.folder_cfg(self.data, w.id))
            for p in paths:
                if p.endswith(".desktop"):
                    fc.setdefault("apps", []).append(os.path.basename(p)[:-8])
                else:
                    fc.setdefault("files", []).append(p)
            X.save(self.data); self.reload()
            return True
        if item is not None and item.kind == "special" and item.special == "trash":
            for p in paths:
                D.spawn(["gio", "trash", p])
            GLib.timeout_add(800, lambda: (self.trash.refresh(), False)[1])
            return True
        ent = getattr(item, "entry", None)
        if ent is not None and not all(p.endswith(".desktop") for p in paths):   # Open files with the selected app
            return self.open_with(ent, uris)
        made = False
        for p in paths:
            if os.path.isdir(p):                                # drag a folder in -> persistent fan folder
                fid = X.new_id(self.data, "folder")
                self.data["extras"].append({"id": fid, "type": "folder", "at": None})
                self.data["folders"][fid] = dict(X.folder_cfg(self.data, fid), name=os.path.basename(p.rstrip("/")) or p, path=p)
                made = True
        if made:
            X.save(self.data); self.reload()
        return made

    def open_with(self, entry, uris):
        eid = str(entry.id)
        for cand in (eid if eid.endswith(".desktop") else eid + ".desktop", eid):
            info = Gio.DesktopAppInfo.new(cand)
            if info is not None:
                try:
                    info.launch_uris(uris, None)
                    self.stats.record_launch(eid)
                    return True
                except GLib.Error as exc:
                    D.toast("Could not open with %s: %s" % (entry.name, exc.message))
                    return False
        return False


class TrashState:
    def __init__(self, on_change):
        self.count, self.on_change = 0, on_change
        self.f = Gio.File.new_for_uri("trash:///")
        try:
            self.mon = self.f.monitor_directory(Gio.FileMonitorFlags.NONE, None)
            self.mon.connect("changed", lambda *_: self.refresh())
        except GLib.Error:
            self.mon = None
        self.refresh()

    def refresh(self):
        try:
            info = self.f.query_info("trash::item-count", Gio.FileQueryInfoFlags.NONE, None)
            n = info.get_attribute_uint32("trash::item-count")
        except GLib.Error:
            n = 0
        if n != self.count:
            self.count = n
            self.on_change()
        return False

    def close(self):
        if self.mon is not None:
            self.mon.cancel()
            self.mon = None


# ------------------------------------------------------------------ runtime patches (originals untouched on disk)
_orig_builtin = D.draw_builtin
_orig_get_item = D.IconCache.get_item


def _patched_builtin(cr, kind, x, y, s, pct=None):
    host = HOST[0]
    if host is not None:
        key = "trash_full" if (kind == "trash" and host.trash.count > 0 and host.override_surface("trash_full", s)) else kind
        ov = host.override_surface(key, s)
        if ov:
            surf, lw, lh = ov
            cr.save()
            if pct:
                rrect(cr, x, y, s, s, s * pct / 100.0); cr.clip()
            cr.translate(x, y); cr.scale(s / lw, s / lh); cr.set_source_surface(surf, 0, 0); cr.paint()
            cr.restore()
            return
    _orig_builtin(cr, kind, x, y, s, pct)
    if host is not None and kind == "trash" and host.trash.count > 0:       # live "full" state on the built-in glyph
        cr.set_source_rgba(1, 1, 1, 0.95)
        for dx, rot in ((-0.09, -0.5), (0.07, 0.45)):
            cr.save(); cr.translate(x + s * (0.5 + dx), y + s * 0.30); cr.rotate(rot)
            rrect(cr, -s * 0.07, -s * 0.09, s * 0.14, s * 0.14, s * 0.02); cr.fill(); cr.restore()


def _patched_get_item(self, it, px, scale, window):
    w = getattr(it, "widget", None)
    if w is not None:                                       # widgets render themselves each frame
        return w.render_surface(px, scale, HOST[0].icon_pct if HOST[0] else None)
    return _orig_get_item(self, it, px, scale, window)


def install_patches():
    D.draw_builtin = _patched_builtin
    D.IconCache.get_item = _patched_get_item


# ------------------------------------------------------------------ subclasses
class DockWindowX(D.DockWindow):
    def __init__(self, app, output):
        super().__init__(app, output)
        self.area.drag_dest_set(Gtk.DestDefaults.ALL, [Gtk.TargetEntry.new("text/uri-list", 0, 0)], Gdk.DragAction.COPY)
        self.area.connect("drag-data-received", self.on_drop)

    def on_drop(self, w, ctx, x, y, data, info, t):
        uris = list(data.get_uris() or [])
        if not uris and data.get_text():
            uris = [ln.strip() for ln in data.get_text().splitlines() if ln.strip().startswith("file://")]
        ok = False
        if uris and self.geo is not None:
            W, H = self.area.get_allocated_width(), self.area.get_allocated_height()
            m, c = M.unplace(self.geo.edge, W, H, x, y)
            ok = self.app.host.handle_drop(self, self.item_at(m, c), uris)
        Gtk.drag_finish(ctx, ok, False, t)

    def after_pointer(self):
        super().after_pointer()
        if self.app.host is not None:
            self.app.host.update_hover(self)

    def on_draw(self, widget, cr):
        ret = super().on_draw(widget, cr)
        if self.app.host is not None:
            draw_badges(self, cr, self.app.host.badges)
        return ret


class DockAppX(D.DockApp):
    def __init__(self):
        super().__init__()
        self.host = None
        self.extras_reload_id = None

    def run(self):
        install_patches()
        return super().run()

    def rebuild(self):                       # Rebuild the normal dock with the integrated extension items.
        if self.host is None:
            self.host = ExtrasHost(self)
            HOST[0] = self.host
        g = D.getter(self.cfg)
        self.host.icon_pct = g("appearance.icon_radius")
        self.items = self.host.inject(M.build_items(self.cfg["items"], self.entries, self.windows,
                                                    g("behavior.show_running_unpinned")))
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
                dock = DockWindowX(self, out)
                self.docks[name] = dock
            dock.apply(C.effective(self.cfg, name), self.items, self.windows, name in self.fullscreen_outs)
        self.apply_blur()

    def reload_config(self):
        self.entries = D.load_entries()
        self.cfg = C.load_config(entries=self.entries)
        self.configure_extensions()
        if self.host is not None:
            self.host.reload(rebuild=False)
        self.blur_applied = None
        self.rebuild()
        return False

    def shutdown(self):
        if self.host is not None:
            self.host.shutdown()
        super().shutdown()

    def watch_config(self):
        super().watch_config()
        if self.monitor is not None:
            self.monitor.connect("changed", self._extras_changed)

    def _extras_changed(self, mon, f, other, event):
        path = f.get_path() or ""
        if f.get_basename() != "extensions.json" and not any(
                path == directory or path.startswith(directory + os.sep)
                for directory in plugin_search_dirs(self.cfg)):
            return
        if self.extras_reload_id is None:
            self.extras_reload_id = GLib.timeout_add(250, self._extras_reload)

    def _extras_reload(self):
        self.extras_reload_id = None
        if self.host is not None:
            self.host.reload()
        return False

    def activate(self, item, new_instance=False, dock=None):
        w = getattr(item, "widget", None)
        if w is not None:
            self.host.widget_click(item, w, dock, 2 if new_instance else 1)
            return
        if item.kind == "special" and item.special == "trash" and new_instance:    # shift/middle-click = Empty Trash
            self.host.empty_trash()
            return
        if getattr(item, "entry", None) is not None and (not item.windows or new_instance):
            self.host.stats.record_launch(item.entry.id)
        super().activate(item, new_instance, dock)


def main():
    sys.exit(DockAppX().run())


if __name__ == "__main__":
    main()
