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


class ExtensionPreferencesPage(Gtk.ScrolledWindow):
    """The extension-related core settings, grouped with the extension tools."""
    def __init__(self, store, shared_rows):
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for side in ("start", "end", "top", "bottom"):
            getattr(box, "set_margin_" + side)(18)
        box.pack_start(S.label("Extension defaults", "md-page-title"), False, False, 0)
        box.pack_start(S.label(
            "Defaults for clocks, music controls, folders, badges and trusted plugin loading.",
            "md-page-sub", wrap=True), False, False, 0)
        entries = [setting for setting in S.C.SCHEMA if setting.key.startswith("extensions.")]
        controls = S.settings_list()
        for setting in entries:
            row = S.SettingRow(setting, store)
            shared_rows.append(row)
            S.row_in_list(controls, row)
        box.pack_start(S.card(controls), False, False, 0)
        self.add(box)


class ExtensionsPanel(Gtk.Box):
    """Dedicated settings panel for dock widgets, folders, native icons and plugins."""
    def __init__(self, settings_store=None, settings_rows=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.pack_start(S.label("Extensions", "md-page-title"), False, False, 0)
        self.pack_start(S.label(
            "Manage dock widgets, fan folders, native icon overrides and trusted Python plugins. "
            "Plugin code is trusted code and is not sandboxed.",
            "md-page-sub", wrap=True), False, False, 0)
        self.data = X.load()
        self.notebook = Gtk.Notebook()
        self.notebook.set_scrollable(True)
        self.pages = [WidgetsPage(self.data), FoldersPage(self.data), IconsPage(self.data), PluginsPage(self.data)]
        labels = ("Widgets", "Folders", "Native icons", "Plugins")
        for page, title in zip(self.pages, labels):
            page.set_size_request(-1, 420)
            self.notebook.append_page(page, Gtk.Label(label=title))
        if settings_store is not None:
            self.preferences_page = ExtensionPreferencesPage(
                settings_store, settings_rows if settings_rows is not None else [])
            self.notebook.append_page(self.preferences_page, Gtk.Label(label="Defaults"))
        self.pack_start(self.notebook, True, True, 0)

    def refresh(self):
        self.data = X.load()
        for page in self.pages:
            page.data = self.data
        self.pages[-1].rebuild()
