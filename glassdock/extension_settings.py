# Integrated GlassDock extension module.
"""Advanced extension settings embedded in the normal Launchers page.

    python3 -m glassdock.extension_settings

Contains tabbed controls for advanced widgets, fan folders, built-in icon overrides and explicitly enabled Python plugins.
"""
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from . import extras_store as X  # noqa: E402
from . import plugin_api as P  # noqa: E402
from . import settings as S  # noqa: E402
from .widgets import LABELS, WIDGET_TYPES  # noqa: E402


def _rgba_to_hex(c):
    return "#%02x%02x%02x" % (round(c.red * 255), round(c.green * 255), round(c.blue * 255))


class Form(Gtk.Box):
    """Schema-driven controls bound to a dict; calls on_change(key, value) after every edit."""

    def __init__(self, schema, values, on_change):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        for key, spec in schema.items():
            row = Gtk.Box(spacing=10)
            lab = S.label(spec.get("label", key), "md-row-title", wrap=True)
            lab.set_hexpand(True)
            row.pack_start(lab, True, True, 0)
            row.pack_end(self.control(key, spec, values.get(key, spec["default"]), on_change), False, False, 0)
            self.pack_start(row, False, False, 0)

    @staticmethod
    def control(key, spec, val, cb):
        t = spec["type"]
        if t == "bool":
            w = Gtk.Switch(active=bool(val), valign=Gtk.Align.CENTER)
            w.connect("notify::active", lambda s, _p: cb(key, s.get_active()))
        elif t in ("int", "float"):
            lo, hi = spec.get("min", 0), spec.get("max", 1000)
            w = Gtk.SpinButton.new_with_range(lo, hi, spec.get("step", 1 if t == "int" else 0.1))
            w.set_digits(0 if t == "int" else 2)
            w.set_value(val)
            w.connect("value-changed", lambda s: cb(key, int(s.get_value()) if t == "int" else s.get_value()))
        elif t == "choice":
            w = Gtk.ComboBoxText()
            for c in spec["choices"]:
                w.append_text(c)
            w.set_active(spec["choices"].index(val) if val in spec["choices"] else 0)
            w.connect("changed", lambda s: cb(key, s.get_active_text()))
        elif t == "color":
            rgba = Gdk.RGBA()
            rgba.parse(val or "#ffffff")
            w = Gtk.ColorButton.new_with_rgba(rgba)
            w.connect("color-set", lambda s: cb(key, _rgba_to_hex(s.get_rgba())))
        elif t == "path":
            w = Gtk.Box(spacing=4)
            e = Gtk.Entry(text=val or "", width_chars=26)
            e.connect("changed", lambda s: cb(key, s.get_text()))
            b = Gtk.Button(label="Browse…")

            def browse(_b):
                dlg = Gtk.FileChooserNative(title="Choose", action=Gtk.FileChooserAction.SELECT_FOLDER
                                            if key == "path" else Gtk.FileChooserAction.OPEN)
                if dlg.run() == Gtk.ResponseType.ACCEPT:
                    e.set_text(dlg.get_filename())
            b.connect("clicked", browse)
            w.pack_start(e, True, True, 0); w.pack_start(b, False, False, 0)
        else:
            w = Gtk.Entry(text=str(val if val is not None else ""), width_chars=20)
            w.connect("changed", lambda s: cb(key, s.get_text()))
        return w


class BasePage(Gtk.ScrolledWindow):
    def __init__(self, title, sub, data=None):
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for side in ("start", "end", "top", "bottom"):
            getattr(self.box, "set_margin_" + side)(18)
        self.box.pack_start(S.label(title, "md-page-title"), False, False, 0)
        self.box.pack_start(S.label(sub, "md-page-sub", wrap=True), False, False, 0)
        self.body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.box.pack_start(self.body, False, False, 0)
        self.add(self.box)
        self.data = X.load() if data is None else data

    def save(self):
        X.save(self.data)

    def rebuild(self):
        for c in self.body.get_children():
            self.body.remove(c)
        self.fill()
        self.body.show_all()

    def card(self, title, widget):
        outer = S.style(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8), "md-card")
        for side in ("start", "end", "top", "bottom"):
            getattr(outer, "set_margin_" + side)(0)
            getattr(widget, "set_margin_" + side)(12)
        if title:
            outer.pack_start(S.label(title, "md-group-title"), False, False, 0)
            outer.get_children()[0].set_margin_start(12); outer.get_children()[0].set_margin_top(10)
        outer.pack_start(widget, False, False, 0)
        return outer


class WidgetsPage(BasePage):
    def __init__(self, data=None):
        super().__init__("Widgets", "Native clocks, calendar and music.", data=data)
        self.fill()

    def fill(self):
        add = Gtk.Box(spacing=8)
        combo = Gtk.ComboBoxText()
        types = [t for t in WIDGET_TYPES]
        for t in types:
            combo.append_text(LABELS[t])
        combo.set_active(0)
        btn = Gtk.Button(label="Add to dock")

        def do_add(_b):
            t = types[combo.get_active()]
            self.data["extras"].append({"id": X.new_id(self.data, t + "-"), "type": t, "at": None})
            self.save(); self.rebuild()
        btn.connect("clicked", do_add)
        add.pack_start(combo, False, False, 0); add.pack_start(btn, False, False, 0)
        self.body.pack_start(add, False, False, 0)
        for e in [e for e in self.data["extras"] if e.get("type") in WIDGET_TYPES]:
            wid, t = e["id"], e["type"]
            vals = X.widget_cfg(self.data, wid, t)

            def changed(k, v, wid=wid):
                self.data["widgets"].setdefault(wid, {})[k] = v
                self.save()
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            inner.pack_start(Form(X.WIDGET_SCHEMA[t], vals, changed), False, False, 0)
            pos = Gtk.Box(spacing=8)
            pos.pack_start(S.label("Position (index, empty = before Trash)", "md-row-help"), False, False, 0)
            en = Gtk.Entry(text="" if e.get("at") is None else str(e["at"]), width_chars=5)

            def set_at(ent, e=e):
                e["at"] = int(ent.get_text()) if ent.get_text().strip().isdigit() else None
                self.save()
            en.connect("changed", set_at)
            rm = Gtk.Button(label="Remove")

            def remove(_b, wid=wid):
                self.data["extras"] = [x for x in self.data["extras"] if x["id"] != wid]
                self.save(); self.rebuild()
            rm.connect("clicked", remove)
            pos.pack_end(rm, False, False, 0); pos.pack_end(en, False, False, 0)
            inner.pack_start(pos, False, False, 0)
            self.body.pack_start(self.card("%s  ·  %s" % (LABELS[t], wid), inner), False, False, 0)


class FoldersPage(BasePage):
    def __init__(self, data=None):
        super().__init__("Folders", "Fan-out folders. Drag a directory or .desktop file onto the dock or a folder to add it.", data=data)
        self.fill()

    def fill(self):
        b = Gtk.Button(label="New folder")

        def new(_b):
            fid = X.new_id(self.data, "folder")
            self.data["extras"].append({"id": fid, "type": "folder", "at": None})
            self.data["folders"][fid] = X.folder_cfg(self.data, fid)
            self.save(); self.rebuild()
        b.connect("clicked", new)
        b.set_halign(Gtk.Align.START)
        self.body.pack_start(b, False, False, 0)
        for e in [e for e in self.data["extras"] if e.get("type") == "folder"]:
            fid = e["id"]
            fc = self.data["folders"].setdefault(fid, X.folder_cfg(self.data, fid))
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

            def changed(k, v, fc=fc):
                fc[k] = v
                self.save()
            inner.pack_start(Form(X.FOLDER_SCHEMA, fc, changed), False, False, 0)
            apps = Gtk.Entry(text=", ".join(fc.get("apps", [])), hexpand=True)
            apps.connect("changed", lambda ent, fc=fc: (fc.__setitem__("apps", [a.strip() for a in ent.get_text().split(",") if a.strip()]), self.save()))
            files = Gtk.Entry(text=", ".join(fc.get("files", [])), hexpand=True)
            files.connect("changed", lambda ent, fc=fc: (fc.__setitem__("files", [a.strip() for a in ent.get_text().split(",") if a.strip()]), self.save()))
            ci = Gtk.Entry(text=", ".join("%s=%s" % kv for kv in fc.get("child_icons", {}).items()), hexpand=True)

            def child_icons(ent, fc=fc):
                d = {}
                for part in ent.get_text().split(","):
                    if "=" in part:
                        k, v = part.split("=", 1)
                        d[k.strip()] = v.strip()
                fc["child_icons"] = d
                self.save()
            ci.connect("changed", child_icons)
            for lab, w in (("App ids (comma separated, e.g. firefox, org.gnome.Nautilus)", apps),
                           ("Extra files/dirs (comma separated paths)", files),
                           ("Per-child icons: key=/path/icon.png  (key = app id or file name)", ci)):
                inner.pack_start(S.label(lab, "md-row-help"), False, False, 0)
                inner.pack_start(w, False, False, 0)
            rm = Gtk.Button(label="Remove folder")
            rm.set_halign(Gtk.Align.END)

            def remove(_b, fid=fid):
                self.data["extras"] = [x for x in self.data["extras"] if x["id"] != fid]
                self.data["folders"].pop(fid, None)
                self.save(); self.rebuild()
            rm.connect("clicked", remove)
            inner.pack_start(rm, False, False, 0)
            self.body.pack_start(self.card("%s  ·  %s" % (fc.get("name", fid), fid), inner), False, False, 0)


class IconsPage(BasePage):
    def __init__(self, data=None):
        super().__init__("Native Icons", "Replace the Apps and Trash glyphs with your own PNG/SVG icons. The full-trash image appears automatically.", data=data)
        self.fill()

    def fill(self):
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for key, text in X.ICON_KEYS.items():
            row = Gtk.Box(spacing=8)
            row.pack_start(S.label(text, "md-row-title"), True, True, 0)
            e = Gtk.Entry(text=self.data["icon_overrides"].get(key, ""), width_chars=30, placeholder_text="(built-in)")

            def changed(ent, key=key):
                v = ent.get_text().strip()
                if v:
                    self.data["icon_overrides"][key] = v
                else:
                    self.data["icon_overrides"].pop(key, None)
                self.save()
            e.connect("changed", changed)
            br = Gtk.Button(label="Browse…")
            br.connect("clicked", lambda _b, e=e: self._browse(e))
            clr = Gtk.Button(label="Reset")
            clr.connect("clicked", lambda _b, e=e: e.set_text(""))
            for w in (e, br, clr):
                row.pack_start(w, False, False, 0)
            inner.pack_start(row, False, False, 0)
        self.body.pack_start(self.card("Overrides", inner), False, False, 0)

    @staticmethod
    def _browse(entry):
        dlg = Gtk.FileChooserNative(title="Choose icon", action=Gtk.FileChooserAction.OPEN)
        if dlg.run() == Gtk.ResponseType.ACCEPT:
            entry.set_text(dlg.get_filename())


PLUGIN_AI_PROMPT = """You are helping me create a GlassDock Python plugin for my own desktop theme.

PLUGIN NAME: [short_module_name_without_spaces]
DISPLAY NAME: [name shown in the dock]
VISUAL STYLE / THEME: [colors, shape, typography, glow, glass, animation]
WHAT IT SHOULD SHOW: [clock, system stats, usage, weather, custom status, etc.]
DATA IT NEEDS: [only the values needed; use GlassDock stats where possible]
CLICK BEHAVIOUR: [what left/middle click should do]
CONFIGURATION OPTIONS: [colors, units, refresh interval, labels, etc.]
PERMISSIONS NEEDED: [none, network, or run_commands; justify each permission]
SIZE / LAYOUT: [compact dock tile details]

Write one complete, runnable .py plugin module using the public API in
`glassdock.plugin_api`: define exactly one PluginBase subclass, set NAME,
TICK, PERMISSIONS, TRANSPARENT and CONFIG as appropriate, and implement
on_load(), on_tick(), render(cr, w, h), on_click(button), and tooltip().
Use only `self.ctx.stats`, `self.ctx.colors`, `self.ctx.cfg()`, and documented
PluginContext methods. Draw with the supplied Cairo context; do not import GTK,
change GlassDock files, access the network, or run commands unless I explicitly
requested and justified the matching permission. Validate missing data and
handle errors gracefully. Keep refresh work cheap; cache slow work between ticks.
Return the full source code, filename, install instructions, and a short explanation
of any permissions. Do not claim this is sandboxed: approved plugins run as my user.
"""


class PluginsPage(BasePage):
    def __init__(self, data=None):
        super().__init__("Plugins", "Create, configure and manage dock plugins. Only modules you explicitly enable are loaded; enabled plugin code runs with your account permissions.", data=data)
        self.fill()

    def show_ai_prompt(self, *_):
        dialog = Gtk.Dialog(title="AI plugin prompt template", transient_for=self.get_toplevel(), modal=True)
        dialog.set_default_size(760, 620)
        dialog.add_button("Close", Gtk.ResponseType.CLOSE)
        dialog.add_button("Copy prompt", Gtk.ResponseType.APPLY)
        area = dialog.get_content_area()
        area.set_spacing(10)
        area.set_margin_top(12); area.set_margin_bottom(12)
        area.set_margin_start(12); area.set_margin_end(12)
        area.pack_start(S.label("Fill in the bracketed fields, copy this prompt, and paste it into your AI assistant. Review generated code before enabling it.", "md-page-sub", wrap=True), False, False, 0)
        view = Gtk.TextView()
        view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        view.get_buffer().set_text(PLUGIN_AI_PROMPT)
        view.set_monospace(True)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.add(view)
        area.pack_start(scroll, True, True, 0)
        dialog.show_all()
        response = dialog.run()
        if response == Gtk.ResponseType.APPLY:
            clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
            clipboard.set_text(view.get_buffer().get_text(view.get_buffer().get_start_iter(), view.get_buffer().get_end_iter(), True), -1)
            clipboard.store()
            S.message(self.get_toplevel(), "Copied", "AI plugin prompt copied to the clipboard.")
        dialog.destroy()

    def fill(self):
        actions = Gtk.Box(spacing=8)
        prompt = Gtk.Button(label="Copy AI plugin prompt…")
        prompt.connect("clicked", self.show_ai_prompt)
        actions.pack_start(prompt, False, False, 0)
        self.body.pack_start(self.card("Create your own plugin", actions), False, False, 0)
        from .dock_extensions import plugin_search_dirs
        enabled = [name for name, conf in self.data["plugins"].items()
                   if isinstance(conf, dict) and conf.get("enabled") is True]
        classes, errors = P.discover(plugin_search_dirs(S.C.load_config()), allowlist=enabled)
        if not self.data["plugins"]:
            self.body.pack_start(S.label("No advanced plugins added yet. Use Launchers → Add other → Plugin widget… and explicitly approve a module.", "md-empty", wrap=True), False, False, 0)
        for name, conf in sorted(self.data["plugins"].items()):
            cls = classes.get(name)
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            head = Gtk.Box(spacing=8)
            head.pack_start(S.label("Enabled", "md-row-title"), True, True, 0)
            switch = Gtk.Switch(active=bool(conf.get("enabled")))
            switch.connect("notify::active", self.on_toggle, name)
            head.pack_end(switch, False, False, 0)
            inner.pack_start(head, False, False, 0)
            if cls is not None:
                if cls.PERMISSIONS:
                    inner.pack_start(S.label("Permissions: " + ", ".join(cls.PERMISSIONS), "md-row-help"), False, False, 0)
                if cls.CONFIG:
                    current = conf.get("config", {}) if isinstance(conf.get("config"), dict) else {}
                    values = {key: spec.get("default") for key, spec in cls.CONFIG.items()}
                    values.update({key: value for key, value in current.items() if key in values})
                    inner.pack_start(Form(cls.CONFIG, values, lambda k, v, conf=conf: (conf.setdefault("config", {}).__setitem__(k, v), self.save())), False, False, 0)
                title = "%s  ·  %s" % (cls.NAME, name)
            elif name in errors:
                inner.pack_start(S.label(errors[name], "md-mono", wrap=True, selectable=True), False, False, 0)
                title = "Plugin error  ·  %s" % name
            else:
                title = "Disabled plugin  ·  %s" % name
            self.body.pack_start(self.card(title, inner), False, False, 0)

    def on_toggle(self, switch, _prop, name):
        conf = self.data["plugins"].setdefault(name, {"enabled": False, "config": {}})
        conf["enabled"] = switch.get_active()
        self.save()
        GLib.idle_add(self.rebuild)


PREFERENCE_GROUPS = (
    ("Clock & Calendar", "Time format, seconds and the calendar's first day of the week.",
     ("extensions.clock_format", "extensions.clock_show_seconds", "extensions.calendar_first_weekday"),
     "x-office-calendar-symbolic"),
    ("Music Controls", "Choose the MPRIS command, metadata refresh rate and hover behaviour.",
     ("extensions.music_playerctl", "extensions.music_refresh_seconds", "extensions.music_controls_on_hover"),
     "audio-x-generic-symbolic"),
    ("Folder Menus", "Control hidden files, menu limits and the fan layout.",
     ("extensions.folder_show_hidden", "extensions.folder_popup_limit", "extensions.folder_fan_radius", "extensions.folder_fan_angle"),
     "folder-symbolic"),
    ("Item Badges", "Choose whether badges appear and how large their labels may be.",
     ("extensions.badges_enabled", "extensions.badge_max_count"),
     "emblem-important-symbolic"),
    ("Plugin Loading", "Set the plugin directory, allowed module names and trusted-code loading policy.",
     ("extensions.plugins_enabled", "extensions.plugin_directory", "extensions.plugin_allowlist"),
     "application-x-python-symbolic"),
)


class ExtensionSettingsDialog:
    """A focused, modal editor for one group of extension defaults."""

    @staticmethod
    def open(parent, store, shared_rows, title, description, keys):
        dialog = Gtk.Dialog(title=title, transient_for=parent, modal=True)
        dialog.set_default_size(680, 560)
        dialog.set_position(Gtk.WindowPosition.CENTER_ON_PARENT)
        dialog.add_button("Done", Gtk.ResponseType.CLOSE)

        area = dialog.get_content_area()
        area.set_spacing(12)
        for side in ("start", "end", "top", "bottom"):
            getattr(area, "set_margin_" + side)(18)
        area.pack_start(S.label(title, "md-page-title"), False, False, 0)
        area.pack_start(S.label(description, "md-page-sub", wrap=True), False, False, 0)

        entries = [setting for setting in S.C.SCHEMA if setting.key in keys]
        controls = S.settings_list()
        rows = []
        for setting in entries:
            row = S.SettingRow(setting, store)
            rows.append(row)
            if shared_rows is not None:
                shared_rows.append(row)
            S.row_in_list(controls, row)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_min_content_height(300)
        scroll.add(S.card(controls))
        area.pack_start(scroll, True, True, 0)

        try:
            dialog.show_all()
            dialog.run()
        finally:
            if shared_rows is not None:
                for row in rows:
                    if row in shared_rows:
                        shared_rows.remove(row)
            dialog.destroy()


class ExtensionsPanel(Gtk.Box):
    """A polished extension hub with dedicated managers and focused preference dialogs."""

    def __init__(self, settings_store=None, settings_rows=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        for side in ("start", "end", "top", "bottom"):
            getattr(self, "set_margin_" + side)(22)
        self.settings_store = settings_store
        self.settings_rows = settings_rows
        self.data = X.load()
        self._summary_labels = {}

        self.pack_start(S.label("Extensions", "md-page-title"), False, False, 0)
        self.pack_start(S.label(
            "A dedicated workspace for dock widgets, folders, icons and Python plugins. "
            "Tune each feature in its own focused settings popup.",
            "md-page-sub", wrap=True), False, False, 0)

        trust = S.style(Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10), "md-card")
        trust.set_margin_top(2)
        trust_inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        for side in ("start", "end", "top", "bottom"):
            getattr(trust_inner, "set_margin_" + side)(12)
        trust_inner.pack_start(S.icon_image(("dialog-information-symbolic", "dialog-information"), Gtk.IconSize.BUTTON),
                               False, False, 0)
        trust_inner.pack_start(S.label(
            "Security note: enabled Python plugins run as your user; they are not sandboxed. "
            "Only enable code you trust.", "md-page-sub", wrap=True), True, True, 0)
        trust.pack_start(trust_inner, True, True, 0)
        self.pack_start(trust, False, False, 0)

        self._add_section("MANAGE")
        management = [
            ("widgets", "view-grid-symbolic", "Dock widgets",
             "Add and tune native clocks, calendars and music controls.",
             "Manage widgets…", lambda: self._open_manager(WidgetsPage, "Manage dock widgets")),
            ("folders", "folder-symbolic", "Fan folders",
             "Organize apps, paths and per-item icons into radial folders.",
             "Manage folders…", lambda: self._open_manager(FoldersPage, "Manage fan folders")),
            ("icons", "applications-graphics-symbolic", "Native icons",
             "Override the built-in Apps and Trash artwork with your own images.",
             "Manage icons…", lambda: self._open_manager(IconsPage, "Manage native icons")),
            ("plugins", "application-x-python-symbolic", "Python plugins",
             "Review enabled modules, permissions and per-plugin configuration.",
             "Manage plugins…", lambda: self._open_manager(PluginsPage, "Manage Python plugins")),
        ]
        grid = Gtk.Grid()
        grid.set_column_spacing(14)
        grid.set_row_spacing(14)
        grid.set_column_homogeneous(True)
        grid.set_hexpand(True)
        for index, (key, glyph, title, description, action, callback) in enumerate(management):
            card, summary = self._make_card(glyph, title, description, action, callback, "0 configured")
            self._summary_labels[key] = summary
            grid.attach(card, index % 2, index // 2, 1, 1)
        self.pack_start(grid, False, False, 0)

        if self.settings_store is not None:
            self._add_section("FEATURE PREFERENCES")
            preference_grid = Gtk.Grid()
            preference_grid.set_column_spacing(14)
            preference_grid.set_row_spacing(14)
            preference_grid.set_column_homogeneous(True)
            for index, (title, description, keys, glyph) in enumerate(PREFERENCE_GROUPS):
                callback = lambda title=title, description=description, keys=keys: self._open_preferences(
                    title, description, keys)
                card, _summary = self._make_card(
                    glyph, title, description, "Configure…", callback, None, height=140)
                preference_grid.attach(card, index % 2, index // 2, 1, 1)
            self.pack_start(preference_grid, False, False, 0)

        self._refresh_summaries()

    def _add_section(self, title):
        heading = S.label(title, "md-group-title")
        heading.set_margin_top(6)
        self.pack_start(heading, False, False, 0)

    @staticmethod
    def _make_card(glyph, title, description, action_text, callback, summary_text=None, height=166):
        outer = S.style(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10), "md-card")
        outer.set_hexpand(True)
        outer.set_size_request(-1, height)
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for side in ("start", "end", "top", "bottom"):
            getattr(inner, "set_margin_" + side)(14)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        header.set_valign(Gtk.Align.CENTER)
        header.pack_start(S.icon_image((glyph, "applications-utilities-symbolic"), Gtk.IconSize.DIALOG),
                          False, False, 0)
        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        title_box.pack_start(S.label(title, "md-row-title", wrap=True), False, False, 0)
        title_box.pack_start(S.label(description, "md-row-help", wrap=True), False, False, 0)
        header.pack_start(title_box, True, True, 0)
        inner.pack_start(header, True, True, 0)

        summary = None
        if summary_text is not None:
            summary = S.style(Gtk.Label(label=summary_text, xalign=0), "md-pill")
            summary.set_halign(Gtk.Align.START)
            inner.pack_start(summary, False, False, 0)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        actions.set_halign(Gtk.Align.END)
        button = S.text_button(action_text, lambda *_: callback(), suggested=True)
        actions.pack_end(button, False, False, 0)
        inner.pack_start(actions, False, False, 0)
        outer.pack_start(inner, True, True, 0)
        return outer, summary

    def _open_manager(self, page_class, title):
        parent = self.get_toplevel()
        dialog = Gtk.Dialog(title=title, transient_for=parent, modal=True)
        dialog.set_default_size(900, 700)
        dialog.set_position(Gtk.WindowPosition.CENTER_ON_PARENT)
        dialog.add_button("Done", Gtk.ResponseType.CLOSE)
        area = dialog.get_content_area()
        area.set_spacing(8)
        for side in ("start", "end", "top", "bottom"):
            getattr(area, "set_margin_" + side)(8)
        page = page_class(self.data)
        page.set_size_request(-1, 590)
        area.pack_start(page, True, True, 0)
        try:
            dialog.show_all()
            dialog.run()
        finally:
            dialog.destroy()
        self.data = X.load()
        self._refresh_summaries()

    def _open_preferences(self, title, description, keys):
        if self.settings_store is None:
            return
        ExtensionSettingsDialog.open(
            self.get_toplevel(), self.settings_store, self.settings_rows,
            title, description, keys)

    def _summary_text(self):
        extras = self.data.get("extras", [])
        widgets = sum(1 for item in extras if item.get("type") in WIDGET_TYPES)
        folders = sum(1 for item in extras if item.get("type") == "folder")
        icons = len(self.data.get("icon_overrides", {}))
        plugins = len(self.data.get("plugins", {}))
        def describe(count, noun):
            return "No %s configured" % noun if count == 0 else "%s %s%s configured" % (
                count, noun, "" if count == 1 else "s")
        return {
            "widgets": describe(widgets, "widget"),
            "folders": describe(folders, "folder"),
            "icons": describe(icons, "icon override"),
            "plugins": describe(plugins, "plugin"),
        }

    def _refresh_summaries(self):
        for key, value in self._summary_text().items():
            label = self._summary_labels.get(key)
            if label is not None:
                label.set_text(value)

    def refresh(self):
        self.data = X.load()
        self._refresh_summaries()
