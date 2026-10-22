#!/usr/bin/env python3
"""GTK 3 interface for GlassIcon Studio."""
from __future__ import annotations

import html
import os
import sys
from pathlib import Path

try:
    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    from gi.repository import Gdk, Gio, GLib, Gtk
except (ImportError, ValueError) as exc:
    print("GlassIcon Studio needs GTK 3 and PyGObject. Run ./scripts/install-deps.sh first.", file=sys.stderr)
    print(str(exc), file=sys.stderr)
    raise SystemExit(2)

import glassicon_core as core


CSS = r"""
window, .app-root { background-color: #0f141c; color: #edf3fb; }
headerbar { background-image: none; background-color: #131b27; border: none; border-bottom: 1px solid #283445; min-height: 44px; }
headerbar label { color: #f5f8fc; font-weight: 700; }
.sidebar { background-color: #121923; border-right: 1px solid #253041; }
.brand-title { color: #f5f8fc; font-size: 17px; font-weight: 800; }
.brand-subtitle, .muted, .helper { color: #98a8bc; }
.page-title { color: #f4f7fb; font-size: 25px; font-weight: 800; }
.page-subtitle { color: #9baabe; font-size: 13px; }
.panel { background-color: #171f2c; border: 1px solid #2a3749; border-radius: 17px; padding: 18px; }
.hero-panel { background-image: linear-gradient(120deg, #1b2a3b, #211f35); border: 1px solid #35445c; border-radius: 20px; padding: 23px; }
.panel-title { color: #eef5fd; font-size: 15px; font-weight: 750; }
.panel-subtitle { color: #a0b0c3; }
.stat-value { color: #9fe6f1; font-size: 24px; font-weight: 800; }
.stat-label { color: #9baabe; font-size: 12px; }
.nav-list { background: transparent; }
.nav-row { border-radius: 10px; margin: 3px 8px; padding: 10px; }
.nav-row:selected, .nav-row.active-nav { background-color: #28384c; }
.nav-row:selected label, .nav-row.active-nav label { color: #a7ecf5; font-weight: 700; }
.nav-row label { color: #c2cedd; }
.nav-row image { color: #aebcd0; }
button { background-image: none; background-color: #263345; color: #eaf2fc; border: 1px solid #35445a; border-radius: 10px; padding: 8px 13px; min-height: 18px; }
button:hover { background-color: #33445b; border-color: #4b617e; }
button:disabled { color: #647286; background-color: #202a37; }
button.suggested-action { background-image: none; background-color: #8be1ec; border-color: #8be1ec; color: #0c1821; font-weight: 800; }
button.suggested-action:hover { background-color: #b3f1f7; }
button.destructive-action { background-color: #422b36; border-color: #68404e; color: #ffdce5; }
entry, combobox, textview { background-color: #101722; color: #eef4fb; border: 1px solid #334156; border-radius: 9px; padding: 8px; caret-color: #9fe6f1; }
list, listbox { background-color: transparent; color: #edf3fb; }
.list-row { background-color: #171f2c; border: 1px solid #2a3749; border-radius: 12px; margin: 4px 0; padding: 8px; }
.list-row:selected { background-color: #26364a; border-color: #6bc8d8; }
.badge { background-color: #24394a; color: #9fe6f1; border-radius: 9px; padding: 4px 8px; font-size: 11px; font-weight: 700; }
.status-line { color: #9fe6f1; font-size: 12px; }
separator { background-color: #273345; min-height: 1px; }
scrolledwindow { border: none; }
progressbar trough { background-color: #243144; border-radius: 5px; }
progressbar progress { background-color: #88dfeb; border-radius: 5px; }
"""

NAV_ITEMS = [
    ("overview", "Overview", "view-grid-symbolic"),
    ("themes", "Icon themes", "preferences-desktop-icons-symbolic"),
    ("apps", "Application icons", "applications-graphics-symbolic"),
    ("system", "Files & system icons", "folder-symbolic"),
    ("restore", "Backups & restore", "document-revert-symbolic"),
]


def _label(text: str, css: str | None = None, wrap: bool = False) -> Gtk.Label:
    label = Gtk.Label(label=text)
    label.set_xalign(0)
    label.set_yalign(0.5)
    label.set_line_wrap(wrap)
    label.set_selectable(False)
    if css:
        label.get_style_context().add_class(css)
    return label


def _button(text: str, callback=None, css: str | None = None) -> Gtk.Button:
    button = Gtk.Button(label=text)
    if css:
        button.get_style_context().add_class(css)
    if callback:
        button.connect("clicked", callback)
    return button


def _class(widget: Gtk.Widget, name: str) -> Gtk.Widget:
    widget.get_style_context().add_class(name)
    return widget


def _panel(title: str, subtitle: str | None = None) -> Gtk.Box:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    box.get_style_context().add_class("panel")
    box.pack_start(_label(title, "panel-title"), False, False, 0)
    if subtitle:
        box.pack_start(_label(subtitle, "panel-subtitle", wrap=True), False, False, 0)
    return box


def _page(title: str, subtitle: str) -> tuple[Gtk.ScrolledWindow, Gtk.Box]:
    scroller = Gtk.ScrolledWindow()
    scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroller.set_overlay_scrolling(True)
    content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=17)
    content.set_margin_start(25)
    content.set_margin_end(25)
    content.set_margin_top(24)
    content.set_margin_bottom(25)
    content.pack_start(_label(title, "page-title"), False, False, 0)
    content.pack_start(_label(subtitle, "page-subtitle", wrap=True), False, False, 0)
    scroller.add(content)
    return scroller, content


def _icon_image(name: str, size: int = 26) -> Gtk.Image:
    try:
        theme = Gtk.IconTheme.get_default()
        if theme and theme.has_icon(name):
            return Gtk.Image.new_from_icon_name(name, Gtk.IconSize.INVALID)
        return Gtk.Image.new_from_icon_name("application-x-executable-symbolic", Gtk.IconSize.INVALID)
    except Exception:
        return Gtk.Image.new_from_icon_name("application-x-executable", Gtk.IconSize.DIALOG)


class GlassIconWindow(Gtk.ApplicationWindow):
    def __init__(self, application: Gtk.Application):
        super().__init__(application=application)
        self.set_title("GlassIcon Studio")
        self.set_default_size(1100, 760)
        self.set_size_request(820, 580)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.current_page = "overview"
        self.selected_theme: str | None = None
        self.selected_app: dict | None = None
        self.theme_rows: list[tuple[Gtk.ListBoxRow, dict]] = []
        self.app_rows: list[tuple[Gtk.ListBoxRow, dict]] = []
        self.nav_rows: dict[str, Gtk.ListBoxRow] = {}

        header = Gtk.HeaderBar()
        header.set_show_close_button(True)
        header.set_title("GlassIcon Studio")
        header.set_subtitle("Icons for every Linux desktop")
        self.set_titlebar(header)

        root = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        root.get_style_context().add_class("app-root")
        self.add(root)
        root.pack_start(self._build_sidebar(), False, False, 0)

        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        root.pack_start(right, True, True, 0)
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(130)
        right.pack_start(self.stack, True, True, 0)
        self.status_label = _label("Ready · changes stay in your user account", "status-line")
        self.status_label.set_margin_start(25)
        self.status_label.set_margin_end(25)
        self.status_label.set_margin_top(8)
        self.status_label.set_margin_bottom(9)
        right.pack_start(self.status_label, False, False, 0)

        self._build_overview()
        self._build_themes()
        self._build_apps()
        self._build_system()
        self._build_restore()
        self.refresh_all()
        self.navigate("overview")

    def _build_sidebar(self) -> Gtk.Widget:
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        sidebar.set_size_request(215, -1)
        sidebar.get_style_context().add_class("sidebar")
        brand = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        brand.set_margin_top(19)
        brand.set_margin_start(18)
        brand.set_margin_end(15)
        brand.set_margin_bottom(20)
        logo = Path(__file__).resolve().parent / "assets" / "glassicon.svg"
        if logo.is_file():
            image = Gtk.Image.new_from_file(str(logo))
            image.set_pixel_size(43)
        else:
            image = Gtk.Image.new_from_icon_name("preferences-desktop-icons", Gtk.IconSize.DIALOG)
        brand.pack_start(image, False, False, 0)
        brand_text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        brand_text.pack_start(_label("GlassIcon", "brand-title"), False, False, 0)
        brand_text.pack_start(_label("A GlassDock companion", "brand-subtitle"), False, False, 0)
        brand.pack_start(brand_text, True, True, 0)
        sidebar.pack_start(brand, False, False, 0)

        self.nav_list = Gtk.ListBox()
        self.nav_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.nav_list.get_style_context().add_class("nav-list")
        self.nav_list.connect("row-selected", self._on_nav_selected)
        for name, label, icon in NAV_ITEMS:
            row = Gtk.ListBoxRow()
            row.get_style_context().add_class("nav-row")
            row.nav_name = name
            inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            inner.set_margin_start(5)
            inner.set_margin_end(5)
            img = Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.MENU)
            inner.pack_start(img, False, False, 0)
            inner.pack_start(_label(label), True, True, 0)
            row.add(inner)
            self.nav_list.add(row)
            self.nav_rows[name] = row
        sidebar.pack_start(self.nav_list, False, False, 0)
        spacer = Gtk.Box()
        sidebar.pack_start(spacer, True, True, 0)
        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        separator.set_margin_start(14)
        separator.set_margin_end(14)
        sidebar.pack_start(separator, False, False, 8)
        open_icons = _button("Open icon folders", self._open_icon_folders)
        open_icons.set_margin_start(12)
        open_icons.set_margin_end(12)
        open_icons.set_margin_bottom(5)
        sidebar.pack_start(open_icons, False, False, 0)
        about = _label("GTK · KDE · GNOME · Xfce · WMs", "muted")
        about.set_margin_start(15)
        about.set_margin_bottom(15)
        sidebar.pack_start(about, False, False, 0)
        return sidebar

    def _on_nav_selected(self, _listbox, row):
        if row is not None:
            self.navigate(getattr(row, "nav_name", "overview"))

    def navigate(self, name: str) -> None:
        self.current_page = name
        self.stack.set_visible_child_name(name)
        row = self.nav_rows.get(name)
        if row and self.nav_list.get_selected_row() is not row:
            self.nav_list.select_row(row)
        self.refresh_page(name)

    def _build_overview(self) -> None:
        page, content = _page("Your desktop, re-iconified.", "Change icon themes, personalize individual launchers, and fix icons in file managers — without root access.")
        self.stack.add_named(page, "overview")
        hero = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        hero.get_style_context().add_class("hero-panel")
        hero.pack_start(_label("One place for all your icons", "panel-title"), False, False, 0)
        hero.pack_start(_label("GlassIcon works alongside your desktop settings. It can also write per-user GTK settings directly, which helps on lightweight window managers and in GTK apps such as Thunar.", "panel-subtitle", wrap=True), False, False, 0)
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=9)
        actions.pack_start(_button("Browse icon themes", lambda *_: self.navigate("themes"), "suggested-action"), False, False, 0)
        actions.pack_start(_button("Change an app icon", lambda *_: self.navigate("apps")), False, False, 0)
        hero.pack_start(actions, False, False, 5)
        content.pack_start(hero, False, False, 0)

        stats = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.stat_themes = self._stat_card("0", "Installed themes")
        self.stat_apps = self._stat_card("0", "Applications")
        self.stat_system = self._stat_card("0", "System overrides")
        self.stat_launchers = self._stat_card("0", "Launcher overrides")
        for card in (self.stat_themes, self.stat_apps, self.stat_system, self.stat_launchers):
            stats.pack_start(card, True, True, 0)
        content.pack_start(stats, False, False, 0)

        current_panel = _panel("Current icon setup")
        self.active_theme_label = _label("Detecting current theme…", "panel-title")
        self.active_theme_path = _label("", "muted", wrap=True)
        current_panel.pack_start(self.active_theme_label, False, False, 0)
        current_panel.pack_start(self.active_theme_path, False, False, 0)
        env_label = _label("", "muted", wrap=True)
        env_label.set_text("Desktop session: " + core.desktop_environment_label())
        current_panel.pack_start(env_label, False, False, 0)
        content.pack_start(current_panel, False, False, 0)

        safe = _panel("Designed to be reversible", "Theme changes and launcher overrides are written to your home directory. GlassIcon never edits files under /usr/share and does not need sudo.")
        safe.pack_start(_label("Tip: restart an already-open file manager or application after changing its theme or launcher icon. Different desktops cache icons differently.", "helper", wrap=True), False, False, 0)
        content.pack_start(safe, False, False, 0)

    def _stat_card(self, value: str, label: str) -> Gtk.Box:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        card.get_style_context().add_class("panel")
        value_label = _label(value, "stat-value")
        card.pack_start(value_label, False, False, 0)
        card.pack_start(_label(label, "stat-label", wrap=True), False, False, 0)
        card.value_label = value_label
        return card

    def _build_themes(self) -> None:
        page, content = _page("Icon themes", "Apply a complete icon pack to your desktop session, including GTK apps that do not follow a control panel setting.")
        self.stack.add_named(page, "themes")
        search = Gtk.SearchEntry()
        search.set_placeholder_text("Search installed icon themes…")
        search.connect("search-changed", self._filter_themes)
        content.pack_start(search, False, False, 0)
        self.theme_search = search

        list_panel = _panel("Installed themes", "Themes found in your user icon folders and system icon directories.")
        self.theme_list = Gtk.ListBox()
        self.theme_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.theme_list.set_filter_func(self._theme_filter)
        self.theme_list.connect("row-selected", self._on_theme_selected)
        theme_scroll = Gtk.ScrolledWindow()
        theme_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        theme_scroll.set_min_content_height(315)
        theme_scroll.set_max_content_height(390)
        theme_scroll.add(self.theme_list)
        list_panel.pack_start(theme_scroll, True, True, 0)
        content.pack_start(list_panel, True, True, 0)

        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=9)
        controls.pack_start(_button("Install theme archive…", self._install_theme_archive), False, False, 0)
        controls.pack_start(_button("Import theme folder…", self._import_theme_folder), False, False, 0)
        self.apply_theme_button = _button("Apply selected theme", self._apply_selected_theme, "suggested-action")
        controls.pack_start(self.apply_theme_button, False, False, 0)
        controls.pack_start(_button("Restore original theme", self._restore_original_theme), False, False, 0)
        controls.pack_start(_button("Open user icon folder", self._open_user_icons), False, False, 0)
        content.pack_start(controls, False, False, 0)
        content.pack_start(_label("Import ZIP, TAR, TAR.GZ, TAR.BZ2, or TAR.XZ packs directly. Imported themes are copied into your user icon folder without replacing an installed theme. GlassIcon writes GTK 3/4 settings and available GNOME, Xfce, KDE Plasma, xsettingsd, or LXQt settings. Running apps may need a restart.", "helper", wrap=True), False, False, 0)

    def _theme_filter(self, row: Gtk.ListBoxRow) -> bool:
        query = self.theme_search.get_text().casefold().strip() if hasattr(self, "theme_search") else ""
        data = getattr(row, "theme_data", {})
        return not query or query in (data.get("name", "") + " " + data.get("label", "")).casefold()

    def _filter_themes(self, *_args):
        self.theme_list.invalidate_filter()

    def _on_theme_selected(self, _listbox, row):
        if row is not None:
            self.selected_theme = row.theme_data["name"]
            self.apply_theme_button.set_sensitive(True)

    def _build_apps(self) -> None:
        page, content = _page("Application icons", "Set a custom icon for a launcher in the applications menu or dock. Original user launchers are backed up and can be restored.")
        self.stack.add_named(page, "apps")
        search = Gtk.SearchEntry()
        search.set_placeholder_text("Search apps by name, desktop ID, or command…")
        search.connect("search-changed", self._filter_apps)
        content.pack_start(search, False, False, 0)
        self.app_search = search

        list_panel = _panel("Installed applications", "Selecting an app changes its .desktop launcher icon, not the icon embedded inside an already-running window.")
        self.app_list = Gtk.ListBox()
        self.app_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.app_list.set_filter_func(self._app_filter)
        self.app_list.connect("row-selected", self._on_app_selected)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_min_content_height(365)
        scroll.set_max_content_height(480)
        scroll.add(self.app_list)
        list_panel.pack_start(scroll, True, True, 0)
        content.pack_start(list_panel, True, True, 0)
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=9)
        self.choose_app_icon_button = _button("Choose icon file…", self._choose_app_icon, "suggested-action")
        self.reset_app_button = _button("Reset selected icon", self._reset_selected_app_icon)
        self.choose_app_icon_button.set_sensitive(False)
        self.reset_app_button.set_sensitive(False)
        actions.pack_start(self.choose_app_icon_button, False, False, 0)
        actions.pack_start(self.reset_app_button, False, False, 0)
        content.pack_start(actions, False, False, 0)
        content.pack_start(_label("Supported image types: SVG, SVGZ, PNG, and XPM. Changes are stored under ~/.local/share/applications and take precedence over the system desktop file.", "helper", wrap=True), False, False, 0)

    def _app_filter(self, row: Gtk.ListBoxRow) -> bool:
        query = self.app_search.get_text().casefold().strip() if hasattr(self, "app_search") else ""
        data = getattr(row, "app_data", {})
        haystack = " ".join((data.get("name", ""), data.get("id", ""), data.get("exec", ""), data.get("icon", ""))).casefold()
        return not query or query in haystack

    def _filter_apps(self, *_args):
        self.app_list.invalidate_filter()

    def _on_app_selected(self, _listbox, row):
        self.selected_app = row.app_data if row else None
        self.choose_app_icon_button.set_sensitive(row is not None)
        self.reset_app_button.set_sensitive(bool(row and row.app_data.get("overridden")))

    def _build_system(self) -> None:
        page, content = _page("Files & system icons", "Override common icon names in a small user-only icon theme. Useful for folder, home, drive, trash, and file-type icons in Thunar and other file managers.")
        self.stack.add_named(page, "system")

        note = _panel("A small overlay, not a system-file replacement", "Your chosen image is added to ~/.local/share/icons/GlassIcon-Overrides (or a collision-safe variation). The overlay inherits the active theme, so every other icon stays unchanged.")
        content.pack_start(note, False, False, 0)

        chooser_panel = _panel("Customize a system icon")
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        row.pack_start(_label("Icon role", "muted"), False, False, 0)
        self.role_combo = Gtk.ComboBoxText()
        for role in core.SYSTEM_ICON_ROLES:
            self.role_combo.append(role["name"], role["label"] + "  ·  " + role["name"])
        self.role_combo.set_active_id("folder")
        row.pack_start(self.role_combo, True, True, 0)
        chooser_panel.pack_start(row, False, False, 0)
        role_actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=9)
        role_actions.pack_start(_button("Choose icon & apply…", self._choose_system_icon, "suggested-action"), False, False, 0)
        role_actions.pack_start(_button("Reset selected override", self._reset_selected_system_icon), False, False, 0)
        chooser_panel.pack_start(role_actions, False, False, 0)
        content.pack_start(chooser_panel, False, False, 0)

        overrides_panel = _panel("Custom system icons", "These names overlay the selected icon theme. Restart file managers after applying changes.")
        self.system_overrides_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        overrides_panel.pack_start(self.system_overrides_box, False, False, 0)
        content.pack_start(overrides_panel, False, False, 0)
        content.pack_start(_label("Thunar is a GTK app: applying a theme also updates your per-user GTK 3 icon-theme setting. GNOME, Xfce, KDE Plasma, and LXQt settings are written where supported; no root access is used.", "helper", wrap=True), False, False, 0)

    def _build_restore(self) -> None:
        page, content = _page("Backups & restore", "Review what GlassIcon changed and undo it. Resetting launcher icons is independent from resetting the system icon theme.")
        self.stack.add_named(page, "restore")

        theme_panel = _panel("Icon theme rollback", "GlassIcon remembers the theme that was active before your first theme change, where it could be detected.")
        theme_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.original_theme_label = _label("No original theme recorded", "panel-subtitle", wrap=True)
        theme_row.pack_start(self.original_theme_label, True, True, 0)
        theme_row.pack_start(_button("Restore original theme & system icons", self._restore_original_theme), False, False, 0)
        theme_panel.pack_start(theme_row, False, False, 0)
        content.pack_start(theme_panel, False, False, 0)

        launcher_panel = _panel("Application launcher overrides", "The source .desktop files in system folders are never edited. Reset removes generated user copies or restores your previous user file.")
        self.backup_apps_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        launcher_panel.pack_start(self.backup_apps_box, False, False, 0)
        launcher_panel.pack_start(_button("Reset all application icon changes", self._reset_all_apps, "destructive-action"), False, False, 0)
        content.pack_start(launcher_panel, False, False, 0)

        system_panel = _panel("System icon overrides", "Custom replacements are kept in a dedicated user theme. Reset any role individually from Files & system icons, or clear all overrides here.")
        self.backup_system_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        system_panel.pack_start(self.backup_system_box, False, False, 0)
        system_panel.pack_start(_button("Reset all custom system icons", self._reset_all_system, "destructive-action"), False, False, 0)
        content.pack_start(system_panel, False, False, 0)

    def refresh_all(self) -> None:
        self._refresh_overview()
        self._refresh_themes()
        self._refresh_apps()
        self._refresh_system_overrides()
        self._refresh_restore()

    def refresh_page(self, name: str) -> None:
        if name == "overview":
            self._refresh_overview()
        elif name == "themes":
            self._refresh_themes()
        elif name == "apps":
            self._refresh_apps()
        elif name == "system":
            self._refresh_system_overrides()
        elif name == "restore":
            self._refresh_restore()

    def _refresh_overview(self) -> None:
        themes = core.discover_icon_themes()
        apps = core.discover_applications()
        state = core.load_state()
        self.stat_themes.value_label.set_text(str(len(themes)))
        self.stat_apps.value_label.set_text(str(len(apps)))
        self.stat_system.value_label.set_text(str(len(state.get("system_overrides", {}))))
        self.stat_launchers.value_label.set_text(str(len(state.get("application_overrides", {}))))
        active = core.detect_icon_theme() or "Not detected"
        if state.get("overlay_theme") and active == state["overlay_theme"]:
            base = state.get("base_theme") or "hicolor"
            self.active_theme_label.set_text(f"{active}  ·  based on {base}")
        else:
            self.active_theme_label.set_text(active)
        self.active_theme_path.set_text("GTK 3 and 4 user settings are maintained by GlassIcon. The selected theme may need a restart to appear in already-open apps.")

    def _refresh_themes(self) -> None:
        if not hasattr(self, "theme_list"):
            return
        for row in list(self.theme_list.get_children()):
            self.theme_list.remove(row)
        self.theme_rows.clear()
        themes = core.discover_icon_themes()
        active = core.detect_icon_theme()
        for theme in themes:
            row = Gtk.ListBoxRow()
            row.get_style_context().add_class("list-row")
            row.theme_data = theme
            line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            image = Gtk.Image.new_from_icon_name("folder", Gtk.IconSize.DIALOG)
            image.set_pixel_size(33)
            line.pack_start(image, False, False, 3)
            labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            labels.pack_start(_label(theme["label"], "panel-title"), False, False, 0)
            path_text = theme["path"]
            if theme.get("generated") and theme["name"] == (core.load_state().get("overlay_theme")):
                path_text += "  ·  GlassIcon custom layer"
            labels.pack_start(_label(path_text, "muted"), False, False, 0)
            line.pack_start(labels, True, True, 0)
            if theme["name"] == active:
                line.pack_start(_label("ACTIVE", "badge"), False, False, 0)
            row.add(line)
            self.theme_list.add(row)
            self.theme_rows.append((row, theme))
            if theme["name"] == active:
                self.selected_theme = theme["name"]
        self.theme_list.show_all()
        self.theme_list.invalidate_filter()
        if self.theme_rows:
            target = next((row for row, theme in self.theme_rows if theme["name"] == active), self.theme_rows[0][0])
            if self.theme_list.get_selected_row() is None:
                self.theme_list.select_row(target)
        self.apply_theme_button.set_sensitive(bool(self.selected_theme))

    def _refresh_apps(self) -> None:
        if not hasattr(self, "app_list"):
            return
        current_id = self.selected_app.get("id") if self.selected_app else None
        for row in list(self.app_list.get_children()):
            self.app_list.remove(row)
        self.app_rows.clear()
        apps = core.discover_applications()
        for app in apps:
            row = Gtk.ListBoxRow()
            row.get_style_context().add_class("list-row")
            row.app_data = app
            line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            image = self._application_image(app, 34)
            line.pack_start(image, False, False, 2)
            labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            labels.pack_start(_label(app["name"], "panel-title"), False, False, 0)
            icon_desc = app["icon"] or "No icon set"
            labels.pack_start(_label(f"{app['id']}  ·  {icon_desc}", "muted"), False, False, 0)
            line.pack_start(labels, True, True, 0)
            if app.get("overridden"):
                line.pack_start(_label("CUSTOM", "badge"), False, False, 0)
            row.add(line)
            self.app_list.add(row)
            self.app_rows.append((row, app))
        self.app_list.show_all()
        self.app_list.invalidate_filter()
        if current_id:
            row = next((row for row, app in self.app_rows if app["id"] == current_id), None)
            if row:
                self.app_list.select_row(row)
        self.choose_app_icon_button.set_sensitive(self.selected_app is not None)
        self.reset_app_button.set_sensitive(bool(self.selected_app and self.selected_app.get("overridden")))

    def _application_image(self, app: dict, size: int) -> Gtk.Image:
        icon = app.get("icon", "")
        if icon and Path(icon).expanduser().is_file():
            try:
                image = Gtk.Image.new_from_file(str(Path(icon).expanduser()))
                image.set_pixel_size(size)
                return image
            except Exception:
                pass
        try:
            theme = Gtk.IconTheme.get_default()
            if theme and icon:
                info = theme.lookup_icon(icon, size, Gtk.IconLookupFlags.FORCE_SIZE)
                if info:
                    image = Gtk.Image.new_from_file(info.get_filename())
                    image.set_pixel_size(size)
                    return image
        except Exception:
            pass
        image = Gtk.Image.new_from_icon_name("application-x-executable", Gtk.IconSize.DIALOG)
        image.set_pixel_size(size)
        return image

    def _refresh_system_overrides(self) -> None:
        if not hasattr(self, "system_overrides_box"):
            return
        for child in list(self.system_overrides_box.get_children()):
            self.system_overrides_box.remove(child)
        overrides = core.load_state().get("system_overrides", {})
        if not overrides:
            self.system_overrides_box.pack_start(_label("No custom system icons yet. Start with Folder or Home for an easy-to-see change.", "muted", wrap=True), False, False, 5)
        for name, record in sorted(overrides.items(), key=lambda item: item[1].get("label", item[0]).casefold()):
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            image_path = Path(record.get("installed_path", ""))
            if image_path.is_file():
                image = Gtk.Image.new_from_file(str(image_path))
                image.set_pixel_size(26)
            else:
                image = Gtk.Image.new_from_icon_name(name, Gtk.IconSize.DIALOG)
            row.pack_start(image, False, False, 0)
            labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            labels.pack_start(_label(record.get("label", name), "panel-title"), False, False, 0)
            labels.pack_start(_label(name, "muted"), False, False, 0)
            row.pack_start(labels, True, True, 0)
            reset = _button("Reset", lambda _b, role=name: self._reset_system_icon_named(role))
            row.pack_start(reset, False, False, 0)
            self.system_overrides_box.pack_start(row, False, False, 3)
        self.system_overrides_box.show_all()

    def _refresh_restore(self) -> None:
        if not hasattr(self, "backup_apps_box"):
            return
        state = core.load_state()
        original = state.get("original_theme")
        self.original_theme_label.set_text(f"Previous theme: {original}" if original else "No previous theme recorded yet.")
        for child in list(self.backup_apps_box.get_children()):
            self.backup_apps_box.remove(child)
        apps = {app["id"]: app for app in core.discover_applications()}
        items = state.get("application_overrides", {})
        if not items:
            self.backup_apps_box.pack_start(_label("No launcher icon overrides are active.", "muted"), False, False, 4)
        for desktop_id in sorted(items):
            app = apps.get(desktop_id, {"name": desktop_id})
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            row.pack_start(_label(app.get("name", desktop_id), "panel-title"), True, True, 0)
            row.pack_start(_button("Restore", lambda _b, item=desktop_id: self._reset_app_named(item)), False, False, 0)
            self.backup_apps_box.pack_start(row, False, False, 3)
        for child in list(self.backup_system_box.get_children()):
            self.backup_system_box.remove(child)
        system = state.get("system_overrides", {})
        if not system:
            self.backup_system_box.pack_start(_label("No custom system icon overrides are active.", "muted"), False, False, 4)
        for name, record in sorted(system.items(), key=lambda item: item[1].get("label", item[0]).casefold()):
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            row.pack_start(_label(record.get("label", name), "panel-title"), True, True, 0)
            row.pack_start(_button("Reset", lambda _b, item=name: self._reset_system_icon_named(item)), False, False, 0)
            self.backup_system_box.pack_start(row, False, False, 3)
        self.backup_apps_box.show_all()
        self.backup_system_box.show_all()

    def _refresh_overrides_badges(self) -> None:
        self._refresh_overview()
        self._refresh_apps()
        self._refresh_system_overrides()
        self._refresh_restore()
        self.theme_list.invalidate_filter()

    def _set_status(self, text: str, error: bool = False) -> None:
        self.status_label.set_text(("Needs attention · " if error else "Ready · ") + text)
        context = self.status_label.get_style_context()
        if error:
            context.add_class("destructive-action")
        else:
            context.remove_class("destructive-action")

    def _message(self, title: str, text: str, error: bool = False) -> None:
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.ERROR if error else Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.CLOSE,
            text=title,
        )
        dialog.format_secondary_text(text)
        dialog.run()
        dialog.destroy()
        self._set_status(title + (" failed" if error else " complete"), error)

    def _confirm(self, title: str, text: str) -> bool:
        dialog = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.QUESTION,
                                   buttons=Gtk.ButtonsType.CANCEL, text=title)
        dialog.add_button("Continue", Gtk.ResponseType.OK)
        dialog.format_secondary_text(text)
        answer = dialog.run()
        dialog.destroy()
        return answer == Gtk.ResponseType.OK

    def _apply_selected_theme(self, *_args) -> None:
        name = self.selected_theme
        if not name:
            self._message("Choose a theme", "Select an installed icon theme first.", True)
            return
        try:
            result = core.apply_icon_theme(name)
        except (OSError, ValueError) as exc:
            self._message("Could not apply icon theme", str(exc), True)
            return
        if result["theme"] != name:
            message = f"Set {name} as the base theme and kept your custom system icons active in {result['theme']}."
        else:
            message = "Updated " + ", ".join(result["written"])
        if result["warnings"]:
            message += "\n\n" + "\n".join(result["warnings"])
        message += "\n\nOpen apps may need to be restarted to refresh their icons."
        self.refresh_all()
        self._message("Icon theme applied", message)

    def _restore_original_theme(self, *_args) -> None:
        if not self._confirm("Restore the original icon theme?", "This restores the detected previous icon theme and removes GlassIcon's custom system-icon overlay. Application launcher overrides are kept separate."):
            return
        try:
            result = core.restore_original_icon_theme()
        except (OSError, ValueError) as exc:
            self._message("Could not restore original theme", str(exc), True)
            return
        self.refresh_all()
        if result is None:
            self._message("No original theme available", "GlassIcon could not find a recorded previous theme, or that theme is no longer installed. Choose an installed theme from Icon themes.", True)
            return
        self._message("Original theme restored", "Your previous theme is selected again. Restart running file managers or applications if they do not refresh immediately.")

    def _choose_file(self, title: str) -> Path | None:
        dialog = Gtk.FileChooserDialog(title=title, parent=self, action=Gtk.FileChooserAction.OPEN)
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Choose", Gtk.ResponseType.ACCEPT)
        filter_images = Gtk.FileFilter()
        filter_images.set_name("Icon images (SVG, PNG, XPM)")
        for mime in ("image/svg+xml", "image/png", "image/x-xpixmap"):
            filter_images.add_mime_type(mime)
        for pattern in ("*.svg", "*.svgz", "*.png", "*.xpm"):
            filter_images.add_pattern(pattern)
        dialog.add_filter(filter_images)
        dialog.set_select_multiple(False)
        response = dialog.run()
        chosen = Path(dialog.get_filename()) if response == Gtk.ResponseType.ACCEPT and dialog.get_filename() else None
        dialog.destroy()
        if chosen and chosen.suffix.lower() not in core.SUPPORTED_IMAGE_EXTENSIONS:
            self._message("Unsupported icon format", "Choose an SVG, SVGZ, PNG, or XPM image.", True)
            return None
        return chosen

    def _install_theme_archive(self, *_args) -> None:
        dialog = Gtk.FileChooserDialog(title="Install an icon theme archive", parent=self, action=Gtk.FileChooserAction.OPEN)
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Install", Gtk.ResponseType.ACCEPT)
        archive_filter = Gtk.FileFilter()
        archive_filter.set_name("Icon theme archives (ZIP, TAR, TAR.GZ, TAR.BZ2, TAR.XZ)")
        for pattern in ("*.zip", "*.tar", "*.tar.gz", "*.tgz", "*.tar.bz2", "*.tbz2", "*.tar.xz", "*.txz"):
            archive_filter.add_pattern(pattern)
        dialog.add_filter(archive_filter)
        response = dialog.run()
        source = Path(dialog.get_filename()) if response == Gtk.ResponseType.ACCEPT and dialog.get_filename() else None
        dialog.destroy()
        if not source:
            return
        try:
            installed = core.install_icon_theme(source)
        except (OSError, ValueError, RuntimeError) as exc:
            self._message("Could not install icon theme", str(exc), True)
            return
        self.refresh_all()
        names = "\n".join(f"• {theme['label']}  ({theme['name']})" for theme in installed)
        self._message("Icon theme imported", f"Imported {len(installed)} theme folder(s) into your user icon directory:\n\n{names}\n\nSelect a theme in the list and choose Apply selected theme when you are ready.")

    def _import_theme_folder(self, *_args) -> None:
        dialog = Gtk.FileChooserDialog(title="Import an icon theme folder", parent=self, action=Gtk.FileChooserAction.SELECT_FOLDER)
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Import", Gtk.ResponseType.ACCEPT)
        response = dialog.run()
        source = Path(dialog.get_filename()) if response == Gtk.ResponseType.ACCEPT and dialog.get_filename() else None
        dialog.destroy()
        if not source:
            return
        try:
            installed = core.install_icon_theme(source)
        except (OSError, ValueError, RuntimeError) as exc:
            self._message("Could not import icon theme folder", str(exc), True)
            return
        self.refresh_all()
        names = "\n".join(f"• {theme['label']}  ({theme['name']})" for theme in installed)
        self._message("Icon theme imported", f"Imported {len(installed)} theme folder(s):\n\n{names}\n\nSelect a theme in the list and choose Apply selected theme when you are ready.")

    def _choose_app_icon(self, *_args) -> None:
        if not self.selected_app:
            return
        chosen = self._choose_file("Choose an application icon")
        if not chosen:
            return
        try:
            target = core.set_application_icon(self.selected_app["id"], chosen)
        except (OSError, ValueError) as exc:
            self._message("Could not change application icon", str(exc), True)
            return
        self.refresh_all()
        self._message("Application icon changed", f"A user-local launcher override was saved to:\n{target}\n\nNo system file was modified. Restart the dock or app menu if it still shows the old icon.")

    def _reset_selected_app_icon(self, *_args) -> None:
        if not self.selected_app:
            return
        self._reset_app_named(self.selected_app["id"])

    def _reset_app_named(self, desktop_id: str) -> None:
        try:
            changed = core.reset_application_icon(desktop_id)
        except (OSError, ValueError) as exc:
            self._message("Could not restore launcher", str(exc), True)
            return
        if not changed:
            self._message("No override found", "This launcher does not have a saved GlassIcon override.", True)
            return
        self.refresh_all()
        self._message("Launcher restored", f"The custom icon for {desktop_id} was removed or its previous user launcher was restored.")

    def _choose_system_icon(self, *_args) -> None:
        name = self.role_combo.get_active_id()
        if not name:
            return
        chosen = self._choose_file("Choose a replacement system icon")
        if not chosen:
            return
        try:
            result = core.set_system_icon(name, chosen)
        except (OSError, ValueError) as exc:
            self._message("Could not apply system icon", str(exc), True)
            return
        self.refresh_all()
        detail = f"The {core.ROLE_BY_NAME[name]['label']} icon was added to the user-only GlassIcon overlay.\n\nBase theme: {result.get('base_theme', 'detected theme')}\nOverlay: {result['theme']}\n\nRestart Thunar or other file managers to see the change."
        self._message("System icon applied", detail)

    def _reset_selected_system_icon(self, *_args) -> None:
        name = self.role_combo.get_active_id()
        if name:
            self._reset_system_icon_named(name)

    def _reset_system_icon_named(self, name: str) -> None:
        try:
            changed = core.reset_system_icon(name)
        except OSError as exc:
            self._message("Could not reset system icon", str(exc), True)
            return
        if not changed:
            self._message("No custom icon for this role", "There is no saved GlassIcon replacement for this icon role.")
            return
        self.refresh_all()
        self._message("System icon reset", f"The custom {name} icon was removed. Any running file manager may need to be restarted.")

    def _reset_all_apps(self, *_args) -> None:
        if not self._confirm("Reset all application icon changes?", "GlassIcon will remove generated launcher overrides and restore any user launcher files saved before the first change."):
            return
        count = core.reset_all_application_icons()
        self.refresh_all()
        self._message("Application icons reset", f"Restored {count} launcher override(s).")

    def _reset_all_system(self, *_args) -> None:
        if not self._confirm("Reset all custom system icons?", "This removes GlassIcon's custom icon overlay and returns to the theme that was active underneath it."):
            return
        count = core.reset_all_system_icons()
        self.refresh_all()
        self._message("System icons reset", f"Removed {count} custom system icon override(s).")

    def _open_icon_folders(self, *_args) -> None:
        core.open_directory(core.data_home() / "icons")

    def _open_user_icons(self, *_args) -> None:
        core.open_directory(core.data_home() / "icons")


class GlassIconApplication(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=core.APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.window: GlassIconWindow | None = None

    def do_activate(self):
        if self.window is None:
            apply_css()
            self.window = GlassIconWindow(self)
        self.window.show_all()
        self.window.present()


def apply_css() -> None:
    provider = Gtk.CssProvider()
    provider.load_from_data(CSS.encode("utf-8"))
    screen = Gdk.Screen.get_default()
    if screen:
        Gtk.StyleContext.add_provider_for_screen(screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


def main() -> int:
    app = GlassIconApplication()
    return app.run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
