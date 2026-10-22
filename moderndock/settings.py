#!/usr/bin/env python3
"""ModernDock settings: a schema-driven GTK3 app.

One control is generated for every entry of config.SCHEMA, so a visible
setting always maps to a real, validated, dock-consumed option. Changes are
saved (debounced) and pushed to the running dock over its control socket.
"""
import json
import math
import os
import subprocess
import sys
import threading

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

import cairo  # noqa: E402

from . import __version__  # noqa: E402
from .core import config as C  # noqa: E402
from .core import control, sway  # noqa: E402
from .core.colors import normalize_color, parse_color, with_alpha  # noqa: E402
from .core.desktop import is_launchable, load_entries  # noqa: E402
from .core.themes import CUSTOM, THEMES, theme_label  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CONTROL_TYPES = ("bool", "int", "float", "choice", "color", "text")  # types make_control supports


# --------------------------------------------------------------------- store

class Store:
    """Holds the working config, validates edits, saves and notifies the dock."""

    def __init__(self):
        self.entries = load_entries()
        self.cfg = C.load_config(entries=self.entries)
        self.listeners = []
        self.save_id = None
        self.on_saved = None

    def listen(self, fn):
        self.listeners.append(fn)

    def get(self, key):
        return C.get_path(self.cfg, key)

    def set(self, key, value):
        try:
            value = C.coerce(C.SETTINGS[key], value)
        except (ValueError, TypeError):
            return
        C.set_path(self.cfg, key, value)
        if key in C.THEME_KEYS:
            self.cfg["theme"] = next((n for n in THEMES if C.matches_theme(self.cfg, n)), CUSTOM)
        self.changed()

    def reset(self, key):
        self.set(key, C.default_value(key))

    def reset_all_settings(self):
        keep_items, keep_mon = self.cfg["items"], self.cfg["monitors"]
        self.cfg = C.default_config(self.entries)
        self.cfg["items"], self.cfg["monitors"] = keep_items, keep_mon
        self.changed()

    def apply_theme(self, name):
        C.apply_theme(self.cfg, name)
        self.changed()

    def set_items(self, items):
        self.cfg["items"] = C.validate_items(items)
        self.changed()

    def reset_items(self):
        self.cfg["items"] = C.default_items(self.entries)
        self.changed()

    # monitors
    def monitor(self, name):
        return dict(self.cfg["monitors"].get(name, {}))

    def set_monitor(self, name, key, value):
        ov = self.cfg["monitors"].setdefault(name, {})
        if value is None:
            ov.pop(key, None)
        else:
            ov[key] = value
        self.cfg["monitors"] = C.validate_monitors(self.cfg["monitors"])
        self.changed()

    def forget_monitor(self, name):
        self.cfg["monitors"].pop(name, None)
        self.changed()

    def changed(self):
        for fn in list(self.listeners):
            fn()
        if self.save_id is not None:
            GLib.source_remove(self.save_id)
        self.save_id = GLib.timeout_add(150, self._save)

    def _save(self):
        self.save_id = None
        try:
            C.save_config(self.cfg)
        except OSError as exc:
            if self.on_saved:
                self.on_saved("Could not save: %s" % exc, False)
            return False
        threading.Thread(target=self._notify, daemon=True).start()
        return False

    def _notify(self):
        reply = control.send_command({"cmd": "reload"})
        msg = "Saved · applied to running dock" if reply else "Saved · dock is not running"
        GLib.idle_add(lambda: self.on_saved and self.on_saved(msg, True))

    def flush(self):
        if self.save_id is not None:
            GLib.source_remove(self.save_id)
            self.save_id = None
            C.save_config(self.cfg)
            control.send_command({"cmd": "reload"}, timeout=0.5)


# ------------------------------------------------------------------ controls

def make_control(setting, value, on_change):
    """Build the widget for one setting. Returns (widget, set_value(v))."""
    t = setting.type
    busy = {"v": False}

    def guarded(fn):
        def inner(*a):
            if not busy["v"]:
                fn(*a)
        return inner

    if t == "bool":
        w = Gtk.Switch()
        w.set_valign(Gtk.Align.CENTER)
        w.set_active(bool(value))
        w.connect("notify::active", guarded(lambda *_: on_change(w.get_active())))

        def setv(v):
            busy["v"] = True
            w.set_active(bool(v))
            busy["v"] = False
        return w, setv

    if t in ("int", "float"):
        digits = 0 if t == "int" else (2 if (setting.step or 1) < 0.1 else 1)
        w = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, setting.min, setting.max, setting.step or 1)
        w.set_digits(digits)
        w.set_value(float(value))
        w.set_draw_value(True)
        w.set_value_pos(Gtk.PositionType.RIGHT)
        w.set_size_request(280, -1)
        unit = (" " + setting.unit) if setting.unit else ""
        w.connect("format-value", lambda s, v: ("%.*f" % (digits, v)) + unit)
        w.connect("value-changed", guarded(lambda *_: on_change(w.get_value())))

        def setv(v):
            busy["v"] = True
            w.set_value(float(v))
            busy["v"] = False
        return w, setv

    if t == "choice":
        w = Gtk.ComboBoxText()
        for val, label in setting.choices:
            w.append(val, label)
        w.set_active_id(str(value))
        w.set_valign(Gtk.Align.CENTER)
        w.connect("changed", guarded(lambda *_: on_change(w.get_active_id())))

        def setv(v):
            busy["v"] = True
            w.set_active_id(str(v))
            busy["v"] = False
        return w, setv

    if t == "color":
        w = Gtk.ColorButton()
        w.set_use_alpha(False)
        rgba = Gdk.RGBA()
        rgba.parse(str(value))
        w.set_rgba(rgba)
        w.set_valign(Gtk.Align.CENTER)

        def picked(*_):
            try:
                on_change(normalize_color(w.get_rgba().to_string()))
            except ValueError:
                pass
        w.connect("color-set", guarded(picked))

        def setv(v):
            busy["v"] = True
            r = Gdk.RGBA()
            r.parse(str(v))
            w.set_rgba(r)
            busy["v"] = False
        return w, setv

    if t == "text":
        w = Gtk.Entry()
        w.set_width_chars(22)
        w.set_text(str(value))
        w.set_valign(Gtk.Align.CENTER)
        w.connect("changed", guarded(lambda *_: on_change(w.get_text())))

        def setv(v):
            busy["v"] = True
            w.set_text(str(v))
            busy["v"] = False
        return w, setv

    raise ValueError("no control for setting type %r" % t)


def depends_met(setting, store):
    if not setting.depends:
        return True
    key, req = setting.depends
    cur = store.get(key)
    return cur in req if isinstance(req, tuple) else cur == req


class SettingRow(Gtk.Box):
    def __init__(self, setting, store):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.setting, self.store = setting, store
        self.set_margin_start(16)
        self.set_margin_end(16)
        self.set_margin_top(6)
        self.set_margin_bottom(6)
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title = Gtk.Label(label=setting.label, xalign=0)
        left.pack_start(title, False, False, 0)
        if setting.help:
            h = Gtk.Label(label=setting.help, xalign=0)
            h.set_line_wrap(True)
            h.set_max_width_chars(48)
            h.get_style_context().add_class("dim-label")
            left.pack_start(h, False, False, 0)
        self.pack_start(left, True, True, 0)
        self.control, self._setv = make_control(setting, store.get(setting.key),
                                                lambda v: store.set(setting.key, v))
        self.pack_start(self.control, False, False, 0)
        self.reset_btn = Gtk.Button.new_from_icon_name("edit-undo-symbolic", Gtk.IconSize.BUTTON)
        self.reset_btn.set_relief(Gtk.ReliefStyle.NONE)
        self.reset_btn.set_tooltip_text("Reset to default")
        self.reset_btn.set_valign(Gtk.Align.CENTER)
        self.reset_btn.connect("clicked", lambda *_: store.reset(setting.key))
        self.pack_start(self.reset_btn, False, False, 0)
        self.refresh()

    def refresh(self):
        cur = self.store.get(self.setting.key)
        self._setv(cur)
        self.reset_btn.set_sensitive(cur != self.setting.default)
        self.set_sensitive(depends_met(self.setting, self.store))


def scrolled(child):
    sw = Gtk.ScrolledWindow()
    sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    sw.add(child)
    return sw


def page_box():
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    box.set_margin_top(8)
    box.set_margin_bottom(16)
    return box


def heading(text, sub=None):
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    box.set_margin_start(16)
    box.set_margin_end(16)
    box.set_margin_top(10)
    box.set_margin_bottom(8)
    lbl = Gtk.Label(xalign=0)
    lbl.set_markup("<span size='large' weight='bold'>%s</span>" % GLib.markup_escape_text(text))
    box.pack_start(lbl, False, False, 0)
    if sub:
        s = Gtk.Label(label=sub, xalign=0)
        s.set_line_wrap(True)
        s.get_style_context().add_class("dim-label")
        box.pack_start(s, False, False, 0)
    return box


# --------------------------------------------------------------- theme cards

def draw_theme_preview(cr, w, h, get):
    """Mini dock preview. `get(key)` returns a value for a theme key."""
    pat = cairo.LinearGradient(0, 0, w, h)
    pat.add_color_stop_rgb(0, 0.10, 0.18, 0.30)
    pat.add_color_stop_rgb(1, 0.45, 0.22, 0.50)
    cr.set_source(pat)
    cr.paint()
    dw, dh = w * 0.78, h * 0.34
    x, y = (w - dw) / 2, h - dh - h * 0.14
    r = min(get("appearance.corner_radius") * 0.45, dh / 2)
    op = get("appearance.bg_opacity")

    def path(px, py, pw, ph, rad):
        cr.new_sub_path()
        cr.arc(px + pw - rad, py + rad, rad, -math.pi / 2, 0)
        cr.arc(px + pw - rad, py + ph - rad, rad, 0, math.pi / 2)
        cr.arc(px + rad, py + ph - rad, rad, math.pi / 2, math.pi)
        cr.arc(px + rad, py + rad, rad, math.pi, 1.5 * math.pi)
        cr.close_path()

    path(x, y, dw, dh, r)
    c1 = with_alpha(parse_color(get("appearance.bg_color")), op)
    if get("appearance.bg_gradient"):
        c2 = with_alpha(parse_color(get("appearance.bg_color2")), op)
        d = get("appearance.gradient_direction")
        g = cairo.LinearGradient(x, y, x + (dw if d != "vertical" else 0), y + (dh if d != "horizontal" else 0))
        g.add_color_stop_rgba(0, *c1)
        g.add_color_stop_rgba(1, *c2)
        cr.set_source(g)
    else:
        cr.set_source_rgba(*c1)
    cr.fill_preserve()
    cr.set_source_rgba(*with_alpha(parse_color(get("appearance.border_color")), get("appearance.border_opacity")))
    cr.set_line_width(max(0.5, get("appearance.border_width")))
    cr.stroke()
    n, size = 5, dh * 0.58
    gap = (dw - n * size) / (n + 1)
    hues = [(0.95, 0.45, 0.30), (0.30, 0.75, 0.45), (0.30, 0.55, 0.95), (0.95, 0.75, 0.25), (0.70, 0.40, 0.90)]
    for i in range(n):
        ix = x + gap + i * (size + gap)
        path(ix, y + (dh - size) / 2 - 1, size, size, size * 0.24)
        cr.set_source_rgb(*hues[i])
        cr.fill()
    ind = parse_color(get("indicators.color"))
    cr.set_source_rgba(*ind)
    cr.arc(x + gap + 2 * (size + gap) + size / 2, y + dh - 4, 1.6, 0, 2 * math.pi)
    cr.fill()


class ThemesPage(Gtk.Box):
    def __init__(self, store):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.store = store
        self.pack_start(heading("Themes", "Pick a starting point. Any edit under Colors & Style switches to Custom."),
                        False, False, 0)
        self.flow = Gtk.FlowBox()
        self.flow.set_selection_mode(Gtk.SelectionMode.NONE)
        self.flow.set_max_children_per_line(3)
        self.flow.set_margin_start(12)
        self.flow.set_margin_end(12)
        self.flow.set_homogeneous(True)
        self.flow.set_row_spacing(10)
        self.flow.set_column_spacing(10)
        self.buttons = {}
        for name in list(THEMES) + [CUSTOM]:
            self.flow.add(self.card(name))
        self.pack_start(self.flow, False, False, 0)
        note = Gtk.Label(xalign=0)
        note.set_markup("<small>“Inspired” themes are visual homages. True background blur needs SwayFX "
                        "(Colors &amp; Style → Background blur); on plain Sway the dock is translucent only.</small>")
        note.set_line_wrap(True)
        note.set_margin_start(16)
        note.set_margin_end(16)
        note.set_margin_top(12)
        self.pack_start(note, False, False, 0)
        store.listen(self.refresh)
        self.refresh()

    def card(self, name):
        btn = Gtk.Button()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        area = Gtk.DrawingArea()
        area.set_size_request(210, 92)
        if name == CUSTOM:
            area.connect("draw", lambda w, cr: draw_theme_preview(
                cr, w.get_allocated_width(), w.get_allocated_height(), self.store.get) or False)
            desc = "Your own edits."
        else:
            vals = THEMES[name]["values"]
            area.connect("draw", lambda w, cr, v=vals: draw_theme_preview(
                cr, w.get_allocated_width(), w.get_allocated_height(), lambda k: v[k]) or False)
            desc = THEMES[name]["description"]
        box.pack_start(area, False, False, 0)
        title = Gtk.Label(label=theme_label(name), xalign=0)
        box.pack_start(title, False, False, 0)
        d = Gtk.Label(label=desc, xalign=0)
        d.set_line_wrap(True)
        d.set_max_width_chars(26)
        d.get_style_context().add_class("dim-label")
        box.pack_start(d, False, False, 0)
        btn.add(box)
        btn.connect("clicked", lambda *_: self.store.apply_theme(name) if name != CUSTOM else None)
        btn.set_sensitive(True)
        self.buttons[name] = (btn, area)
        return btn

    def refresh(self):
        cur = self.store.cfg.get("theme")
        for name, (btn, area) in self.buttons.items():
            ctx = btn.get_style_context()
            if name == cur:
                ctx.add_class("suggested-action")
            else:
                ctx.remove_class("suggested-action")
            if name == CUSTOM:
                area.queue_draw()


# ------------------------------------------------------------------ launchers

def gicon_for(icon):
    if icon and os.path.isabs(icon) and os.path.exists(icon):
        return Gio.FileIcon.new(Gio.File.new_for_path(icon))
    return Gio.ThemedIcon.new_with_default_fallbacks(icon or "application-x-executable")


class AppPicker(Gtk.Dialog):
    def __init__(self, parent, entries):
        super().__init__(title="Add application", transient_for=parent, modal=True)
        self.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Add", Gtk.ResponseType.OK)
        self.set_default_size(460, 520)
        box = self.get_content_area()
        self.search = Gtk.SearchEntry()
        self.search.set_margin_start(8)
        self.search.set_margin_end(8)
        self.search.set_margin_top(8)
        box.pack_start(self.search, False, False, 0)
        self.listbox = Gtk.ListBox()
        self.listbox.set_filter_func(self._filter)
        names = [e for e in entries.values() if is_launchable(e, ())]
        for e in sorted(names, key=lambda e: e.name.lower()):
            row = Gtk.ListBoxRow()
            row.entry_id = e.id
            row.text = ("%s %s %s" % (e.name, e.generic_name, e.id)).lower()
            hb = Gtk.Box(spacing=10)
            hb.set_margin_start(8)
            hb.set_margin_top(4)
            hb.set_margin_bottom(4)
            img = Gtk.Image.new_from_gicon(gicon_for(e.icon), Gtk.IconSize.DND)
            img.set_pixel_size(32)
            hb.pack_start(img, False, False, 0)
            hb.pack_start(Gtk.Label(label=e.name, xalign=0), True, True, 0)
            row.add(hb)
            self.listbox.add(row)
        self.listbox.connect("row-activated", lambda *_: self.response(Gtk.ResponseType.OK))
        box.pack_start(scrolled(self.listbox), True, True, 8)
        self.search.connect("search-changed", lambda *_: self.listbox.invalidate_filter())
        self.show_all()

    def _filter(self, row):
        q = self.search.get_text().strip().lower()
        return all(tok in row.text for tok in q.split())

    def selected_id(self):
        row = self.listbox.get_selected_row()
        return row.entry_id if row else None


class LauncherDialog(Gtk.Dialog):
    def __init__(self, parent, spec=None):
        super().__init__(title="Custom launcher", transient_for=parent, modal=True)
        self.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Save", Gtk.ResponseType.OK)
        grid = Gtk.Grid(column_spacing=10, row_spacing=8)
        grid.set_margin_start(14)
        grid.set_margin_end(14)
        grid.set_margin_top(14)
        grid.set_margin_bottom(8)
        self.name = Gtk.Entry()
        self.exec = Gtk.Entry()
        self.icon = Gtk.Entry()
        self.match = Gtk.Entry()
        self.name.set_hexpand(True)
        self.icon.set_placeholder_text("icon name or image path")
        self.match.set_placeholder_text("optional: window app_id / class to show as running")
        rows = [("Name", self.name), ("Command", self.exec), ("Icon", self.icon), ("Match", self.match)]
        for i, (label, widget) in enumerate(rows):
            grid.attach(Gtk.Label(label=label, xalign=1), 0, i, 1, 1)
            grid.attach(widget, 1, i, 1, 1)
        browse = Gtk.Button(label="Browse…")
        browse.connect("clicked", self.browse)
        grid.attach(browse, 2, 2, 1, 1)
        self.get_content_area().add(grid)
        if spec:
            self.name.set_text(spec.get("name", ""))
            self.exec.set_text(spec.get("exec", ""))
            self.icon.set_text(spec.get("icon", ""))
            self.match.set_text(spec.get("match", ""))
        self.ok = self.get_widget_for_response(Gtk.ResponseType.OK)
        for w in (self.name, self.exec):
            w.connect("changed", self.check)
        self.check()
        self.show_all()

    def check(self, *_):
        self.ok.set_sensitive(bool(self.name.get_text().strip() and self.exec.get_text().strip()))

    def browse(self, *_):
        dlg = Gtk.FileChooserNative(title="Choose icon", transient_for=self, action=Gtk.FileChooserAction.OPEN)
        if dlg.run() == Gtk.ResponseType.ACCEPT:
            self.icon.set_text(dlg.get_filename())

    def spec(self):
        s = {"type": "launcher", "name": self.name.get_text().strip(), "exec": self.exec.get_text().strip(),
             "icon": self.icon.get_text().strip()}
        if self.match.get_text().strip():
            s["match"] = self.match.get_text().strip()
        return s


class LaunchersPage(Gtk.Box):
    def __init__(self, store, window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.store, self.window = store, window
        self.loading = False
        self.pack_start(heading("Launchers", "Drag rows to reorder. Items stay in this order on the dock. "
                                "Running apps that are not pinned appear after a divider."), False, False, 0)
        self.model = Gtk.ListStore(Gio.Icon, str, str)  # gicon, label, json
        self.tree = Gtk.TreeView(model=self.model)
        self.tree.set_headers_visible(False)
        self.tree.set_reorderable(True)
        pix = Gtk.CellRendererPixbuf()
        pix.set_property("stock-size", Gtk.IconSize.LARGE_TOOLBAR)
        col = Gtk.TreeViewColumn("Item")
        col.pack_start(pix, False)
        col.add_attribute(pix, "gicon", 0)
        txt = Gtk.CellRendererText()
        txt.set_property("xpad", 8)
        col.pack_start(txt, True)
        col.add_attribute(txt, "text", 1)
        self.tree.append_column(col)
        self.tree.connect("row-activated", self.edit_row)
        self.model.connect("row-deleted", lambda *_: GLib.idle_add(self.sync_from_model))
        sw = scrolled(self.tree)
        sw.set_margin_start(16)
        sw.set_margin_end(16)
        sw.set_size_request(-1, 280)
        sw.set_shadow_type(Gtk.ShadowType.IN)
        self.pack_start(sw, True, True, 0)

        bar = Gtk.FlowBox()
        bar.set_selection_mode(Gtk.SelectionMode.NONE)
        bar.set_margin_start(12)
        bar.set_margin_end(12)
        bar.set_margin_top(8)
        bar.set_margin_bottom(8)
        bar.set_max_children_per_line(5)
        for label, cb in [
            ("Add application…", self.add_app), ("Add custom launcher…", self.add_custom),
            ("Add separator", lambda *_: self.append({"type": "separator"})),
            ("Add Applications button", lambda *_: self.append({"type": "special", "kind": "apps"})),
            ("Add Trash", lambda *_: self.append({"type": "special", "kind": "trash"})),
            ("Move up", lambda *_: self.move(-1)), ("Move down", lambda *_: self.move(1)),
            ("Remove", self.remove), ("Reset to defaults", self.reset),
        ]:
            b = Gtk.Button(label=label)
            b.connect("clicked", cb)
            bar.add(b)
        self.pack_start(bar, False, False, 0)
        self.load()

    # model <-> config
    def describe(self, spec):
        t = spec["type"]
        if t == "separator":
            return gicon_for("list-remove-symbolic"), "──  Separator  ──"
        if t == "special":
            info = C.SPECIAL_KINDS[spec["kind"]]
            return gicon_for(info["icon"]), info["name"] + " (built-in)"
        if t == "launcher":
            return gicon_for(spec.get("icon")), spec["name"] + "  ·  custom launcher"
        entry = self.store.entries.get(spec["id"])
        if entry is None:
            return gicon_for("dialog-question-symbolic"), "%s  (not installed)" % spec["id"]
        return gicon_for(entry.icon), entry.name

    def load(self):
        self.loading = True
        self.model.clear()
        for spec in self.store.cfg["items"]:
            icon, label = self.describe(spec)
            self.model.append([icon, label, json.dumps(spec)])
        self.loading = False

    def sync_from_model(self):
        if self.loading:
            return False
        items = [json.loads(row[2]) for row in self.model]
        if items != self.store.cfg["items"]:
            self.store.set_items(items)
        return False

    def commit(self, items):
        self.store.set_items(items)
        self.load()

    def current_items(self):
        return [json.loads(r[2]) for r in self.model]

    def selected_index(self):
        sel = self.tree.get_selection().get_selected_rows()[1]
        return sel[0].get_indices()[0] if sel else None

    def append(self, spec):
        self.commit(self.current_items() + [spec])

    def add_app(self, *_):
        dlg = AppPicker(self.window, self.store.entries)
        if dlg.run() == Gtk.ResponseType.OK and dlg.selected_id():
            sid = dlg.selected_id()
            if not any(i.get("id") == sid for i in self.current_items()):
                self.append({"type": "app", "id": sid})
        dlg.destroy()

    def add_custom(self, *_):
        dlg = LauncherDialog(self.window)
        if dlg.run() == Gtk.ResponseType.OK:
            self.append(dlg.spec())
        dlg.destroy()

    def edit_row(self, tree, path, col):
        idx = path.get_indices()[0]
        items = self.current_items()
        if items[idx]["type"] != "launcher":
            return
        dlg = LauncherDialog(self.window, items[idx])
        if dlg.run() == Gtk.ResponseType.OK:
            items[idx] = dlg.spec()
            self.commit(items)
        dlg.destroy()

    def move(self, delta):
        i = self.selected_index()
        items = self.current_items()
        if i is None or not 0 <= i + delta < len(items):
            return
        items[i], items[i + delta] = items[i + delta], items[i]
        self.commit(items)
        self.tree.get_selection().select_path(Gtk.TreePath(i + delta))

    def remove(self, *_):
        i = self.selected_index()
        if i is None:
            return
        items = self.current_items()
        del items[i]
        self.commit(items)

    def reset(self, *_):
        self.store.reset_items()
        self.load()


# ------------------------------------------------------------------- monitors

class OverrideRow(Gtk.Box):
    def __init__(self, setting, store, output):
        super().__init__(spacing=12)
        self.setting, self.store, self.output = setting, store, output
        self.set_margin_start(16)
        self.set_margin_end(16)
        self.set_margin_top(6)
        self.set_margin_bottom(6)
        self.check = Gtk.CheckButton(label=setting.label)
        self.pack_start(self.check, True, True, 0)
        ov = store.monitor(output)
        has = setting.key in ov
        value = ov.get(setting.key, store.get(setting.key))
        self.control, self.setv = make_control(setting, value, self.on_value)
        self.pack_start(self.control, False, False, 0)
        self.check.set_active(has)
        self.control.set_sensitive(has)
        self.check.connect("toggled", self.on_toggle)

    def on_toggle(self, *_):
        on = self.check.get_active()
        self.control.set_sensitive(on)
        if on:
            self.store.set_monitor(self.output, self.setting.key, self.store.get(self.setting.key))
            self.setv(self.store.get(self.setting.key))
        else:
            self.store.set_monitor(self.output, self.setting.key, None)

    def on_value(self, v):
        if self.check.get_active():
            try:
                v = C.coerce(self.setting, v)
            except (ValueError, TypeError):
                return
            self.store.set_monitor(self.output, self.setting.key, v)


class MonitorsPage(Gtk.Box):
    def __init__(self, store):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.store = store
        self.pack_start(heading("Monitors", "Each connected monitor gets its own dock. Choose a monitor to "
                                "disable its dock or override a few settings just for it."), False, False, 0)
        top = Gtk.Box(spacing=8)
        top.set_margin_start(16)
        top.set_margin_end(16)
        self.combo = Gtk.ComboBoxText.new_with_entry()
        self.combo.set_size_request(260, -1)
        top.pack_start(Gtk.Label(label="Monitor"), False, False, 0)
        top.pack_start(self.combo, False, False, 0)
        refresh = Gtk.Button(label="Detect monitors")
        refresh.connect("clicked", lambda *_: self.detect())
        top.pack_start(refresh, False, False, 0)
        self.pack_start(top, False, False, 0)
        self.msg = Gtk.Label(xalign=0)
        self.msg.set_margin_start(16)
        self.msg.get_style_context().add_class("dim-label")
        self.pack_start(self.msg, False, False, 4)
        self.body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.pack_start(self.body, False, False, 0)
        self.combo.connect("changed", lambda *_: self.rebuild())
        self.detect()

    def detect(self):
        names = []
        err = ""
        try:
            ipc = sway.SwayIPC()
            names = [o["name"] for o in sway.parse_outputs(ipc.get_outputs())]
            ipc.close()
        except (sway.SwayError, OSError) as exc:
            err = "Could not query Sway (%s). Type an output name (e.g. eDP-1) to configure it." % exc
        for n in self.store.cfg["monitors"]:
            if n not in names:
                names.append(n)
        self.combo.remove_all()
        for n in names:
            self.combo.append_text(n)
        if names:
            self.combo.set_active(0)
        self.msg.set_text(err or ("%d monitor(s) found." % len(names)))
        self.rebuild()

    def current(self):
        return (self.combo.get_active_text() or "").strip()

    def rebuild(self):
        for c in self.body.get_children():
            c.destroy()
        name = self.current()
        if not name:
            return
        row = Gtk.Box(spacing=12)
        row.set_margin_start(16)
        row.set_margin_end(16)
        row.set_margin_top(10)
        row.pack_start(Gtk.Label(label="Show a dock on this monitor", xalign=0), True, True, 0)
        sw = Gtk.Switch()
        sw.set_active(C.monitor_enabled(self.store.cfg, name))
        sw.connect("notify::active", lambda s, *_: self.store.set_monitor(name, "enabled", s.get_active()))
        row.pack_start(sw, False, False, 0)
        self.body.pack_start(row, False, False, 0)
        for key in C.MONITOR_OVERRIDE_KEYS:
            self.body.pack_start(OverrideRow(C.SETTINGS[key], self.store, name), False, False, 0)
        forget = Gtk.Button(label="Remove all overrides for this monitor")
        forget.set_halign(Gtk.Align.START)
        forget.set_margin_start(16)
        forget.set_margin_top(10)
        forget.connect("clicked", lambda *_: (self.store.forget_monitor(name), self.rebuild()))
        self.body.pack_start(forget, False, False, 0)
        self.body.show_all()


# --------------------------------------------------------------------- status

class StatusPage(Gtk.Box):
    def __init__(self, store):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.store = store
        self.pack_start(heading("Status", "Live information from the running dock."), False, False, 0)
        self.info = Gtk.Label(xalign=0, yalign=0)
        self.info.set_margin_start(16)
        self.info.set_selectable(True)
        self.pack_start(self.info, False, False, 0)
        bar = Gtk.Box(spacing=8)
        bar.set_margin_start(16)
        bar.set_margin_top(10)
        for label, cb in [("Refresh", lambda *_: self.refresh()), ("Start dock", self.start),
                          ("Restart dock", self.restart), ("Stop dock", self.stop),
                          ("Open config folder", self.open_folder)]:
            b = Gtk.Button(label=label)
            b.connect("clicked", cb)
            bar.pack_start(b, False, False, 0)
        self.pack_start(bar, False, False, 0)
        note = Gtk.Label(xalign=0)
        note.set_markup(
            "<small>Blur: ModernDock only reports blur as active if SwayFX accepted the "
            "<tt>layer_effects</tt> command; otherwise the dock is translucent without blur.</small>")
        note.set_line_wrap(True)
        note.set_margin_start(16)
        note.set_margin_end(16)
        note.set_margin_top(14)
        self.pack_start(note, False, False, 0)
        self.refresh()

    def refresh(self):
        r = control.send_command({"cmd": "status"})
        lines = ["Settings app: v%s" % __version__, "Config file: %s" % C.config_path()]
        if r is None:
            lines.insert(0, "Dock: not running")
        else:
            lines.insert(0, "Dock: running (v%s)" % r.get("version"))
            lines += ["Sway IPC: %s" % ("connected" if r.get("sway_ipc") else "not connected (no running indicators)"),
                      "Monitors with a dock: %s" % (", ".join(r.get("outputs", [])) or "none"),
                      "Open windows seen: %s" % r.get("windows"), "Dock items: %s" % r.get("items"),
                      "Blur: %s" % r.get("blur"), "Theme: %s" % r.get("theme")]
        self.info.set_text("\n".join(lines))

    def _spawn_dock(self):
        # go through the launcher script so the layer-shell preload is applied
        subprocess.Popen([os.path.join(ROOT, "bin", "moderndock")], cwd=ROOT,
                         start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        GLib.timeout_add(900, lambda: (self.refresh(), False)[1])

    def start(self, *_):
        if control.send_command({"cmd": "ping"}) is None:
            self._spawn_dock()
        self.refresh()

    def stop(self, *_):
        control.send_command({"cmd": "quit"})
        GLib.timeout_add(500, lambda: (self.refresh(), False)[1])

    def restart(self, *_):
        control.send_command({"cmd": "quit"})
        GLib.timeout_add(600, lambda: (self._spawn_dock(), False)[1])

    def open_folder(self, *_):
        subprocess.Popen(["xdg-open", C.config_dir()], start_new_session=True)


# --------------------------------------------------------------------- window

class SettingsWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="ModernDock Settings")
        self.set_default_size(980, 700)
        self.store = Store()
        self.store.on_saved = self.on_saved
        self.store.listen(self.refresh_rows)
        self.rows = []
        self.search_rows = []

        hb = Gtk.HeaderBar()
        hb.set_show_close_button(True)
        hb.set_title("ModernDock Settings")
        self.status = Gtk.Label(label="")
        self.status.get_style_context().add_class("dim-label")
        hb.pack_start(self.status)
        reset = Gtk.Button(label="Reset all settings…")
        reset.connect("clicked", self.reset_all)
        hb.pack_end(reset)
        self.set_titlebar(hb)

        paned = Gtk.Paned()
        self.add(paned)
        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.search = Gtk.SearchEntry()
        self.search.set_placeholder_text("Search settings")
        self.search.set_margin_start(8)
        self.search.set_margin_end(8)
        self.search.set_margin_top(8)
        self.search.set_margin_bottom(8)
        self.search.connect("search-changed", self.on_search)
        side.pack_start(self.search, False, False, 0)
        self.sidebar = Gtk.ListBox()
        self.sidebar.connect("row-selected", self.on_select)
        side.pack_start(self.sidebar, True, True, 0)
        side.set_size_request(210, -1)
        paned.pack1(side, False, False)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        paned.pack2(self.stack, True, False)

        self.add_page("themes", "Themes", ThemesPage(self.store))
        for cat, label in C.CATEGORIES:
            self.add_page(cat, label, self.category_page(cat, label))
        self.add_page("launchers", "Launchers", LaunchersPage(self.store, self))
        self.add_page("monitors", "Monitors", MonitorsPage(self.store))
        self.add_page("status", "Status", StatusPage(self.store))
        self.search_box = page_box()
        self.stack.add_named(scrolled(self.search_box), "search")
        self.sidebar.select_row(self.sidebar.get_row_at_index(0))
        self.connect("delete-event", self.on_close)
        self.show_all()

    def add_page(self, name, label, widget):
        if not isinstance(widget, Gtk.ScrolledWindow):
            widget = scrolled(widget)
        self.stack.add_named(widget, name)
        row = Gtk.ListBoxRow()
        row.page = name
        lbl = Gtk.Label(label=label, xalign=0)
        lbl.set_margin_start(14)
        lbl.set_margin_top(9)
        lbl.set_margin_bottom(9)
        row.add(lbl)
        self.sidebar.add(row)

    def category_page(self, cat, label):
        box = page_box()
        box.pack_start(heading(label), False, False, 0)
        for s in C.SCHEMA:
            if s.category == cat:
                row = SettingRow(s, self.store)
                self.rows.append(row)
                box.pack_start(row, False, False, 0)
        return box

    def on_select(self, lb, row):
        if row is not None:
            self.stack.set_visible_child_name(row.page)

    def on_search(self, entry):
        q = entry.get_text().strip().lower()
        for r in self.search_rows:
            r.destroy()
        self.search_rows = []
        for c in self.search_box.get_children():
            c.destroy()
        if not q:
            row = self.sidebar.get_selected_row() or self.sidebar.get_row_at_index(0)
            self.stack.set_visible_child_name(row.page)
            return
        cats = dict(C.CATEGORIES)
        self.search_box.pack_start(heading("Search results", "“%s”" % q), False, False, 0)
        found = 0
        for s in C.SCHEMA:
            hay = " ".join([s.label, s.key, s.help, s.keywords, cats[s.category]]).lower()
            if all(tok in hay for tok in q.split()):
                row = SettingRow(s, self.store)
                self.search_rows.append(row)
                self.search_box.pack_start(row, False, False, 0)
                found += 1
        if not found:
            self.search_box.pack_start(Gtk.Label(label="No matching settings."), False, False, 20)
        self.search_box.show_all()
        self.stack.set_visible_child_name("search")

    def refresh_rows(self):
        for r in self.rows + self.search_rows:
            r.refresh()

    def on_saved(self, msg, ok):
        self.status.set_text(msg)
        return False

    def reset_all(self, *_):
        dlg = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.QUESTION,
                                buttons=Gtk.ButtonsType.OK_CANCEL,
                                text="Reset all appearance and behavior settings?")
        dlg.format_secondary_text("Your launchers and per-monitor settings are kept.")
        if dlg.run() == Gtk.ResponseType.OK:
            self.store.reset_all_settings()
        dlg.destroy()

    def on_close(self, *_):
        self.store.flush()
        return False


def main():
    if Gdk.Display.get_default() is None:
        print("No display available.", file=sys.stderr)
        return 1
    SettingsWindow().connect("destroy", Gtk.main_quit)
    Gtk.main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
