"""Configuration schema, defaults, validation, migration and persistence.

The SCHEMA is the single source of truth: the settings GUI generates one
control per entry, validation coerces every entry, and the dock reads every
entry by key. tests/test_coverage.py enforces that all three stay in sync.
"""
import copy
import json
import math
import os
import re
import time
from dataclasses import dataclass

from .colors import normalize_color
from .themes import CUSTOM, DEFAULT_THEME, THEMES

CONFIG_VERSION = 3

CATEGORIES = [
    ("style", "Colors & Style"),
    ("size", "Size & Spacing"),
    ("animation", "Animation"),
    ("indicators", "Indicators"),
    ("position", "Position"),
    ("behavior", "Behavior"),
]


@dataclass(frozen=True)
class Setting:
    key: str
    label: str
    category: str
    type: str                 # bool | int | float | choice | color | text
    default: object
    min: float = None
    max: float = None
    step: float = None
    choices: tuple = ()       # ((value, label), ...)
    help: str = ""
    keywords: str = ""
    depends: tuple = None     # (other_key, required_value)
    unit: str = ""


def _s(*a, **k):
    return Setting(*a, **k)


SCHEMA = [
    # ---- Colors & Style
    _s("appearance.bg_color", "Background color", "style", "color", "#1d1d22",
       keywords="fill panel charcoal"),
    _s("appearance.bg_opacity", "Background opacity", "style", "float", 0.72,
       min=0.0, max=1.0, step=0.01, keywords="transparency translucent alpha"),
    _s("appearance.bg_gradient", "Use gradient", "style", "bool", False,
       help="Blend from the background color to a second color."),
    _s("appearance.bg_color2", "Gradient end color", "style", "color", "#2c2c36",
       depends=("appearance.bg_gradient", True)),
    _s("appearance.gradient_direction", "Gradient direction", "style", "choice", "vertical",
       choices=(("vertical", "Vertical"), ("horizontal", "Horizontal"), ("diagonal", "Diagonal")),
       depends=("appearance.bg_gradient", True)),
    _s("appearance.border_color", "Border color", "style", "color", "#ffffff"),
    _s("appearance.border_opacity", "Border opacity", "style", "float", 0.16,
       min=0.0, max=1.0, step=0.01),
    _s("appearance.border_width", "Border width", "style", "float", 1.0,
       min=0.0, max=6.0, step=0.5, unit="px"),
    _s("appearance.corner_radius", "Corner radius", "style", "int", 22,
       min=0, max=120, step=1, unit="px", keywords="rounded corners round radius pill",
       help="Rounding of the dock panel. Values above half the dock's height just give a pill shape."),
    _s("appearance.icon_radius", "Icon corner radius", "style", "int", 0,
       min=0, max=50, step=1, unit="%", keywords="rounded corners squircle circle icons",
       help="Rounds the corners of every icon. 0 keeps each icon as its app drew it; 50 makes circles."),
    _s("appearance.shadow", "Drop shadow", "style", "bool", True),
    _s("appearance.shadow_size", "Shadow size", "style", "int", 18,
       min=0, max=40, step=1, unit="px", depends=("appearance.shadow", True)),
    _s("appearance.shadow_opacity", "Shadow strength", "style", "float", 0.45,
       min=0.0, max=1.0, step=0.01, depends=("appearance.shadow", True)),
    _s("appearance.show_labels", "Show name labels on hover", "style", "bool", True,
       keywords="tooltip title"),
    _s("appearance.label_bg", "Label background", "style", "color", "#1d1d22",
       depends=("appearance.show_labels", True)),
    _s("appearance.label_color", "Label text color", "style", "color", "#ffffff",
       depends=("appearance.show_labels", True)),
    _s("appearance.blur", "Background blur (SwayFX only)", "style", "bool", False,
       help="Asks SwayFX to blur what is behind the dock. On plain Sway this "
            "has no effect and the dock stays translucent without blur.",
       keywords="frosted glass swayfx layer_effects"),

    # ---- Size & Spacing
    _s("size.icon_size", "Icon size", "size", "int", 52, min=24, max=128, step=1, unit="px"),
    _s("size.spacing", "Icon spacing", "size", "int", 8, min=0, max=32, step=1, unit="px"),
    _s("size.padding", "Dock padding", "size", "int", 10, min=0, max=32, step=1, unit="px"),
    _s("size.margin", "Distance from screen edge", "size", "int", 10,
       min=0, max=120, step=1, unit="px", keywords="gap offset"),

    # ---- Animation
    _s("animation.magnify", "Hover magnification", "animation", "bool", True,
       keywords="zoom"),
    _s("animation.magnify_factor", "Magnification factor", "animation", "float", 1.5,
       min=1.0, max=2.5, step=0.05, depends=("animation.magnify", True)),
    _s("animation.magnify_range", "Magnification reach", "animation", "float", 2.0,
       min=0.5, max=4.0, step=0.25, unit="icons", depends=("animation.magnify", True)),
    _s("animation.duration", "Animation duration", "animation", "int", 180,
       min=0, max=800, step=10, unit="ms", help="0 disables animations."),
    _s("animation.easing", "Show/hide easing", "animation", "choice", "ease-out",
       choices=(("ease-out", "Ease out"), ("ease-in-out", "Ease in-out"), ("linear", "Linear"))),
    _s("animation.launch_bounce", "Bounce icon while launching", "animation", "bool", True),

    # ---- Indicators
    _s("indicators.style", "Running indicator", "indicators", "choice", "dot",
       choices=(("dot", "Dots"), ("line", "Line"), ("none", "None"))),
    _s("indicators.color", "Indicator color", "indicators", "color", "#ffffff",
       depends=("indicators.style", ("dot", "line"))),
    _s("indicators.active_color", "Focused-app indicator color", "indicators", "color", "#8ab4ff",
       depends=("indicators.style", ("dot", "line"))),
    _s("indicators.size", "Indicator size", "indicators", "int", 4, min=2, max=10, step=1,
       unit="px", depends=("indicators.style", ("dot", "line"))),

    # ---- Position
    _s("position.edge", "Screen edge", "position", "choice", "bottom",
       choices=(("bottom", "Bottom"), ("top", "Top"), ("left", "Left"), ("right", "Right"))),
    _s("position.alignment", "Alignment along edge", "position", "choice", "center",
       choices=(("start", "Start (left/top)"), ("center", "Center"), ("end", "End (right/bottom)"))),

    # ---- Behavior
    _s("behavior.autohide", "Auto-hide", "behavior", "choice", "off",
       choices=(("off", "Off"), ("always", "Always (reveal on edge hover)"),
                ("overlap", "When a window overlaps the dock"))),
    _s("behavior.show_delay", "Reveal delay", "behavior", "int", 0, min=0, max=2000, step=50,
       unit="ms", depends=("behavior.autohide", ("always", "overlap"))),
    _s("behavior.hide_delay", "Hide delay", "behavior", "int", 400, min=0, max=3000, step=50,
       unit="ms", depends=("behavior.autohide", ("always", "overlap"))),
    _s("behavior.hide_on_fullscreen", "Hide while a window is fullscreen", "behavior", "bool", True),
    _s("behavior.exclusive_zone", "Reserve screen space (windows won't overlap)", "behavior",
       "bool", False, help="Only applies when auto-hide is off."),
    _s("behavior.layer", "Stacking layer", "behavior", "choice", "top",
       choices=(("top", "Top (normal)"), ("overlay", "Overlay (above fullscreen apps)"))),
    _s("behavior.show_running_unpinned", "Show running apps that are not pinned", "behavior",
       "bool", True),
    _s("behavior.launcher_command", "Applications button command", "behavior", "text", "fuzzel",
       help="Run when the Applications item is clicked."),
    _s("behavior.autostart", "Start GlassDock automatically at login", "behavior", "bool", True,
       keywords="startup boot login session",
       help="Master switch for login autostart (set up by install.sh)."),
    _s("behavior.autostart_wms", "Only auto-start in these sessions/WMs", "behavior", "text", "sway",
       depends=("behavior.autostart", True), keywords="window manager compositor hyprland niri river",
       help="Comma-separated, e.g. sway, hyprland, niri. Use * for every session. Matched against "
            "XDG_CURRENT_DESKTOP, XDG_SESSION_DESKTOP and DESKTOP_SESSION."),
    _s("behavior.terminal_command", "Terminal for terminal apps", "behavior", "text", "foot",
       help="Used for launchers that need a terminal (run as: terminal -e command)."),

    # ---- Widgets & Extensions
    _s("extensions.clock_format", "Clock format", "behavior", "choice", "24h",
       choices=(("24h", "24-hour"), ("12h", "12-hour"))),
    _s("extensions.clock_show_seconds", "Show seconds in the clock label", "behavior", "bool", False),
    _s("extensions.calendar_first_weekday", "Calendar first day of week", "behavior", "choice", "monday",
       choices=(("monday", "Monday"), ("sunday", "Sunday"))),
    _s("extensions.music_playerctl", "Music-control executable", "behavior", "text", "playerctl",
       help="Uses playerctl for MPRIS-compatible media players. Install it to enable media controls."),
    _s("extensions.music_refresh_seconds", "Music metadata refresh", "behavior", "float", 2.0,
       min=1.0, max=30.0, step=0.5, unit="s"),
    _s("extensions.music_controls_on_hover", "Show music status on hover", "behavior", "bool", True),
    _s("extensions.folder_show_hidden", "Show hidden files in folder menus", "behavior", "bool", False),
    _s("extensions.folder_popup_limit", "Maximum folder-menu entries", "behavior", "int", 30,
       min=5, max=100, step=5),
    _s("extensions.folder_fan_radius", "Folder fan radius", "behavior", "int", 96,
       min=60, max=150, step=2, unit="px"),
    _s("extensions.folder_fan_angle", "Folder fan angle", "behavior", "int", 110,
       min=60, max=150, step=5, unit="°"),
    _s("extensions.badges_enabled", "Show item badges", "behavior", "bool", True),
    _s("extensions.badge_max_count", "Maximum badge label", "behavior", "int", 99,
       min=1, max=9999, step=1),
    _s("extensions.plugins_enabled", "Enable trusted user plugins", "behavior", "bool", True,
       help="Plugins are ordinary Python code, not sandboxed. Only allowlist code you trust."),
    _s("extensions.plugin_directory", "Plugin directory", "behavior", "text", "",
       help="Leave blank to use the GlassDock config folder's plugins directory."),
    _s("extensions.plugin_allowlist", "Allowed plugin module names", "behavior", "text", "",
       help="Comma-separated Python filenames without .py. Only explicitly listed plugins are loaded."),
]

SETTINGS = {s.key: s for s in SCHEMA}

# Settings that may be overridden per monitor.
MONITOR_OVERRIDE_KEYS = [
    "position.edge", "position.alignment", "size.icon_size", "size.margin",
    "behavior.autohide",
]

SPECIAL_KINDS = {
    "apps": {"name": "Applications", "icon": "view-app-grid-symbolic"},
    "trash": {"name": "Trash", "icon": "user-trash"},
}


# ------------------------------------------------------------- coercion

def coerce(setting, value):
    """Coerce value to the setting's type/range. Raises ValueError/TypeError."""
    t = setting.type
    if t == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            v = value.strip().lower()
            if v in ("1", "true", "yes", "on"):
                return True
            if v in ("0", "false", "no", "off"):
                return False
        raise ValueError("not a bool: %r" % (value,))
    if t in ("int", "float"):
        if isinstance(value, bool):
            raise ValueError("bool is not a number")
        f = float(value)
        if not math.isfinite(f):
            raise ValueError("non-finite number")
        if setting.min is not None:
            f = max(setting.min, f)
        if setting.max is not None:
            f = min(setting.max, f)
        return int(round(f)) if t == "int" else float(f)
    if t == "choice":
        v = str(value)
        if v not in [c[0] for c in setting.choices]:
            raise ValueError("invalid choice %r" % (value,))
        return v
    if t == "color":
        return normalize_color(value)
    if t == "text":
        return str(value)[:500]
    raise ValueError("unknown setting type %r" % t)


# ------------------------------------------------------------- helpers

def get_path(cfg, key, default=None):
    node = cfg
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def set_path(cfg, key, value):
    parts = key.split(".")
    node = cfg
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value


def default_value(key):
    return SETTINGS[key].default


def default_settings():
    cfg = {}
    for s in SCHEMA:
        set_path(cfg, s.key, s.default)
    return cfg


def default_config(entries=None):
    cfg = default_settings()
    cfg["version"] = CONFIG_VERSION
    cfg["theme"] = DEFAULT_THEME
    cfg["items"] = default_items(entries)
    cfg["monitors"] = {}
    return cfg


# Alternatives per slot: the first installed one wins.
_DEFAULT_SLOTS = [
    ["org.mozilla.firefox.desktop", "firefox.desktop", "org.chromium.Chromium.desktop",
     "chromium-browser.desktop", "google-chrome.desktop"],
    ["org.gnome.Nautilus.desktop", "thunar.desktop", "org.kde.dolphin.desktop",
     "pcmanfm.desktop", "pcmanfm-qt.desktop"],
    ["foot.desktop", "org.gnome.Ptyxis.desktop", "org.gnome.Console.desktop",
     "org.gnome.Terminal.desktop", "kitty.desktop", "Alacritty.desktop",
     "org.wezfurlong.wezterm.desktop"],
    ["org.gnome.TextEditor.desktop", "org.gnome.gedit.desktop", "kate.desktop",
     "org.kde.kate.desktop", "mousepad.desktop"],
    ["org.gnome.Settings.desktop", "org.kde.systemsettings.desktop", "pavucontrol.desktop"],
]


def default_items(entries=None):
    items = [{"type": "special", "kind": "apps"}]
    if entries:
        for slot in _DEFAULT_SLOTS:
            for cand in slot:
                if cand in entries:
                    items.append({"type": "app", "id": cand})
                    break
    items.append({"type": "separator"})
    items.append({"type": "special", "kind": "trash"})
    return items


def validate_items(items):
    """Validate persisted dock items without discarding extension item fields."""
    out = []
    seen_apps, seen_widgets, seen_folders, seen_plugins = set(), set(), set(), set()
    if not isinstance(items, list):
        return None

    def add(spec, raw):
        count = raw.get("badge_count") if isinstance(raw, dict) else None
        if isinstance(count, int) and not isinstance(count, bool) and count >= 0:
            spec["badge_count"] = min(count, 999999)
        out.append(spec)

    for it in items:
        if not isinstance(it, dict):
            continue
        t = it.get("type")
        if t == "app":
            aid = it.get("id")
            if isinstance(aid, str) and aid and aid not in seen_apps:
                seen_apps.add(aid)
                app = {"type": "app", "id": aid}
                for key, cap in (("name", 100), ("icon", 500)):
                    value = it.get(key)
                    if isinstance(value, str) and value.strip():
                        app[key] = value.strip()[:cap]
                add(app, it)
        elif t == "launcher":
            name, command = it.get("name"), it.get("exec")
            if isinstance(name, str) and name.strip() and isinstance(command, str) and command.strip():
                entry = {"type": "launcher", "name": name.strip()[:100],
                         "exec": command.strip()[:1000], "icon": str(it.get("icon", "") or "")[:500]}
                match = it.get("match")
                if isinstance(match, str) and match.strip():
                    entry["match"] = match.strip()[:200]
                add(entry, it)
        elif t == "separator":
            out.append({"type": "separator"})
        elif t == "special":
            if it.get("kind") in SPECIAL_KINDS:
                add({"type": "special", "kind": it["kind"]}, it)
        elif t == "folder":
            path = it.get("path")
            if not isinstance(path, str) or not path.strip():
                continue
            path = os.path.abspath(os.path.expanduser(path.strip()))
            if path in seen_folders:
                continue
            seen_folders.add(path)
            name = it.get("name")
            icon = it.get("icon")
            spec = {"type": "folder", "path": path,
                    "name": name.strip()[:100] if isinstance(name, str) and name.strip() else os.path.basename(path) or path,
                    "icon": icon.strip()[:500] if isinstance(icon, str) else "folder"}
            add(spec, it)
        elif t == "widget":
            kind = it.get("kind")
            if kind not in ("clock", "calendar", "music") or kind in seen_widgets:
                continue
            seen_widgets.add(kind)
            add({"type": "widget", "kind": kind}, it)
        elif t == "plugin":
            name = it.get("name")
            if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", name):
                continue
            if name in seen_plugins:
                continue
            seen_plugins.add(name)
            spec = {"type": "plugin", "name": name}
            icon = it.get("icon")
            if isinstance(icon, str) and icon.strip():
                spec["icon"] = icon.strip()[:500]
            add(spec, it)
    return out


def validate_monitors(monitors):
    out = {}
    if not isinstance(monitors, dict):
        return out
    for name, ov in monitors.items():
        if not isinstance(name, str) or not isinstance(ov, dict):
            continue
        clean = {}
        if "enabled" in ov:
            try:
                clean["enabled"] = coerce(Setting("enabled", "", "", "bool", True), ov["enabled"])
            except (ValueError, TypeError):
                pass
        for key in MONITOR_OVERRIDE_KEYS:
            if key in ov:
                try:
                    clean[key] = coerce(SETTINGS[key], ov[key])
                except (ValueError, TypeError):
                    pass
        out[name] = clean
    return out


def validate(cfg, entries=None):
    """Return a fully valid copy of cfg; bad values fall back to defaults."""
    out = default_config(entries)
    if not isinstance(cfg, dict):
        return out
    for s in SCHEMA:
        raw = get_path(cfg, s.key, None)
        if raw is None:
            continue
        try:
            set_path(out, s.key, coerce(s, raw))
        except (ValueError, TypeError):
            pass
    theme = cfg.get("theme")
    is_user_theme = isinstance(theme, str) and re.fullmatch(r"user:[a-z0-9][a-z0-9-]{0,47}", theme)
    out["theme"] = theme if (theme in THEMES or theme == CUSTOM or is_user_theme) else CUSTOM
    if "items" in cfg:
        items = validate_items(cfg["items"])
        if items is not None:
            out["items"] = items
    out["monitors"] = validate_monitors(cfg.get("monitors", {}))
    out["version"] = CONFIG_VERSION
    return out


# ------------------------------------------------------------ migrations

def migrate(cfg):
    """Upgrade old config layouts to CONFIG_VERSION. Unknown/new versions are
    returned unchanged (validate() will drop what it does not know)."""
    if not isinstance(cfg, dict):
        return cfg
    cfg = copy.deepcopy(cfg)
    version = cfg.get("version", 0)
    if not isinstance(version, int):
        version = 0
    if version < 1:
        # v0: flat keys
        flat_map = {
            "icon_size": "size.icon_size", "spacing": "size.spacing",
            "padding": "size.padding", "margin": "size.margin",
            "edge": "position.edge", "alignment": "position.alignment",
            "autohide": "behavior.autohide", "opacity": "appearance.bg_opacity",
            "radius": "appearance.corner_radius",
        }
        for old, new in flat_map.items():
            if old in cfg and not isinstance(cfg[old], dict):
                set_path(cfg, new, cfg.pop(old))
        pinned = cfg.pop("pinned", None)
        if isinstance(pinned, list) and "items" not in cfg:
            cfg["items"] = [{"type": "app", "id": p} for p in pinned if isinstance(p, str)]
        version = 1
    if version < 2:
        # v1: autohide was a boolean
        ah = get_path(cfg, "behavior.autohide")
        if isinstance(ah, bool):
            set_path(cfg, "behavior.autohide", "always" if ah else "off")
        version = 2
    if version < 3:
        # v2: built-in widgets and trusted user plugins use defaulted extension settings.
        version = 3
    cfg["version"] = version
    return cfg


# ----------------------------------------------------------- per-monitor

def effective(cfg, output_name):
    """Config for one output with that monitor's overrides applied."""
    eff = copy.deepcopy(cfg)
    ov = cfg.get("monitors", {}).get(output_name, {})
    for key in MONITOR_OVERRIDE_KEYS:
        if key in ov:
            set_path(eff, key, ov[key])
    return eff


def monitor_enabled(cfg, output_name):
    return cfg.get("monitors", {}).get(output_name, {}).get("enabled", True)


# ------------------------------------------------------------- themes

def apply_theme(cfg, name):
    """Copy a built-in theme's values into cfg and record the theme name."""
    if name == CUSTOM:
        cfg["theme"] = CUSTOM
        return cfg
    if name not in THEMES:
        raise KeyError(name)
    for key, value in THEMES[name]["values"].items():
        set_path(cfg, key, coerce(SETTINGS[key], value))
    cfg["theme"] = name
    return cfg


THEME_KEYS = sorted({k for t in THEMES.values() for k in t["values"]})


def matches_theme(cfg, name):
    return all(get_path(cfg, k) == coerce(SETTINGS[k], v) for k, v in THEMES[name]["values"].items())


# ----------------------------------------------------------- persistence

def config_dir(env=None):
    env = os.environ if env is None else env
    base = env.get("XDG_CONFIG_HOME") or os.path.join(env.get("HOME", os.path.expanduser("~")), ".config")
    return os.path.join(base, "glassdock")


def config_path(env=None):
    return os.path.join(config_dir(env), "config.json")


LEGACY_NAME = "modern" + "dock"   # the project's previous name


def legacy_config_path(env=None):
    env = os.environ if env is None else env
    base = env.get("XDG_CONFIG_HOME") or os.path.join(env.get("HOME", os.path.expanduser("~")), ".config")
    return os.path.join(base, LEGACY_NAME, "config.json")


def _read_legacy():
    try:
        with open(legacy_config_path(), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def load_config(path=None, entries=None):
    """Load, migrate and validate the config. A missing file yields defaults;
    a corrupt file is moved aside (config.json.corrupt-<time>) first."""
    use_default = path is None
    path = path or config_path()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except FileNotFoundError:
        raw = _read_legacy() if use_default else None
        if raw is None:
            return default_config(entries)
    except (OSError, ValueError):
        try:
            os.replace(path, "%s.corrupt-%d" % (path, int(time.time())))
        except OSError:
            pass
        return default_config(entries)
    return validate(migrate(raw), entries)


def save_config(cfg, path=None):
    path = path or config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = "%s.tmp-%d" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)
