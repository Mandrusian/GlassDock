#!/usr/bin/env python3
"""GlassDock settings: a schema-driven GTK3 app.

One control is generated for every entry of config.SCHEMA, so a visible
setting always maps to a real, validated, dock-consumed option. Changes are
saved (debounced) and pushed to the running dock over its control socket.

Layout: a grouped sidebar, a pinned live dock preview, and card-style pages.
"""
import json
import math
import os
import re
import subprocess
import sys
import threading
import time

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import GLib as _GLib  # noqa: E402

# The dock matches a window to its desktop entry by app_id. On Wayland GTK takes it from
# the program class / prgname, which must therefore equal the desktop file's id.
# Without this the window is unmatched and the dock draws a green letter tile.
_GLib.set_prgname("glassdock-settings")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402
Gdk.set_program_class("glassdock-settings")

import cairo  # noqa: E402

from . import __version__  # noqa: E402
from .core import config as C  # noqa: E402
from .core import control, sway  # noqa: E402
from .core.colors import normalize_color, parse_color, with_alpha  # noqa: E402
from .core.desktop import is_launchable, load_entries  # noqa: E402
from .core.icons import candidate_names, find_icon_file  # noqa: E402
from .core.themes import CUSTOM, THEMES  # noqa: E402
from .core import usertheme as UT  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


CATEGORY_BLURBS = {
    "style": "Colors, borders, shadow and glass effects.",
    "size": "How big the dock and its icons are. Large docks automatically fit the available monitor space.",
    "animation": "Magnification, motion and timing.",
    "indicators": "How running and focused apps are marked.",
    "position": "Which edge the dock lives on.",
    "behavior": "Auto-hide, stacking and dock behavior.",
}

# page name -> (sidebar icon fallbacks)
PAGE_ICONS = {
    "themes": ("applications-graphics-symbolic", "preferences-desktop-theme-symbolic"),
    "style": ("preferences-color-symbolic", "color-select-symbolic"),
    "size": ("view-fullscreen-symbolic", "zoom-fit-best-symbolic"),
    "animation": ("media-playback-start-symbolic", "view-refresh-symbolic"),
    "indicators": ("media-record-symbolic", "emblem-ok-symbolic"),
    "position": ("go-bottom-symbolic", "view-pin-symbolic"),
    "behavior": ("preferences-system-symbolic", "emblem-system-symbolic"),
    "launchers": ("view-app-grid-symbolic", "view-list-symbolic"),
    "extensions": ("applications-utilities-symbolic", "preferences-plugin-symbolic"),
    "monitors": ("video-display-symbolic", "computer-symbolic"),
    "status": ("utilities-system-monitor-symbolic", "dialog-information-symbolic"),
}

# Less frequently changed controls remain available from a focused popup instead
# of taking space on the everyday settings pages.
ADVANCED_SETTING_KEYS = {
    "style": (
        "appearance.bg_color2", "appearance.gradient_direction", "appearance.border_opacity",
        "appearance.border_width", "appearance.corner_radius", "appearance.icon_radius",
        "appearance.shadow_size", "appearance.shadow_opacity", "appearance.label_bg",
        "appearance.label_color",
    ),
    "size": ("size.spacing", "size.padding", "size.margin"),
    "animation": (
        "animation.magnify_factor", "animation.magnify_range", "animation.easing",
    ),
    "indicators": ("indicators.color", "indicators.size"),
    "behavior": (
        "behavior.show_delay", "behavior.hide_delay", "behavior.exclusive_zone",
        "behavior.layer", "behavior.launcher_command", "behavior.autostart_wms",
        "behavior.terminal_command",
    ),
}

PREVIEW_PAGES = {"style", "size", "indicators", "position"}

CSS = b"""
.md-sidebar { background: alpha(@theme_fg_color, 0.04); border-right: 1px solid alpha(@theme_fg_color, 0.14); }
.md-sidebar row { margin: 1px 8px; padding: 0; border-radius: 8px; }
.md-sidebar row:hover { background: alpha(@theme_fg_color, 0.07); }
.md-sidebar row:selected, .md-sidebar row:selected:hover { background: @theme_selected_bg_color; }
.md-sidebar row:selected label, .md-sidebar row:selected image { color: @theme_selected_fg_color; }
.md-sidebar row.md-section, .md-sidebar row.md-section:hover { background: none; margin-top: 10px; }
.md-section-label { font-size: 10px; font-weight: 700; letter-spacing: 1px; opacity: 0.55; }
.md-sidebar-icon { opacity: 0.8; }
.md-search { margin: 10px 8px 4px 8px; }

.md-content { background: @theme_bg_color; }
.md-page-title { font-size: 22px; font-weight: 700; }
.md-page-sub { opacity: 0.65; }
.md-group-title { font-size: 11px; font-weight: 700; letter-spacing: 0.5px; opacity: 0.6; }

.md-card { background: @theme_base_color; border: 1px solid alpha(@theme_fg_color, 0.16); border-radius: 12px; }
list.md-list { background: transparent; border-radius: 12px; }
list.md-list row { background: transparent; border-bottom: 1px solid alpha(@theme_fg_color, 0.11); padding: 0; }
list.md-list row:last-child { border-bottom: none; }
list.md-list row:hover { background: transparent; }
.md-row-title { font-weight: 500; }
.md-row-help { font-size: 12px; opacity: 0.6; }
.md-dependent { padding-left: 22px; }
.md-value { font-feature-settings: "tnum"; opacity: 0.75; min-width: 56px; }
.md-hex { font-family: monospace; font-size: 12px; opacity: 0.6; }
.md-reset { opacity: 0.55; min-width: 28px; min-height: 28px; padding: 0; border-radius: 14px; }
.md-reset:hover { opacity: 1; }
.md-reset:disabled { opacity: 0.18; }

.md-preview { background: transparent; border-radius: 14px; border: 1px solid alpha(@theme_fg_color, 0.16); }
.md-preview-caption { font-size: 11px; opacity: 0.55; }

button.md-theme-card { padding: 8px; border-radius: 14px; background: @theme_base_color;
                       border: 1px solid alpha(@theme_fg_color, 0.16); box-shadow: none; }
button.md-theme-card:hover { background: mix(@theme_base_color, @theme_fg_color, 0.05); }
button.md-theme-card.active { border-color: @theme_selected_bg_color; box-shadow: 0 0 0 2px @theme_selected_bg_color; }
.md-theme-name { font-weight: 600; }
.md-theme-desc { font-size: 12px; opacity: 0.6; }
.md-active-pill { background: @theme_selected_bg_color; color: @theme_selected_fg_color;
                  border-radius: 99px; padding: 0 8px; font-size: 10px; font-weight: 700; }

.md-pill { border-radius: 99px; padding: 2px 10px; font-size: 12px; background: alpha(@theme_fg_color, 0.08); }
.md-pill.ok { background: rgba(46, 194, 126, 0.18); color: #1a8d56; }
.md-pill.bad { background: rgba(224, 27, 36, 0.16); color: #c01c28; }
.md-badge { border-radius: 99px; padding: 2px 10px; font-size: 12px; font-weight: 600; }
.md-badge.ok { background: rgba(46, 194, 126, 0.18); color: #1a8d56; }
.md-badge.off { background: rgba(229, 165, 10, 0.2); color: #a8740a; }
.md-badge.bad { background: rgba(224, 27, 36, 0.16); color: #c01c28; }
.md-key { opacity: 0.6; }
.md-mono { font-family: monospace; font-size: 12px; }

.md-toolbar button { padding: 4px 10px; }
.md-empty { opacity: 0.55; padding: 28px; }
"""


def install_css():
    provider = Gtk.CssProvider()
    try:
        provider.load_from_data(CSS)
    except GLib.Error as exc:  # never let styling stop the app from opening
        print("settings: stylesheet rejected: %s" % exc, file=sys.stderr)
        return
    screen = Gdk.Screen.get_default()
    if screen is not None:
        Gtk.StyleContext.add_provider_for_screen(screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


# --------------------------------------------------------------------- store

class Store:
    """Holds the working config, validates edits, saves and notifies the dock."""

    def __init__(self):
        self.entries = load_entries()
        self.cfg = C.load_config(entries=self.entries)
        self.listeners = []
        self.save_id = None
        self.on_saved = None
        self.ext_listeners = []
        self.last_write = 0.0
        self._ext_id = None
        self._mon = None
        self.watch_file()

    def listen(self, fn):
        self.listeners.append(fn)

    def listen_external(self, fn):
        """Called when config.json was changed by someone else (e.g. the dock)."""
        self.ext_listeners.append(fn)

    def watch_file(self):
        try:
            d = C.config_dir()
            os.makedirs(d, exist_ok=True)
            self._mon = Gio.File.new_for_path(d).monitor_directory(Gio.FileMonitorFlags.WATCH_MOVES, None)
            self._mon.connect("changed", self._on_file)
        except (GLib.Error, OSError):
            self._mon = None

    def _on_file(self, mon, f, other, event):
        names = {x.get_basename() for x in (f, other) if x is not None}
        if "config.json" in names and self._ext_id is None:
            self._ext_id = GLib.timeout_add(150, self._reload_external)

    def _reload_external(self):
        self._ext_id = None
        if self.save_id is not None or time.monotonic() - self.last_write < 0.6:
            return False  # our own write (or edits still pending) wins
        try:
            new = C.load_config(entries=self.entries)
        except Exception as exc:
            print("[glassdock-settings] external config reload failed: %s" % exc, file=sys.stderr)
            return False
        if new == self.cfg:
            return False
        self.cfg = new
        for fn in list(self.ext_listeners) + list(self.listeners):
            try:
                fn()
            except Exception as exc:  # a broken page must not stop the others
                print("[glassdock-settings] refresh failed: %s" % exc, file=sys.stderr)
        if self.on_saved:
            self.on_saved("Updated: the dock changed your settings", True)
        return False

    def get(self, key):
        return C.get_path(self.cfg, key)

    def set(self, key, value):
        try:
            value = C.coerce(C.SETTINGS[key], value)
        except (ValueError, TypeError):
            return
        C.set_path(self.cfg, key, value)
        if key in C.THEME_KEYS:
            self.cfg["theme"] = self.detect_theme()
        self.changed()

    def reset(self, key):
        self.set(key, C.default_value(key))

    def reset_all_settings(self):
        keep_items, keep_mon = self.cfg["items"], self.cfg["monitors"]
        self.cfg = C.default_config(self.entries)
        self.cfg["items"], self.cfg["monitors"] = keep_items, keep_mon
        self.changed()

    def apply_theme(self, name):
        if name == CUSTOM or name in THEMES:
            C.apply_theme(self.cfg, name)
        else:
            info = self.user_themes().get(name)
            if info is None:
                return
            UT.apply_values(self.cfg, info, name)
        self.changed()

    # ---- user themes (see core/usertheme.py). Methods that can fail raise UT.ThemeError
    #      with a message that is safe to show the user.
    def user_themes(self):
        cache = getattr(self, "_user_themes", None)
        if cache is None:
            cache, self.theme_problems = UT.list_user_themes()
            self._user_themes = cache
        return cache

    def reload_user_themes(self):
        self._user_themes = None
        return self.user_themes()

    def all_themes(self):
        """{name: {'label','description','values','user'}}: built-ins first, then the user's."""
        return UT.all_themes(self.user_themes())

    def theme_label(self, name):
        return UT.label_for(name, self.user_themes())

    def detect_theme(self):
        for n in THEMES:
            if C.matches_theme(self.cfg, n):
                return n
        for n, info in self.user_themes().items():
            if UT.matches(self.cfg, info):
                return n
        return CUSTOM

    def save_current_theme(self, label, description=""):
        name = UT.save_theme(self.cfg, label, description)
        self.reload_user_themes()
        self.cfg["theme"] = name
        self.changed()
        return name

    def import_theme(self, path, apply=False):
        """Returns (name, info); info['ignored'] lists settings that were skipped."""
        name, info = UT.import_file(path)
        self.reload_user_themes()
        if apply:
            self.apply_theme(name)
        else:
            self.changed()
        return name, info

    def export_theme(self, name, path):
        if name == CUSTOM:
            info = {"label": "My theme", "description": "", "values": UT.current_values(self.cfg)}
        else:
            info = self.all_themes().get(name)
        if info is None:
            raise UT.ThemeError("That theme no longer exists.")
        UT.export_file(info, path)

    def rename_theme(self, name, label):
        UT.rename_theme(name, label)
        self.reload_user_themes()
        self.changed()

    def delete_theme(self, name):
        removed = UT.delete_theme(name)
        self.reload_user_themes()
        if self.cfg.get("theme") == name:
            self.cfg["theme"] = CUSTOM
        self.changed()
        return removed

    def export_settings(self, path):
        """Write the whole working config (appearance, behavior, launchers, monitors) to `path`."""
        C.save_config(self.cfg, path)

    def import_settings(self, path):
        """Replace appearance and behavior from a settings file. Launchers and monitors are kept.
        Raises ValueError with a message that is safe to show."""
        bad = "That isn't a readable GlassDock settings file."
        try:
            if os.path.getsize(path) > 1024 * 1024:
                raise ValueError("That file is too large to be a settings file.")
            with open(path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
            raise ValueError(bad) from exc
        if not isinstance(raw, dict):
            raise ValueError(bad)
        try:
            new = C.validate(C.migrate(raw), self.entries)
        except (TypeError, ValueError, KeyError, AttributeError, RecursionError) as exc:
            raise ValueError(bad) from exc
        new["items"], new["monitors"] = self.cfg["items"], self.cfg["monitors"]
        self.cfg = new
        self.cfg["theme"] = self.detect_theme()
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
        # A view refresh must not prevent a user change from being persisted.
        for fn in list(self.listeners):
            try:
                fn()
            except Exception as exc:
                print("[glassdock-settings] view refresh failed: %s" % exc, file=sys.stderr)
        if self.save_id is not None:
            GLib.source_remove(self.save_id)
        self.save_id = GLib.timeout_add(150, self._save)

    def _save(self):
        self.save_id = None
        self.last_write = time.monotonic()
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
            self.last_write = time.monotonic()
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
        unit = (" " + setting.unit) if setting.unit else ""
        box = Gtk.Box(spacing=10)
        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, setting.min, setting.max, setting.step or 1)
        scale.set_digits(digits)
        scale.set_draw_value(False)
        scale.set_size_request(160, -1)
        scale.set_hexpand(True)
        scale.set_valign(Gtk.Align.CENTER)
        scale.set_value(float(value))
        readout = Gtk.Label(xalign=1)
        readout.get_style_context().add_class("md-value")

        def show(v):
            readout.set_text(("%.*f" % (digits, v)) + unit)
        show(float(value))
        scale.connect("value-changed", guarded(lambda *_: (show(scale.get_value()), on_change(scale.get_value()))))
        box.pack_start(scale, True, True, 0)
        box.pack_start(readout, False, False, 0)

        def setv(v):
            busy["v"] = True
            scale.set_value(float(v))
            show(float(v))
            busy["v"] = False
        return box, setv

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
        box = Gtk.Box(spacing=8)
        w = Gtk.ColorButton()
        w.set_use_alpha(False)
        w.set_valign(Gtk.Align.CENTER)
        hexlbl = Gtk.Label(label=str(value).upper())
        hexlbl.get_style_context().add_class("md-hex")
        rgba = Gdk.RGBA()
        rgba.parse(str(value))
        w.set_rgba(rgba)

        def picked(*_):
            try:
                v = normalize_color(w.get_rgba().to_string())
            except ValueError:
                return
            hexlbl.set_text(v.upper())
            on_change(v)
        w.connect("color-set", guarded(picked))
        box.pack_start(hexlbl, False, False, 0)
        box.pack_start(w, False, False, 0)

        def setv(v):
            busy["v"] = True
            r = Gdk.RGBA()
            r.parse(str(v))
            w.set_rgba(r)
            hexlbl.set_text(str(v).upper())
            busy["v"] = False
        return box, setv

    if t == "text":
        w = Gtk.Entry()
        w.set_width_chars(14)
        w.set_max_width_chars(28)
        w.set_text(str(value))
        w.set_valign(Gtk.Align.CENTER)
        w.connect("changed", guarded(lambda *_: on_change(w.get_text())))

        def setv(v):
            if w.get_text() != str(v):  # don't move the caret while typing
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


def style(widget, *classes):
    ctx = widget.get_style_context()
    for c in classes:
        ctx.add_class(c)
    return widget


def label(text, *classes, xalign=0.0, wrap=False, selectable=False):
    lbl = Gtk.Label(label=text, xalign=xalign)
    lbl.set_line_wrap(wrap)
    lbl.set_selectable(selectable)
    return style(lbl, *classes)


class SettingRow(Gtk.Box):
    def __init__(self, setting, store):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        self.setting, self.store = setting, store
        for side in ("start", "end"):
            getattr(self, "set_margin_" + side)(16)
        self.set_margin_top(10)
        self.set_margin_bottom(10)
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        left.set_valign(Gtk.Align.CENTER)
        left.pack_start(label(setting.label, "md-row-title"), False, False, 0)
        if setting.help:
            h = label(setting.help, "md-row-help", wrap=True)
            h.set_max_width_chars(52)
            left.pack_start(h, False, False, 0)
        if setting.depends:
            style(left, "md-dependent")
        self.pack_start(left, True, True, 0)
        self.control, self._setv = make_control(setting, store.get(setting.key),
                                                lambda v: store.set(setting.key, v))
        self.control.set_valign(Gtk.Align.CENTER)
        self.pack_start(self.control, False, False, 0)
        self.reset_btn = Gtk.Button.new_from_icon_name("edit-undo-symbolic", Gtk.IconSize.BUTTON)
        self.reset_btn.set_relief(Gtk.ReliefStyle.NONE)
        self.reset_btn.set_tooltip_text("Reset to default")
        self.reset_btn.set_valign(Gtk.Align.CENTER)
        style(self.reset_btn, "md-reset")
        self.reset_btn.connect("clicked", lambda *_: store.reset(setting.key))
        self.pack_start(self.reset_btn, False, False, 0)
        self.refresh()

    def refresh(self):
        cur = self.store.get(self.setting.key)
        self._setv(cur)
        self.reset_btn.set_sensitive(cur != self.setting.default)
        self.set_sensitive(depends_met(self.setting, self.store))


# ------------------------------------------------------------------ layout bits

def scrolled(child):
    sw = Gtk.ScrolledWindow()
    sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    sw.add(child)
    return sw


def page_box():
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    for side in ("start", "end"):
        getattr(box, "set_margin_" + side)(28)
    box.set_margin_top(22)
    box.set_margin_bottom(28)
    return box


def heading(text, sub=None):
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
    box.set_margin_bottom(16)
    box.pack_start(label(text, "md-page-title"), False, False, 0)
    if sub:
        box.pack_start(label(sub, "md-page-sub", wrap=True), False, False, 0)
    return box


def group_title(text):
    lbl = label(text.upper(), "md-group-title")
    lbl.set_margin_top(18)
    lbl.set_margin_bottom(6)
    lbl.set_margin_start(4)
    return lbl


def card(child=None):
    frame = style(Gtk.Box(orientation=Gtk.Orientation.VERTICAL), "md-card")
    if child is not None:
        frame.pack_start(child, True, True, 0)
    return frame


def settings_list():
    lb = style(Gtk.ListBox(), "md-list")
    lb.set_selection_mode(Gtk.SelectionMode.NONE)
    lb.set_activate_on_single_click(False)
    return lb


def row_in_list(lb, widget):
    """Add widget to a ListBox as a non-focusable, non-selectable row."""
    lb.add(widget)
    parent = widget.get_parent()
    if isinstance(parent, Gtk.ListBoxRow):
        parent.set_activatable(False)
        parent.set_selectable(False)
        parent.set_can_focus(False)


def icon_image(names, size=Gtk.IconSize.MENU):
    img = Gtk.Image.new_from_gicon(Gio.ThemedIcon.new_from_names(list(names) + ["image-missing"]), size)
    return style(img, "md-sidebar-icon")


def icon_button(icon, tip, cb):
    b = Gtk.Button.new_from_icon_name(icon, Gtk.IconSize.BUTTON)
    b.set_tooltip_text(tip)
    b.connect("clicked", cb)
    return b


def text_button(text, cb, suggested=False):
    b = Gtk.Button(label=text)
    b.connect("clicked", cb)
    if suggested:
        style(b, "suggested-action")
    return b


# --------------------------------------------------------------- dock preview

def _rounded(cr, x, y, w, h, r):
    r = max(0.0, min(r, w / 2.0, h / 2.0))
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
    cr.close_path()


APP_HUES = [(0.95, 0.45, 0.30), (0.30, 0.75, 0.45), (0.30, 0.55, 0.95), (0.95, 0.75, 0.25), (0.70, 0.40, 0.90)]


def draw_dock_preview(cr, w, h, get, compact=False):
    """Draw a miniature dock. `get(key)` returns a value for a setting key.

    compact=True draws a fixed bottom-centered thumbnail (theme cards);
    otherwise edge, alignment, icon size, spacing, padding and margin are honoured.
    """
    wall = cairo.LinearGradient(0, 0, w, h)
    wall.add_color_stop_rgb(0, 0.10, 0.18, 0.30)
    wall.add_color_stop_rgb(0.55, 0.30, 0.20, 0.48)
    wall.add_color_stop_rgb(1, 0.62, 0.30, 0.48)
    cr.set_source(wall)
    cr.paint()

    n = 5
    edge, align = ("bottom", "center") if compact else (get("position.edge"), get("position.alignment"))
    vertical = edge in ("left", "right")
    icon, gap, pad, margin = (get("size.icon_size"), get("size.spacing"), get("size.padding"),
                              get("size.margin")) if not compact else (52, 8, 10, 10)
    run = 2 * pad + n * icon + (n - 1) * gap          # length along the edge
    thick = icon + 2 * pad                              # depth away from the edge
    along, across = (h, w) if vertical else (w, h)
    k = min(1.0, along * 0.84 / run, across * 0.60 / thick)
    if compact:
        k = min(along * 0.78 / run, across * 0.42 / thick)
    run, thick, icon, gap, pad, margin = (v * k for v in (run, thick, icon, gap, pad, margin))
    margin = max(margin, 4)
    start = {"start": along * 0.06, "center": (along - run) / 2.0, "end": along - run - along * 0.06}[align]
    if vertical:
        dw, dh = thick, run
        dx = margin if edge == "left" else w - thick - margin
        dy = start
    else:
        dw, dh = run, thick
        dx = start
        dy = margin if edge == "top" else h - thick - margin
    radius = get("appearance.corner_radius") * k

    if get("appearance.shadow"):
        size = get("appearance.shadow_size") * k
        strength = get("appearance.shadow_opacity")
        for i in range(6):
            grow = size * (1 - i / 6.0)
            _rounded(cr, dx - grow / 2, dy - grow / 2 + size * 0.25, dw + grow, dh + grow, radius + grow / 2)
            cr.set_source_rgba(0, 0, 0, strength * 0.10)
            cr.fill()

    op = get("appearance.bg_opacity")
    _rounded(cr, dx, dy, dw, dh, radius)
    c1 = with_alpha(parse_color(get("appearance.bg_color")), op)
    if get("appearance.bg_gradient"):
        c2 = with_alpha(parse_color(get("appearance.bg_color2")), op)
        d = get("appearance.gradient_direction")
        g = cairo.LinearGradient(dx, dy, dx + (dw if d != "vertical" else 0), dy + (dh if d != "horizontal" else 0))
        g.add_color_stop_rgba(0, *c1)
        g.add_color_stop_rgba(1, *c2)
        cr.set_source(g)
    else:
        cr.set_source_rgba(*c1)
    cr.fill_preserve()
    bw = get("appearance.border_width")
    if bw > 0:
        cr.set_source_rgba(*with_alpha(parse_color(get("appearance.border_color")), get("appearance.border_opacity")))
        cr.set_line_width(max(0.5, bw * max(k, 0.6)))
        cr.stroke()
    else:
        cr.new_path()

    ind_style = "dot" if compact else get("indicators.style")
    ind_size = max(1.5, (4 if compact else get("indicators.size")) * max(k, 0.6) / 2.0)
    for i in range(n):
        off = pad + i * (icon + gap)
        ix, iy = (dx + pad, dy + off) if vertical else (dx + off, dy + pad)
        _rounded(cr, ix, iy, icon, icon, icon * 0.24)
        cr.set_source_rgb(*APP_HUES[i])
        cr.fill()
        running = i in (1, 2)
        if ind_style == "none" or not running:
            continue
        col = get("indicators.active_color") if i == 1 else get("indicators.color")
        cr.set_source_rgba(*parse_color(col))
        # indicator sits on the side of the icon that faces the screen edge
        gapspace = max(pad * 0.55, ind_size + 1)
        if vertical:
            cx = (dx + gapspace * 0.5) if edge == "left" else (dx + dw - gapspace * 0.5)
            cy = iy + icon / 2
            if ind_style == "line":
                cr.rectangle(cx - ind_size / 2, cy - icon * 0.2, ind_size, icon * 0.4)
            else:
                cr.arc(cx, cy, ind_size, 0, 2 * math.pi)
        else:
            cx = ix + icon / 2
            cy = (dy + dh - gapspace * 0.5) if edge != "top" else (dy + gapspace * 0.5)
            if ind_style == "line":
                cr.rectangle(cx - icon * 0.2, cy - ind_size / 2, icon * 0.4, ind_size)
            else:
                cr.arc(cx, cy, ind_size, 0, 2 * math.pi)
        cr.fill()


class LivePreview(Gtk.Box):
    """Pinned, always-current preview of the dock built from the working config."""

    def __init__(self, store):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.store = store
        self.set_margin_start(28)
        self.set_margin_end(28)
        self.set_margin_top(18)
        self.area = style(Gtk.DrawingArea(), "md-preview")
        self.area.set_size_request(-1, 150)
        self.area.connect("draw", self.on_draw)
        self.pack_start(self.area, False, False, 0)
        self.pack_start(label("Live preview · scaled to fit, approximate", "md-preview-caption"), False, False, 0)
        store.listen(self.area.queue_draw)

    def on_draw(self, area, cr):
        w, h = area.get_allocated_width(), area.get_allocated_height()
        cr.save()
        _rounded(cr, 0, 0, w, h, 14)
        cr.clip()
        try:
            draw_dock_preview(cr, w, h, self.store.get)
        except Exception as exc:  # a bad value must never take the window down
            print("preview: %s" % exc, file=sys.stderr)
        cr.restore()
        return False


# --------------------------------------------------------------- theme cards

# ---------------------------------------------------------- theme dialogs / page

def message(parent, text, secondary="", kind=Gtk.MessageType.INFO, buttons=Gtk.ButtonsType.OK, accept=None):
    dlg = Gtk.MessageDialog(transient_for=parent, modal=True, message_type=kind, buttons=buttons, text=text)
    if secondary:
        dlg.format_secondary_text(secondary)
    if accept:
        btn = dlg.add_button(accept, Gtk.ResponseType.OK)
        style(btn, "destructive-action")
    resp = dlg.run()
    dlg.destroy()
    return resp


def json_chooser(parent, title, save=False, name=""):
    dlg = Gtk.FileChooserNative(title=title, transient_for=parent,
                                action=Gtk.FileChooserAction.SAVE if save else Gtk.FileChooserAction.OPEN,
                                accept_label="Export" if save else "Open", cancel_label="Cancel")
    flt = Gtk.FileFilter()
    flt.set_name("JSON files")
    flt.add_pattern("*.json")
    dlg.add_filter(flt)
    if save:
        dlg.set_do_overwrite_confirmation(True)
        dlg.set_current_name(name)
    return dlg


class ThemeNameDialog(Gtk.Dialog):
    """Name (and optionally describe) a theme, with a live picture of what is being saved."""

    def __init__(self, parent, title, accept, name="", desc=None, store=None):
        super().__init__(title=title, transient_for=parent, modal=True)
        self.add_buttons("Cancel", Gtk.ResponseType.CANCEL, accept, Gtk.ResponseType.OK)
        self.set_default_response(Gtk.ResponseType.OK)
        box = self.get_content_area()
        box.set_spacing(10)
        for side in ("start", "end", "top", "bottom"):
            getattr(box, "set_margin_" + side)(16)
        if store is not None:
            area = style(Gtk.DrawingArea(), "md-preview")
            area.set_size_request(320, 110)

            def draw(w, cr):
                width, height = w.get_allocated_width(), w.get_allocated_height()
                cr.save()
                _rounded(cr, 0, 0, width, height, 14)
                cr.clip()
                draw_dock_preview(cr, width, height, store.get, compact=True)
                cr.restore()
                return False
            area.connect("draw", draw)
            box.pack_start(area, False, False, 0)
        self.name = Gtk.Entry()
        self.name.set_max_length(60)
        self.name.set_placeholder_text("Theme name, e.g. Midnight Blue")
        self.name.set_text(name)
        self.name.set_activates_default(True)
        box.pack_start(self.name, False, False, 0)
        self.desc = None
        if desc is not None:
            self.desc = Gtk.Entry()
            self.desc.set_max_length(200)
            self.desc.set_placeholder_text("Description (optional)")
            self.desc.set_text(desc)
            self.desc.set_activates_default(True)
            box.pack_start(self.desc, False, False, 0)
        self.ok = self.get_widget_for_response(Gtk.ResponseType.OK)
        style(self.ok, "suggested-action")
        self.name.connect("changed", self.check)
        self.check()
        self.show_all()
        self.name.grab_focus()

    def check(self, *_):
        self.ok.set_sensitive(bool(self.name.get_text().strip()))

    def values(self):
        return self.name.get_text().strip(), (self.desc.get_text().strip() if self.desc else "")


class ThemesPage(Gtk.Box):
    def __init__(self, store):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.store = store
        self.names = []
        self.cards = {}
        self.pack_start(heading("Themes", "Pick a look, save your own, or share one as a file."), False, False, 0)
        bar = style(Gtk.Box(spacing=6), "md-toolbar")
        bar.set_margin_bottom(14)
        bar.pack_start(text_button("Save current look…", lambda *_: self.save_current(), suggested=True), False, False, 0)
        bar.pack_start(text_button("Import theme…", lambda *_: self.import_file()), False, False, 0)
        bar.pack_start(text_button("Export current…", lambda *_: self.export_current()), False, False, 0)
        self.pack_start(bar, False, False, 0)
        self.flow = Gtk.FlowBox()
        self.flow.set_selection_mode(Gtk.SelectionMode.NONE)
        self.flow.set_max_children_per_line(3)
        self.flow.set_min_children_per_line(1)
        self.flow.set_homogeneous(True)
        self.flow.set_row_spacing(12)
        self.flow.set_column_spacing(12)
        self.pack_start(self.flow, False, False, 0)
        note = label("“Inspired” themes are visual homages, not copies. True background blur needs SwayFX "
                     "(Colors & Style → Background blur); on plain Sway the dock is translucent only. "
                     "Imported themes can only change appearance, never commands or launchers.",
                     "md-page-sub", wrap=True)
        note.set_margin_top(18)
        self.pack_start(note, False, False, 0)
        self.rebuild()
        store.listen(self.refresh)

    # --- cards
    def rebuild(self):
        for child in self.flow.get_children():
            child.destroy()
        self.cards = {}
        self.names = list(self.store.all_themes()) + [CUSTOM]
        for name in self.names:
            self.flow.add(self.make_card(name))
        self.flow.show_all()
        self.update_active()

    def make_card(self, name):
        info = self.store.all_themes().get(name)
        btn = style(Gtk.Button(), "md-theme-card")
        btn.set_relief(Gtk.ReliefStyle.NONE)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        area = Gtk.DrawingArea()
        area.set_size_request(180, 96)
        if info is None:  # the live "Custom" card follows the working config
            def getter(k):
                return self.store.get(k)
            desc = "Your current edits. Save them to keep this look."
        else:
            vals = info["values"]

            def getter(k, v=vals):
                return v[k] if k in v else C.default_value(k)
            desc = info.get("description") or ("Your saved theme." if info.get("user") else "")

        def draw(w, cr, g=getter):
            width, height = w.get_allocated_width(), w.get_allocated_height()
            cr.save()
            _rounded(cr, 0, 0, width, height, 10)
            cr.clip()
            draw_dock_preview(cr, width, height, g, compact=True)
            cr.restore()
            return False
        area.connect("draw", draw)
        box.pack_start(area, False, False, 0)
        head = Gtk.Box(spacing=8)
        head.pack_start(label(self.store.theme_label(name), "md-theme-name"), True, True, 0)
        pill = style(Gtk.Label(label="ACTIVE"), "md-active-pill")
        pill.set_no_show_all(True)
        head.pack_end(pill, False, False, 0)
        box.pack_start(head, False, False, 0)
        d = label(desc, "md-theme-desc", wrap=True)
        d.set_max_width_chars(28)
        box.pack_start(d, False, False, 0)
        btn.add(box)
        if info is None:
            btn.set_tooltip_text("Edit any color or style setting to use a custom look")
        else:
            btn.connect("clicked", lambda *_: self.store.apply_theme(name))
        overlay = Gtk.Overlay()
        overlay.add(btn)
        menu = self.card_menu(name, info)
        menu.set_halign(Gtk.Align.END)
        menu.set_valign(Gtk.Align.START)
        menu.set_margin_top(14)
        menu.set_margin_end(14)
        overlay.add_overlay(menu)
        self.cards[name] = (btn, area, pill)
        return overlay

    def card_menu(self, name, info):
        entries = []
        if info is None:
            entries.append(("Save as theme…", self.save_current))
        entries.append(("Export…", lambda: self.export(name)))
        if info is not None and info.get("user"):
            entries += [("Rename…", lambda: self.rename(name)), ("Delete…", lambda: self.delete(name))]
        mb = Gtk.MenuButton()
        mb.set_relief(Gtk.ReliefStyle.NONE)
        mb.add(Gtk.Image.new_from_icon_name("view-more-symbolic", Gtk.IconSize.BUTTON))
        mb.set_tooltip_text("Theme options")
        pop = Gtk.Popover()
        pbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        for side in ("start", "end", "top", "bottom"):
            getattr(pbox, "set_margin_" + side)(6)
        for text, cb in entries:
            item = Gtk.ModelButton(text=text)
            item.connect("clicked", lambda _b, f=cb: (pop.popdown(), GLib.idle_add(lambda: (f(), False)[1])))
            pbox.pack_start(item, False, False, 0)
        pbox.show_all()
        pop.add(pbox)
        mb.set_popover(pop)
        return mb

    def refresh(self):
        if list(self.store.all_themes()) + [CUSTOM] != self.names:
            self.rebuild()
        else:
            self.update_active()

    def update_active(self):
        cur = self.store.cfg.get("theme")
        for name, (btn, area, pill) in self.cards.items():
            ctx = btn.get_style_context()
            if name == cur:
                ctx.add_class("active")
                pill.show()
            else:
                ctx.remove_class("active")
                pill.hide()
            if name == CUSTOM:
                area.queue_draw()

    # --- actions
    def win(self):
        top = self.get_toplevel()
        return top if isinstance(top, Gtk.Window) else None

    def fail(self, exc):
        message(self.win(), "That didn't work", str(exc), Gtk.MessageType.ERROR)

    def save_current(self):
        dlg = ThemeNameDialog(self.win(), "Save current look as a theme", "Save", desc="", store=self.store)
        try:
            if dlg.run() == Gtk.ResponseType.OK:
                name, desc = dlg.values()
                try:
                    self.store.save_current_theme(name, desc)
                except (UT.ThemeError, OSError, ValueError) as exc:
                    self.fail(exc)
        finally:
            dlg.destroy()

    def rename(self, name):
        dlg = ThemeNameDialog(self.win(), "Rename theme", "Rename", name=self.store.theme_label(name))
        try:
            if dlg.run() == Gtk.ResponseType.OK:
                try:
                    self.store.rename_theme(name, dlg.values()[0])
                except (UT.ThemeError, OSError, ValueError) as exc:
                    self.fail(exc)
        finally:
            dlg.destroy()

    def delete(self, name):
        resp = message(self.win(), "Delete “%s”?" % self.store.theme_label(name),
                       "Your dock keeps its current look. Only the saved theme is removed.",
                       Gtk.MessageType.QUESTION, Gtk.ButtonsType.CANCEL, accept="Delete")
        if resp == Gtk.ResponseType.OK:
            try:
                self.store.delete_theme(name)
            except (UT.ThemeError, OSError, ValueError) as exc:
                self.fail(exc)

    def export_current(self):
        cur = self.store.cfg.get("theme", CUSTOM)
        self.export(cur if cur in self.store.all_themes() else CUSTOM)

    def export(self, name):
        base = UT.slugify(self.store.theme_label(name) if name != CUSTOM else "my-theme")
        dlg = json_chooser(self.win(), "Export theme", save=True, name=base + ".json")
        try:
            if dlg.run() != Gtk.ResponseType.ACCEPT:
                return
            try:
                path = dlg.get_filename()
                self.store.export_theme(name, path)
            except (UT.ThemeError, OSError, ValueError) as exc:
                self.fail(exc)
                return
            cb = getattr(self.store, "on_saved", None)
            if cb:
                cb("Exported theme to %s" % os.path.basename(path), True)
        finally:
            dlg.destroy()

    def import_file(self):
        dlg = json_chooser(self.win(), "Import theme")
        try:
            if dlg.run() != Gtk.ResponseType.ACCEPT:
                return
            try:
                name, info = self.store.import_theme(dlg.get_filename())
            except (UT.ThemeError, OSError, ValueError) as exc:
                self.fail(exc)
                return
        finally:
            dlg.destroy()
        ignored = info.get("ignored", [])
        extra = ""
        if ignored:
            extra = "\n\n%d setting(s) in the file aren't appearance options and were skipped." % len(ignored)
        resp = message(self.win(), "Imported “%s”" % info.get("label", name), "Apply it to your dock now?" + extra,
                       Gtk.MessageType.QUESTION, Gtk.ButtonsType.YES_NO)
        if resp == Gtk.ResponseType.YES:
            try:
                self.store.apply_theme(name)
            except (UT.ThemeError, OSError, ValueError) as exc:
                self.fail(exc)


# ------------------------------------------------------------------ launchers

def gicon_for(icon, entry=None):
    names = candidate_names(icon, entry)
    theme = Gtk.IconTheme.get_default()
    for n in names:
        if os.path.isabs(n):
            if os.path.exists(n):
                return Gio.FileIcon.new(Gio.File.new_for_path(n))
        elif theme.has_icon(n):
            return Gio.ThemedIcon.new(n)
    for n in names:
        p = find_icon_file(n)
        if p:
            return Gio.FileIcon.new(Gio.File.new_for_path(p))
    return Gio.ThemedIcon.new_with_default_fallbacks(icon or "application-x-executable")


class AppPicker(Gtk.Dialog):
    def __init__(self, parent, entries):
        super().__init__(title="Add application", transient_for=parent, modal=True)
        self.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Add", Gtk.ResponseType.OK)
        self.set_default_response(Gtk.ResponseType.OK)
        self.set_default_size(460, 540)
        box = self.get_content_area()
        self.search = Gtk.SearchEntry()
        self.search.set_placeholder_text("Search applications")
        self.search.set_margin_start(12)
        self.search.set_margin_end(12)
        self.search.set_margin_top(12)
        box.pack_start(self.search, False, False, 0)
        self.listbox = Gtk.ListBox()
        self.listbox.set_filter_func(self._filter)
        names = [e for e in entries.values() if is_launchable(e, ())]
        for e in sorted(names, key=lambda e: e.name.lower()):
            row = Gtk.ListBoxRow()
            row.entry_id = e.id
            row.text = ("%s %s %s" % (e.name, e.generic_name, e.id)).lower()
            hb = Gtk.Box(spacing=12)
            hb.set_margin_start(12)
            hb.set_margin_end(12)
            hb.set_margin_top(6)
            hb.set_margin_bottom(6)
            img = Gtk.Image.new_from_gicon(gicon_for(e.icon, e), Gtk.IconSize.DND)
            img.set_pixel_size(32)
            hb.pack_start(img, False, False, 0)
            hb.pack_start(label(e.name), True, True, 0)
            row.add(hb)
            self.listbox.add(row)
        self.listbox.connect("row-activated", lambda *_: self.response(Gtk.ResponseType.OK))
        sw = scrolled(self.listbox)
        sw.set_margin_start(12)
        sw.set_margin_end(12)
        sw.set_margin_top(10)
        sw.set_margin_bottom(12)
        sw.set_shadow_type(Gtk.ShadowType.IN)
        box.pack_start(sw, True, True, 0)
        self.search.connect("search-changed", lambda *_: self.listbox.invalidate_filter())
        self.show_all()
        self.search.grab_focus()

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
        self.set_default_response(Gtk.ResponseType.OK)
        grid = Gtk.Grid(column_spacing=12, row_spacing=10)
        for side in ("start", "end", "top"):
            getattr(grid, "set_margin_" + side)(18)
        grid.set_margin_bottom(10)
        self.name = Gtk.Entry()
        self.exec = Gtk.Entry()
        self.icon = Gtk.Entry()
        self.match = Gtk.Entry()
        for e in (self.name, self.exec, self.icon, self.match):
            e.set_activates_default(True)
        self.name.set_hexpand(True)
        self.name.set_placeholder_text("e.g. Notes")
        self.exec.set_placeholder_text("command to run, e.g. foot -e htop")
        self.icon.set_placeholder_text("icon name or image path")
        self.match.set_placeholder_text("optional: window app_id / class to show as running")
        rows = [("Name", self.name), ("Command", self.exec), ("Icon", self.icon), ("Match", self.match)]
        for i, (text, widget) in enumerate(rows):
            grid.attach(label(text, "md-key", xalign=1.0), 0, i, 1, 1)
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
        style(self.ok, "suggested-action")
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


class ItemDialog(Gtk.Dialog):
    """Rename a pinned app and/or give it a different icon (the .desktop file is untouched)."""

    def __init__(self, parent, spec, entry):
        super().__init__(title="Customize %s" % entry.name, transient_for=parent, modal=True)
        self.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Save", Gtk.ResponseType.OK)
        self.set_default_response(Gtk.ResponseType.OK)
        self.spec_id, self.entry = spec["id"], entry
        grid = Gtk.Grid(column_spacing=12, row_spacing=10)
        for side in ("start", "end", "top"):
            getattr(grid, "set_margin_" + side)(18)
        grid.set_margin_bottom(10)
        self.preview = Gtk.Image()
        self.preview.set_margin_bottom(6)
        grid.attach(self.preview, 0, 0, 3, 1)
        self.name = Gtk.Entry()
        self.icon = Gtk.Entry()
        for e in (self.name, self.icon):
            e.set_activates_default(True)
        self.name.set_hexpand(True)
        self.name.set_placeholder_text(entry.name)
        self.icon.set_placeholder_text(entry.icon or "icon name or image path")
        grid.attach(label("Name", "md-key", xalign=1.0), 0, 1, 1, 1)
        grid.attach(self.name, 1, 1, 1, 1)
        grid.attach(label("Icon", "md-key", xalign=1.0), 0, 2, 1, 1)
        grid.attach(self.icon, 1, 2, 1, 1)
        browse = Gtk.Button(label="Browse…")
        browse.connect("clicked", self.browse)
        grid.attach(browse, 2, 2, 1, 1)
        grid.attach(label("Leave a field empty to keep the app's own name or icon.", "md-row-help", wrap=True),
                    1, 3, 2, 1)
        reset = Gtk.Button(label="Use app defaults")
        reset.connect("clicked", lambda *_: (self.name.set_text(""), self.icon.set_text("")))
        reset.set_halign(Gtk.Align.START)
        grid.attach(reset, 1, 4, 2, 1)
        self.get_content_area().add(grid)
        self.name.set_text(spec.get("name", ""))
        self.icon.set_text(spec.get("icon", ""))
        style(self.get_widget_for_response(Gtk.ResponseType.OK), "suggested-action")
        self.icon.connect("changed", self.update_preview)
        self.update_preview()
        self.show_all()
        self.name.grab_focus()

    def update_preview(self, *_):
        icon = self.icon.get_text().strip() or self.entry.icon
        self.preview.set_from_gicon(gicon_for(icon, self.entry), Gtk.IconSize.DIALOG)
        self.preview.set_pixel_size(64)

    def browse(self, *_):
        dlg = Gtk.FileChooserNative(title="Choose icon", transient_for=self, action=Gtk.FileChooserAction.OPEN)
        if dlg.run() == Gtk.ResponseType.ACCEPT:
            self.icon.set_text(dlg.get_filename())

    def spec(self):
        s = {"type": "app", "id": self.spec_id}
        if self.name.get_text().strip():
            s["name"] = self.name.get_text().strip()
        if self.icon.get_text().strip():
            s["icon"] = self.icon.get_text().strip()
        return s


class LaunchersPage(Gtk.Box):
    def __init__(self, store, window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.store, self.window = store, window
        self.loading = False
        self.pack_start(heading("Launchers", "Drag rows to reorder. Double-click an app or launcher to rename it or change its icon. "
                                "Running apps that are not pinned appear after a divider."), False, False, 0)

        self.model = Gtk.ListStore(Gio.Icon, str, str)  # gicon, label, json
        self.tree = Gtk.TreeView(model=self.model)
        self.tree.set_headers_visible(False)
        self.tree.set_reorderable(True)
        self.tree.set_enable_search(False)
        self.tree.set_activate_on_single_click(False)
        pix = Gtk.CellRendererPixbuf()
        pix.set_property("stock-size", Gtk.IconSize.LARGE_TOOLBAR)
        pix.set_property("xpad", 12)
        pix.set_property("ypad", 7)
        col = Gtk.TreeViewColumn("Item")
        col.pack_start(pix, False)
        col.add_attribute(pix, "gicon", 0)
        txt = Gtk.CellRendererText()
        txt.set_property("xpad", 8)
        col.pack_start(txt, True)
        col.add_attribute(txt, "text", 1)
        self.tree.append_column(col)
        self.tree.connect("row-activated", self.edit_row)
        self.tree.get_selection().connect("changed", self.update_buttons)
        self.model.connect("row-deleted", lambda *_: GLib.idle_add(self.sync_from_model))
        sw = scrolled(self.tree)
        sw.set_size_request(-1, 320)
        self.empty = label("No items yet. Add an application to get started.", "md-empty", xalign=0.5)
        self.empty.set_no_show_all(True)
        inner = Gtk.Overlay()
        inner.add(sw)
        inner.add_overlay(self.empty)
        self.empty.set_halign(Gtk.Align.CENTER)
        self.empty.set_valign(Gtk.Align.CENTER)
        inner.set_overlay_pass_through(self.empty, True)
        self.pack_start(card(inner), True, True, 0)

        bar = style(Gtk.Box(spacing=6), "md-toolbar")
        bar.set_margin_top(12)
        bar.pack_start(text_button("Add application…", self.add_app, suggested=True), False, False, 0)
        more = Gtk.MenuButton(label="Add other")
        pop = Gtk.Popover()
        pbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        pbox.set_margin_start(6)
        pbox.set_margin_end(6)
        pbox.set_margin_top(6)
        pbox.set_margin_bottom(6)
        for text, cb in [("Custom launcher…", self.add_custom),
                         ("Separator", lambda *_: self.append({"type": "separator"})),
                         ("Applications button", lambda *_: self.append({"type": "special", "kind": "apps"})),
                         ("Trash", lambda *_: self.append({"type": "special", "kind": "trash"})),
                         ("Clock widget", lambda *_: self.add_widget("clock")),
                         ("Calendar widget", lambda *_: self.add_widget("calendar")),
                         ("Music controls", lambda *_: self.add_widget("music")),
                         ("Folder…", self.add_folder),
                         ("Plugin widget…", self.add_plugin)]:
            item = Gtk.ModelButton(text=text)
            item.connect("clicked", lambda _b, f=cb: (pop.popdown(), f()))
            pbox.pack_start(item, False, False, 0)
        pbox.show_all()
        pop.add(pbox)
        more.set_popover(pop)
        bar.pack_start(more, False, False, 0)
        self.edit_btn = icon_button("document-edit-symbolic", "Rename / change icon…", lambda *_: self.edit_selected())
        bar.pack_start(self.edit_btn, False, False, 0)
        self.up_btn = icon_button("go-up-symbolic", "Move up", lambda *_: self.move(-1))
        self.down_btn = icon_button("go-down-symbolic", "Move down", lambda *_: self.move(1))
        self.rm_btn = icon_button("user-trash-symbolic", "Remove from dock", self.remove)
        for b in (self.up_btn, self.down_btn, self.rm_btn):
            bar.pack_start(b, False, False, 0)
        bar.pack_end(text_button("Reset to defaults", self.reset), False, False, 0)
        self.pack_start(bar, False, False, 0)

        store.listen_external(self.load)
        self.load()
        self.update_buttons()

    # model <-> config
    def describe(self, spec):
        t = spec["type"]
        if t == "separator":
            return gicon_for("list-remove-symbolic"), "──  Separator  ──"
        if t == "special":
            info = C.SPECIAL_KINDS[spec["kind"]]
            return gicon_for(info["icon"]), info["name"] + "  ·  built-in"
        if t == "launcher":
            return gicon_for(spec.get("icon")), spec["name"] + "  ·  custom launcher"
        if t == "widget":
            names = {"clock": "Clock", "calendar": "Calendar", "music": "Music controls"}
            icons = {"clock": "clock", "calendar": "x-office-calendar", "music": "audio-x-generic"}
            kind = spec.get("kind", "")
            return gicon_for(icons.get(kind, "application-x-executable")), names.get(kind, kind) + "  ·  widget"
        if t == "folder":
            name = spec.get("name") or os.path.basename(spec.get("path", "")) or "Folder"
            return gicon_for(spec.get("icon") or "folder"), name + "  ·  folder"
        if t == "plugin":
            return gicon_for(spec.get("icon") or "application-x-addon-symbolic"), spec.get("name", "Plugin") + "  ·  plugin"
        entry = self.store.entries.get(spec["id"])
        if entry is None:
            return gicon_for("dialog-question-symbolic"), "%s  (not installed)" % spec["id"]
        name, icon = spec.get("name") or entry.name, spec.get("icon") or entry.icon
        tag = "  ·  customized" if (spec.get("name") or spec.get("icon")) else ""
        return gicon_for(icon, entry), name + tag

    def load(self):
        self.loading = True
        self.model.clear()
        for spec in self.store.cfg["items"]:
            icon, text = self.describe(spec)
            self.model.append([icon, text, json.dumps(spec)])
        self.loading = False
        self.empty.set_visible(len(self.model) == 0)
        self.update_buttons()

    def update_buttons(self, *_):
        i = self.selected_index()
        n = len(self.model)
        self.up_btn.set_sensitive(i is not None and i > 0)
        self.down_btn.set_sensitive(i is not None and i < n - 1)
        self.rm_btn.set_sensitive(i is not None)
        kind = self.current_items()[i]["type"] if i is not None and i < n else None
        self.edit_btn.set_sensitive(kind in ("app", "launcher"))

    def sync_from_model(self):
        if self.loading:
            return False
        items = [json.loads(row[2]) for row in self.model]
        if items != self.store.cfg["items"]:
            self.store.set_items(items)
        return False

    def commit(self, items, select=None):
        self.store.set_items(items)
        self.load()
        if select is not None and 0 <= select < len(self.model):
            self.tree.get_selection().select_path(Gtk.TreePath(select))

    def current_items(self):
        return [json.loads(r[2]) for r in self.model]

    def selected_index(self):
        sel = self.tree.get_selection().get_selected_rows()[1]
        return sel[0].get_indices()[0] if sel else None

    def append(self, spec):
        items = self.current_items() + [spec]
        self.commit(items, select=len(items) - 1)

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

    def add_widget(self, kind):
        if kind not in ("clock", "calendar", "music"):
            return
        if any(spec.get("type") == "widget" and spec.get("kind") == kind for spec in self.current_items()):
            message(self.window, "That widget is already in the dock.")
            return
        self.append({"type": "widget", "kind": kind})

    def add_folder(self, *_):
        chooser = Gtk.FileChooserNative(title="Choose a folder for GlassDock", transient_for=self.window,
                                        action=Gtk.FileChooserAction.SELECT_FOLDER,
                                        accept_label="Add folder", cancel_label="Cancel")
        try:
            if chooser.run() != Gtk.ResponseType.ACCEPT:
                return
            path = chooser.get_filename()
        finally:
            chooser.destroy()
        if not path:
            return
        path = os.path.abspath(os.path.expanduser(path))
        if not os.path.isdir(path):
            message(self.window, "Folder not found", path, Gtk.MessageType.ERROR)
            return
        if any(spec.get("type") == "folder" and os.path.abspath(os.path.expanduser(spec.get("path", ""))) == path
               for spec in self.current_items()):
            message(self.window, "That folder is already in the dock.")
            return
        self.append({"type": "folder", "path": path,
                     "name": os.path.basename(path.rstrip(os.sep)) or path, "icon": "folder"})

    def add_plugin(self, *_):
        """Explicitly trust and add a Python plugin found in the configured plugin directory."""
        plugin_directory = self.store.get("extensions.plugin_directory").strip()
        if not plugin_directory:
            plugin_directory = os.path.join(C.config_dir(), "plugins")
        plugin_directory = os.path.abspath(os.path.expanduser(plugin_directory))
        os.makedirs(plugin_directory, exist_ok=True)
        names = sorted(os.path.splitext(name)[0] for name in os.listdir(plugin_directory)
                       if name.endswith(".py") and not name.startswith("_")
                       and os.path.isfile(os.path.join(plugin_directory, name))
                       and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", name[:-3]))
        if not names:
            message(self.window, "No plugin modules found",
                    "Place a reviewed .py plugin in %s, then try again. Plugins run as your user and are not sandboxed."
                    % plugin_directory, Gtk.MessageType.INFO)
            return
        dialog = Gtk.Dialog(title="Add trusted plugin", transient_for=self.window, modal=True)
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Allow and add", Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        box.set_spacing(10)
        for side in ("start", "end", "top", "bottom"):
            getattr(box, "set_margin_" + side)(16)
        box.pack_start(heading("Choose a plugin", "Choose code you have reviewed."), False, False, 0)
        combo = Gtk.ComboBoxText()
        for name in names:
            combo.append_text(name)
        combo.set_active(0)
        box.pack_start(combo, False, False, 0)
        warning = label("Trust warning: plugin code executes with your account permissions; it is not a security sandbox.",
                        "md-page-sub", wrap=True)
        box.pack_start(warning, False, False, 0)
        dialog.show_all()
        response = dialog.run()
        name = combo.get_active_text()
        dialog.destroy()
        if response != Gtk.ResponseType.OK or not name:
            return
        if any(spec.get("type") == "plugin" and spec.get("name") == name for spec in self.current_items()):
            message(self.window, "That plugin is already in the dock.")
            return

        # The newer Cairo plugin API is optional and coexists with the original
        # JSON-rendered plugin format. Execute only the module the user just
        # approved; discovery never imports every disabled module in a folder.
        from . import extras_store as ExtrasStore, plugin_api as ExtraPluginAPI
        extra_classes, _extra_errors = ExtraPluginAPI.discover([plugin_directory], allowlist=[name])
        if name in extra_classes:
            data = ExtrasStore.load()
            conf = data["plugins"].setdefault(name, {"enabled": False, "config": {}})
            conf["enabled"] = True
            existing_config = conf.get("config", {}) if isinstance(conf.get("config"), dict) else {}
            defaults = {key: spec.get("default") for key, spec in extra_classes[name].CONFIG.items()}
            defaults.update({key: value for key, value in existing_config.items() if key in defaults})
            conf["config"] = defaults
            ExtrasStore.save(data)
            self.append({"type": "plugin", "name": name})
            self.extensions_panel.refresh()
            return

        existing = [part.strip() for part in self.store.get("extensions.plugin_allowlist").split(",") if part.strip()]
        if name not in existing:
            existing.append(name)
        self.store.set("extensions.plugin_allowlist", ", ".join(existing))
        self.store.set("extensions.plugins_enabled", True)
        self.append({"type": "plugin", "name": name})

    def edit_row(self, tree, path, col):
        self.edit_at(path.get_indices()[0])

    def edit_selected(self, *_):
        i = self.selected_index()
        if i is not None:
            self.edit_at(i)

    def edit_at(self, idx):
        """Open the right editor for item `idx` (custom launcher or pinned app)."""
        items = self.current_items()
        if not 0 <= idx < len(items):
            return
        spec = items[idx]
        if spec["type"] == "launcher":
            dlg = LauncherDialog(self.window, spec)
        elif spec["type"] == "app" and self.store.entries.get(spec["id"]) is not None:
            dlg = ItemDialog(self.window, spec, self.store.entries[spec["id"]])
        else:
            return
        if dlg.run() == Gtk.ResponseType.OK:
            items[idx] = dlg.spec()
            self.commit(items, select=idx)
        dlg.destroy()

    def move(self, delta):
        i = self.selected_index()
        items = self.current_items()
        if i is None or not 0 <= i + delta < len(items):
            return
        items[i], items[i + delta] = items[i + delta], items[i]
        self.commit(items, select=i + delta)

    def remove(self, *_):
        i = self.selected_index()
        if i is None:
            return
        items = self.current_items()
        del items[i]
        self.commit(items, select=min(i, len(items) - 1))

    def reset(self, *_):
        self.store.reset_items()
        self.load()


# ------------------------------------------------------------------- monitors

class OverrideRow(Gtk.Box):
    def __init__(self, setting, store, output):
        super().__init__(spacing=14)
        self.setting, self.store, self.output = setting, store, output
        for side in ("start", "end"):
            getattr(self, "set_margin_" + side)(16)
        self.set_margin_top(10)
        self.set_margin_bottom(10)
        self.check = Gtk.CheckButton(label=setting.label)
        self.pack_start(self.check, True, True, 0)
        ov = store.monitor(output)
        has = setting.key in ov
        value = ov.get(setting.key, store.get(setting.key))
        self.control, self.setv = make_control(setting, value, self.on_value)
        self.control.set_valign(Gtk.Align.CENTER)
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
        self.combo = Gtk.ComboBoxText.new_with_entry()
        self.combo.set_size_request(180, -1)
        top.pack_start(label("Monitor", "md-key"), False, False, 0)
        top.pack_start(self.combo, False, False, 0)
        top.pack_start(text_button("Detect monitors", lambda *_: self.detect()), False, False, 0)
        self.pack_start(top, False, False, 0)
        self.msg = label("", "md-page-sub")
        self.msg.set_margin_top(8)
        self.pack_start(self.msg, False, False, 0)
        self.body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.pack_start(self.body, False, False, 0)
        self.combo.connect("changed", lambda *_: self.rebuild())
        self.detect()

    def detect(self):
        names = []
        err = ""
        ipc = None
        try:
            ipc = sway.SwayIPC()
            names = [o["name"] for o in sway.parse_outputs(ipc.get_outputs())]
        except (sway.SwayError, OSError) as exc:
            err = "Could not query Sway (%s). Type an output name (e.g. eDP-1) to configure it." % exc
        finally:
            if ipc is not None:
                ipc.close()
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
        self.body.pack_start(group_title("Dock on %s" % name), False, False, 0)
        lb = settings_list()
        enable = Gtk.Box(spacing=14)
        enable.set_margin_start(16)
        enable.set_margin_end(16)
        enable.set_margin_top(10)
        enable.set_margin_bottom(10)
        enable.pack_start(label("Show a dock on this monitor", "md-row-title"), True, True, 0)
        sw = Gtk.Switch()
        sw.set_active(C.monitor_enabled(self.store.cfg, name))
        sw.set_valign(Gtk.Align.CENTER)
        sw.connect("notify::active", lambda s, *_: self.store.set_monitor(name, "enabled", s.get_active()))
        enable.pack_start(sw, False, False, 0)
        row_in_list(lb, enable)
        self.body.pack_start(card(lb), False, False, 0)

        self.body.pack_start(group_title("Overrides for this monitor"), False, False, 0)
        olb = settings_list()
        for key in C.MONITOR_OVERRIDE_KEYS:
            row_in_list(olb, OverrideRow(C.SETTINGS[key], self.store, name))
        self.body.pack_start(card(olb), False, False, 0)
        hint = label("Tick a setting to give this monitor its own value; untick to follow the global one.",
                     "md-row-help", wrap=True)
        hint.set_margin_top(8)
        hint.set_margin_start(4)
        self.body.pack_start(hint, False, False, 0)
        forget = text_button("Remove all overrides for this monitor",
                             lambda *_: (self.store.forget_monitor(name), self.rebuild()))
        forget.set_halign(Gtk.Align.START)
        forget.set_margin_top(12)
        self.body.pack_start(forget, False, False, 0)
        self.body.show_all()


# --------------------------------------------------------------------- status

class StatusPage(Gtk.Box):
    REFRESH_MS = 3000

    def __init__(self, store):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.store = store
        self.pending = False
        self.timer = None
        self.pack_start(heading("Status", "Live information from the running dock."), False, False, 0)

        self.badge = style(Gtk.Label(label="Checking…"), "md-badge")
        self.badge.set_halign(Gtk.Align.START)
        top = Gtk.Box(spacing=10)
        top.set_margin_start(16)
        top.set_margin_top(14)
        top.set_margin_bottom(6)
        top.pack_start(label("Dock", "md-row-title"), False, False, 0)
        top.pack_start(self.badge, False, False, 0)

        self.grid = Gtk.Grid(column_spacing=24, row_spacing=8)
        self.grid.set_margin_start(16)
        self.grid.set_margin_end(16)
        self.grid.set_margin_bottom(16)
        self.values = {}
        fields = [("version", "Dock version"), ("app", "Settings app"), ("config", "Config file"),
                  ("sway", "Sway IPC"), ("outputs", "Monitors with a dock"), ("windows", "Open windows seen"),
                  ("items", "Dock items"), ("blur", "Blur"), ("theme", "Theme"), ("autostart", "Autostart")]
        for i, (key, text) in enumerate(fields):
            self.grid.attach(label(text, "md-key"), 0, i, 1, 1)
            v = label("–", "md-mono", selectable=True, wrap=True)
            v.set_hexpand(True)
            self.grid.attach(v, 1, i, 1, 1)
            self.values[key] = v
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        inner.pack_start(top, False, False, 0)
        inner.pack_start(self.grid, False, False, 0)
        self.pack_start(card(inner), False, False, 0)

        bar = style(Gtk.Box(spacing=6), "md-toolbar")
        bar.set_margin_top(12)
        for text, cb in [("Refresh", lambda *_: self.refresh()), ("Start dock", self.start),
                         ("Restart dock", self.restart), ("Stop dock", self.stop),
                         ("Open config folder", self.open_folder)]:
            bar.pack_start(text_button(text, cb), False, False, 0)
        self.pack_start(bar, False, False, 0)
        note = label("Blur is only reported as active if SwayFX accepted the layer_effects command; "
                     "otherwise the dock is translucent without blur.", "md-page-sub", wrap=True)
        note.set_margin_top(16)
        self.pack_start(note, False, False, 0)
        self.connect("map", self.on_map)
        self.connect("unmap", self.on_unmap)
        self.refresh()

    def on_map(self, *_):
        self.refresh()
        if self.timer is None:
            self.timer = GLib.timeout_add(self.REFRESH_MS, self._tick)

    def on_unmap(self, *_):
        if self.timer is not None:
            GLib.source_remove(self.timer)
            self.timer = None

    def _tick(self):
        self.refresh()
        return True

    def set_badge(self, text, kind):
        ctx = self.badge.get_style_context()
        for k in ("ok", "off", "bad"):
            ctx.remove_class(k)
        ctx.add_class(kind)
        self.badge.set_text(text)

    def refresh(self):
        if self.pending:
            return
        self.pending = True

        def work():
            try:
                reply = control.send_command({"cmd": "status"})
            except Exception as exc:
                print("[glassdock-settings] status request failed: %s" % exc, file=sys.stderr)
                reply = None
            GLib.idle_add(self.apply, reply)
        threading.Thread(target=work, daemon=True).start()

    def apply(self, r):
        self.pending = False
        v = self.values
        v["app"].set_text("v%s" % __version__)
        v["config"].set_text(C.config_path())
        if not isinstance(r, dict) or not r.get("ok", False):
            self.set_badge("Not running", "off")
            for k in ("version", "sway", "outputs", "windows", "items", "blur", "theme", "autostart"):
                v[k].set_text("–")
            return False
        self.set_badge("Running", "ok")
        v["version"].set_text("v%s" % r.get("version", "?"))
        v["sway"].set_text("connected" if r.get("sway_ipc") else "not connected (no running indicators)")
        outputs = r.get("outputs", [])
        if not isinstance(outputs, (list, tuple)):
            outputs = []
        v["outputs"].set_text(", ".join(str(output) for output in outputs) or "none")
        v["windows"].set_text(str(r.get("windows", "–")))
        v["items"].set_text(str(r.get("items", "–")))
        v["blur"].set_text(str(r.get("blur", "–")))
        v["theme"].set_text(str(r.get("theme", "–")))
        v["autostart"].set_text("%s (%s)" % ("on" if r.get("autostart") else "off", r.get("autostart_wms", "unknown")))
        return False

    def _spawn_dock(self):
        # Go through the launcher script so the layer-shell preload is applied.
        try:
            subprocess.Popen([os.path.join(ROOT, "bin", "glassdock")], cwd=ROOT,
                             start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as exc:
            self.set_badge("Start failed", "bad")
            self.values["version"].set_text("Could not start dock: %s" % exc)
            return
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
        try:
            subprocess.Popen(["xdg-open", C.config_dir()], start_new_session=True)
        except OSError as exc:
            if self.store.on_saved:
                self.store.on_saved("Could not open config folder: %s" % exc, False)


# --------------------------------------------------------------------- window

class SettingsWindow(Gtk.Window):
    def __init__(self, edit_index=None):
        super().__init__(title="GlassDock Settings")
        self.set_default_size(1040, 740)
        install_css()
        self.store = Store()
        self.store.on_saved = self.on_saved
        self.store.listen(self.refresh_rows)
        self.rows = []
        self.search_rows = []
        self.advanced_rows = []
        self.status_timer = None

        self.set_titlebar(self.build_header())

        root = Gtk.Box()
        self.add(root)

        side = style(Gtk.Box(orientation=Gtk.Orientation.VERTICAL), "md-sidebar")
        side.set_size_request(208, -1)
        self.search = style(Gtk.SearchEntry(), "md-search")
        self.search.set_placeholder_text("Search settings  (Ctrl+F)")
        self.search.connect("search-changed", self.on_search)
        side.pack_start(self.search, False, False, 0)
        self.sidebar = Gtk.ListBox()
        self.sidebar.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.sidebar.connect("row-selected", self.on_select)
        side.pack_start(scrolled(self.sidebar), True, True, 0)
        root.pack_start(side, False, False, 0)

        content = style(Gtk.Box(orientation=Gtk.Orientation.VERTICAL), "md-content")
        root.pack_start(content, True, True, 0)
        self.preview = LivePreview(self.store)
        self.revealer = Gtk.Revealer()
        self.revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        self.revealer.set_transition_duration(160)
        self.revealer.add(self.preview)
        content.pack_start(self.revealer, False, False, 0)
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(120)
        content.pack_start(self.stack, True, True, 0)

        self.add_section("Appearance")
        self.add_page("themes", "Themes", ThemesPage(self.store))
        for cat, text in C.CATEGORIES:
            if cat in ("style", "size", "animation", "indicators"):
                self.add_page(cat, text, self.category_page(cat, text))
        self.add_section("Dock")
        for cat, text in C.CATEGORIES:
            if cat in ("position", "behavior"):
                self.add_page(cat, text, self.category_page(cat, text))
        self.launchers = LaunchersPage(self.store, self)
        self.add_page("launchers", "Launchers", self.launchers)
        self.add_page("monitors", "Monitors", MonitorsPage(self.store))
        self.add_section("Extensions")
        from .extension_settings import ExtensionsPanel
        self.extensions_panel = ExtensionsPanel(self.store, self.rows)
        self.add_page("extensions", "Extensions", self.extensions_panel)
        self.add_section("System")
        self.add_page("status", "Status", StatusPage(self.store))
        self.search_box = page_box()
        self.stack.add_named(scrolled(self.search_box), "search")

        self.connect("key-press-event", self.on_key)
        self.connect("delete-event", self.on_close)
        self.show_all()
        if edit_index is not None:  # opened from the dock's right-click menu
            self.select_page("launchers")
            GLib.idle_add(lambda: (self.launchers.edit_at(edit_index), False)[1])
        else:
            self.select_page("themes")

    def open_config_folder(self, *_):
        try:
            subprocess.Popen(["xdg-open", C.config_dir()], start_new_session=True)
        except OSError as exc:
            self.on_saved("Could not open config folder: %s" % exc, False)

    def build_header(self):
        hb = Gtk.HeaderBar()
        hb.set_show_close_button(True)
        hb.set_title("GlassDock Settings")
        hb.set_subtitle("v%s" % __version__)
        self.status = style(Gtk.Label(label=""), "md-pill")
        self.status.set_no_show_all(True)
        hb.pack_start(self.status)

        menu = Gtk.MenuButton()
        menu.add(Gtk.Image.new_from_icon_name("open-menu-symbolic", Gtk.IconSize.BUTTON))
        pop = Gtk.Popover()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        for side in ("start", "end", "top", "bottom"):
            getattr(box, "set_margin_" + side)(6)
        for text, cb in [("Export all settings…", self.export_settings),
                         ("Import settings…", self.import_settings),
                         ("Reset all settings…", self.reset_all),
                         ("Open config folder", self.open_config_folder),
                         ("About GlassDock", self.show_about)]:
            item = Gtk.ModelButton(text=text)
            item.connect("clicked", lambda _b, f=cb: (pop.popdown(), f()))
            box.pack_start(item, False, False, 0)
        box.show_all()
        pop.add(box)
        menu.set_popover(pop)
        hb.pack_end(menu)
        return hb

    # sidebar
    def add_section(self, text):
        row = Gtk.ListBoxRow()
        row.page = None
        row.set_selectable(False)
        row.set_activatable(False)
        style(row, "md-section")
        lbl = label(text.upper(), "md-section-label")
        lbl.set_margin_start(12)
        lbl.set_margin_top(4)
        lbl.set_margin_bottom(2)
        row.add(lbl)
        self.sidebar.add(row)

    def add_page(self, name, text, widget):
        if not isinstance(widget, Gtk.ScrolledWindow):
            widget = scrolled(self.padded(widget))
        self.stack.add_named(widget, name)
        row = Gtk.ListBoxRow()
        row.page = name
        box = Gtk.Box(spacing=10)
        box.set_margin_start(10)
        box.set_margin_end(10)
        box.set_margin_top(7)
        box.set_margin_bottom(7)
        box.pack_start(icon_image(PAGE_ICONS.get(name, ("preferences-system-symbolic",))), False, False, 0)
        box.pack_start(label(text), True, True, 0)
        row.add(box)
        self.sidebar.add(row)

    @staticmethod
    def padded(widget):
        if isinstance(widget, (ThemesPage, LaunchersPage, MonitorsPage, StatusPage)):
            wrap = page_box()
            wrap.pack_start(widget, True, True, 0)
            return wrap
        return widget

    def select_page(self, name):
        for row in self.sidebar.get_children():
            if getattr(row, "page", None) == name:
                self.sidebar.select_row(row)
                return

    def category_page(self, cat, text):
        box = page_box()
        box.pack_start(heading(text, CATEGORY_BLURBS.get(cat)), False, False, 0)
        advanced_keys = set(ADVANCED_SETTING_KEYS.get(cat, ()))
        entries = [s for s in C.SCHEMA
                   if s.category == cat and not s.key.startswith("extensions.")
                   and s.key not in advanced_keys]
        advanced_entries = [s for s in C.SCHEMA
                            if s.category == cat and s.key in advanced_keys]
        if entries:
            lb = settings_list()
            for setting in entries:
                row = SettingRow(setting, self.store)
                self.rows.append(row)
                row_in_list(lb, row)
            box.pack_start(card(lb), False, False, 0)
        if advanced_entries:
            actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            actions.pack_start(label(
                "%d additional controls for fine-tuning this section." % len(advanced_entries),
                "md-row-help", wrap=True), True, True, 0)
            actions.pack_end(text_button(
                "Advanced options…",
                lambda *_: self.show_advanced_settings(text, advanced_entries),
            ), False, False, 0)
            box.pack_start(card(actions), False, False, 0)
        return box

    def show_advanced_settings(self, page_title, entries):
        dialog = Gtk.Dialog(
            title="Advanced %s settings" % page_title.lower(),
            transient_for=self, modal=True)
        dialog.set_default_size(760, 620)
        dialog.set_position(Gtk.WindowPosition.CENTER_ON_PARENT)
        dialog.add_button("Done", Gtk.ResponseType.CLOSE)
        area = dialog.get_content_area()
        area.set_spacing(12)
        for side in ("start", "end", "top", "bottom"):
            getattr(area, "set_margin_" + side)(18)
        area.pack_start(label(
            "These controls are kept separate to make the main settings pages easier to scan.",
            "md-page-sub", wrap=True), False, False, 0)
        lb = settings_list()
        rows = []
        for setting in entries:
            row = SettingRow(setting, self.store)
            rows.append(row)
            self.advanced_rows.append(row)
            row_in_list(lb, row)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.add(card(lb))
        area.pack_start(scroll, True, True, 0)
        try:
            dialog.show_all()
            dialog.run()
        finally:
            for row in rows:
                if row in self.advanced_rows:
                    self.advanced_rows.remove(row)
            dialog.destroy()

    def on_select(self, lb, row):
        if row is None or getattr(row, "page", None) is None:
            return
        if self.search.get_text().strip():
            self.search.set_text("")
        self.stack.set_visible_child_name(row.page)
        self.revealer.set_reveal_child(row.page in PREVIEW_PAGES)

    def on_search(self, entry):
        q = entry.get_text().strip().lower()
        for r in self.search_rows:
            r.destroy()
        self.search_rows = []
        for c in self.search_box.get_children():
            c.destroy()
        if not q:
            row = self.sidebar.get_selected_row()
            if row is not None and getattr(row, "page", None):
                self.stack.set_visible_child_name(row.page)
                self.revealer.set_reveal_child(row.page in PREVIEW_PAGES)
            return
        cats = dict(C.CATEGORIES)
        self.search_box.pack_start(heading("Search results", "Matching “%s”" % q), False, False, 0)
        lb = settings_list()
        found = 0
        for s in C.SCHEMA:
            hay = " ".join([s.label, s.key, s.help, s.keywords, cats[s.category]]).lower()
            if all(tok in hay for tok in q.split()):
                row = SettingRow(s, self.store)
                self.search_rows.append(row)
                row_in_list(lb, row)
                found += 1
        if found:
            self.search_box.pack_start(card(lb), False, False, 0)
        else:
            self.search_box.pack_start(label("No matching settings.", "md-empty", xalign=0.5), False, False, 20)
        self.search_box.show_all()
        self.revealer.set_reveal_child(False)
        self.stack.set_visible_child_name("search")

    def on_key(self, _w, ev):
        ctrl = ev.state & Gdk.ModifierType.CONTROL_MASK
        if ctrl and ev.keyval in (Gdk.KEY_f, Gdk.KEY_F):
            self.search.grab_focus()
            return True
        if ev.keyval == Gdk.KEY_Escape and self.search.get_text():
            self.search.set_text("")
            return True
        return False

    def refresh_rows(self):
        for r in self.rows + self.search_rows + self.advanced_rows:
            r.refresh()

    def on_saved(self, msg, ok):
        self.status.set_text(msg)
        ctx = self.status.get_style_context()
        ctx.remove_class("ok")
        ctx.remove_class("bad")
        ctx.add_class("ok" if ok else "bad")
        self.status.show()
        if self.status_timer is not None:
            GLib.source_remove(self.status_timer)
        self.status_timer = GLib.timeout_add_seconds(4, self._clear_status)
        return False

    def _clear_status(self):
        self.status_timer = None
        self.status.hide()
        return False

    def export_settings(self, *_):
        dlg = json_chooser(self, "Export all settings", save=True, name="glassdock-settings.json")
        try:
            if dlg.run() != Gtk.ResponseType.ACCEPT:
                return
            path = dlg.get_filename()
            try:
                self.store.export_settings(path)
            except OSError as exc:
                message(self, "Couldn't export", exc.strerror or str(exc), Gtk.MessageType.ERROR)
            else:
                self.on_saved("Exported settings to %s" % os.path.basename(path), True)
        finally:
            dlg.destroy()

    def import_settings(self, *_):
        dlg = json_chooser(self, "Import settings")
        try:
            if dlg.run() != Gtk.ResponseType.ACCEPT:
                return
            path = dlg.get_filename()
        finally:
            dlg.destroy()
        resp = message(self, "Replace your appearance and behavior settings?",
                       "Your launchers and monitor setup are kept. Only import files you trust: "
                       "settings can include commands, such as the Applications button command.",
                       Gtk.MessageType.QUESTION, Gtk.ButtonsType.CANCEL, accept="Import")
        if resp != Gtk.ResponseType.OK:
            return
        try:
            self.store.import_settings(path)
        except ValueError as exc:
            message(self, "Couldn't import", str(exc), Gtk.MessageType.ERROR)

    def reset_all(self, *_):
        dlg = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.QUESTION,
                                buttons=Gtk.ButtonsType.CANCEL,
                                text="Reset all appearance and behavior settings?")
        dlg.format_secondary_text("Your launchers and per-monitor settings are kept.")
        dlg.add_button("Reset", Gtk.ResponseType.OK)
        style(dlg.get_widget_for_response(Gtk.ResponseType.OK), "destructive-action")
        if dlg.run() == Gtk.ResponseType.OK:
            self.store.reset_all_settings()
        dlg.destroy()

    def show_about(self, *_):
        dlg = Gtk.AboutDialog(transient_for=self, modal=True)
        dlg.set_program_name("GlassDock")
        dlg.set_version(__version__)
        dlg.set_comments("A floating, macOS-inspired dock for Wayland / Sway / SwayFX.")
        dlg.set_license_type(Gtk.License.MIT_X11)
        icon = os.path.join(ROOT, "assets", "glassdock.svg")
        if os.path.exists(icon):
            try:
                from gi.repository import GdkPixbuf
                dlg.set_logo(GdkPixbuf.Pixbuf.new_from_file_at_size(icon, 96, 96))
            except Exception:
                pass
        dlg.run()
        dlg.destroy()

    def on_close(self, *_):
        try:
            self.store.flush()
        except OSError as exc:
            self.on_saved("Could not save pending changes: %s" % exc, False)
            # Keep the window open so the user can correct a permissions/disk error.
            return True
        return False


def _set_app_icon():
    """Window/default icon from the bundled artwork (the dock itself uses the desktop entry)."""
    for fname in ("glassdock.svg", "moderndock.svg"):
        p = os.path.join(ROOT, "assets", fname)
        if os.path.exists(p):
            try:
                Gtk.Window.set_default_icon_from_file(p)
            except GLib.Error:
                pass
            return


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    edit_index = None
    if "--edit" in argv:
        try:
            edit_index = int(argv[argv.index("--edit") + 1])
        except (ValueError, IndexError):
            print("usage: settings [--edit ITEM_INDEX]", file=sys.stderr)
            return 2
    if Gdk.Display.get_default() is None:
        print("No display available.", file=sys.stderr)
        return 1
    _set_app_icon()
    SettingsWindow(edit_index).connect("destroy", Gtk.main_quit)
    Gtk.main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
