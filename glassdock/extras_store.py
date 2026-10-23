"""Validated persistence for GlassDock's integrated native widgets and plugins.

The file lives beside config.json in the normal GlassDock configuration directory.
Writes use a same-directory temporary file and atomic replacement.
"""
import copy
import json
import math
import os
import re
import tempfile

from .core import config as C

CONFIG_DIR = C.config_dir()
PATH = os.path.join(CONFIG_DIR, "extensions.json")
USER_PLUGIN_DIR = os.path.join(CONFIG_DIR, "plugins")

WIDGET_SCHEMA = {
    "analog_clock": {
        "dial": {"type": "choice", "default": "minimal", "choices": ["minimal", "ticks", "roman"], "label": "Dial style"},
        "seconds": {"type": "bool", "default": True, "label": "Show second hand"},
        "smooth": {"type": "bool", "default": True, "label": "Smooth second hand (more redraws)"},
        "face_color": {"type": "color", "default": "#f7f7fa", "label": "Face color"},
        "hand_color": {"type": "color", "default": "#1c1c1e", "label": "Hand color"},
        "second_color": {"type": "color", "default": "#ff453a", "label": "Second-hand color"},
    },
    "digital_clock": {
        "format": {"type": "str", "default": "%H:%M", "label": "Time format (strftime)"},
        "show_date": {"type": "bool", "default": True, "label": "Show date line"},
        "date_format": {"type": "str", "default": "%a %d %b", "label": "Date format (strftime)"},
        "font": {"type": "str", "default": "Sans", "label": "Font family"},
        "text_color": {"type": "color", "default": "#ffffff", "label": "Text color"},
        "bg_color": {"type": "color", "default": "#1c1c1e", "label": "Background color"},
    },
    "calendar": {
        "show_week_numbers": {"type": "bool", "default": True, "label": "Show week numbers"},
        "accent": {"type": "color", "default": "#ff3b30", "label": "Header color"},
    },
    "music": {
        "player": {"type": "str", "default": "", "label": "Prefer player (name contains…)"},
        "hover_controls": {"type": "bool", "default": True, "label": "Previous / Play / Next on hover"},
        "show_art": {"type": "bool", "default": True, "label": "Show album art"},
    },
}
FOLDER_SCHEMA = {
    "name": {"type": "str", "default": "Folder", "label": "Name"},
    "icon": {"type": "path", "default": "", "label": "Custom icon (image path, empty = auto preview)"},
    "path": {"type": "path", "default": "", "label": "Directory to show (optional)"},
    "spread": {"type": "int", "default": 90, "min": 30, "max": 160, "label": "Fan spread (degrees)"},
    "radius": {"type": "int", "default": 0, "min": 0, "max": 400, "label": "Fan radius px (0 = auto)"},
}
ICON_KEYS = {"apps": "Apps launcher", "trash": "Trash (empty)", "trash_full": "Trash (full)"}
DEFAULTS = {"extras": [], "icon_overrides": {}, "folders": {}, "plugins": {}, "widgets": {}}
_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,80}\Z")
_PLUGIN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}\Z")
_COLOR_RE = re.compile(r"#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\Z")


def defaults_for(schema):
    return {key: spec["default"] for key, spec in schema.items()}


_INVALID = object()


def _json_safe(value, depth=0):
    """Copy bounded JSON values while rejecting NaN/Infinity and exotic objects."""
    if depth > 8:
        return _INVALID
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else _INVALID
    if isinstance(value, str):
        return value[:4096]
    if isinstance(value, list):
        result = []
        for child in value[:200]:
            safe = _json_safe(child, depth + 1)
            if safe is not _INVALID:
                result.append(safe)
        return result
    if isinstance(value, dict):
        result = {}
        for key, child in list(value.items())[:200]:
            if not isinstance(key, str):
                continue
            safe = _json_safe(child, depth + 1)
            if safe is not _INVALID:
                result[key[:120]] = safe
        return result
    return _INVALID


def _bounded_text(value, limit=4096):
    if not isinstance(value, str) or "\x00" in value:
        return ""
    return value.strip()[:limit]


def _coerce_value(spec, value):
    kind = spec.get("type")
    if kind == "bool":
        return value if isinstance(value, bool) else spec["default"]
    if kind in ("int", "float"):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            return spec["default"]
        value = max(spec.get("min", value), min(spec.get("max", value), value))
        return int(value) if kind == "int" else float(value)
    if kind == "choice":
        return value if value in spec.get("choices", []) else spec["default"]
    if kind == "color":
        return value.lower() if isinstance(value, str) and _COLOR_RE.fullmatch(value) else spec["default"]
    if kind in ("str", "path"):
        return _bounded_text(value, 4096)
    return spec["default"]


def _clean_mapping(raw, allowed, defaults=None):
    raw = raw if isinstance(raw, dict) else {}
    result = copy.deepcopy(defaults or {})
    for key, spec in allowed.items():
        if key in raw:
            result[key] = _coerce_value(spec, raw[key])
    return result


def _normalize(raw):
    data = copy.deepcopy(DEFAULTS)
    for key, default in DEFAULTS.items():
        if isinstance(raw, dict) and isinstance(raw.get(key), type(default)):
            data[key] = raw[key]

    extras = []
    used = set()
    for entry in data["extras"][:200]:
        if not isinstance(entry, dict):
            continue
        wid = entry.get("id")
        kind = entry.get("type")
        if not isinstance(wid, str) or not _ID_RE.fullmatch(wid) or wid in used:
            continue
        if kind not in (*WIDGET_SCHEMA.keys(), "folder"):
            continue
        at = entry.get("at")
        if isinstance(at, bool) or not isinstance(at, int) or at < 0:
            at = None
        extras.append({"id": wid, "type": kind, "at": at})
        used.add(wid)
    data["extras"] = extras

    data["icon_overrides"] = {
        key: _bounded_text(value)
        for key, value in data["icon_overrides"].items()
        if key in ICON_KEYS and isinstance(value, str)
    }

    folders = {}
    raw_folders = data["folders"]
    for fid, raw_folder in list(raw_folders.items())[:200]:
        if not isinstance(fid, str) or not _ID_RE.fullmatch(fid) or not isinstance(raw_folder, dict):
            continue
        cfg = _clean_mapping(raw_folder, FOLDER_SCHEMA, defaults_for(FOLDER_SCHEMA))
        cfg["apps"] = [_bounded_text(v, 255) for v in raw_folder.get("apps", [])[:100]
                       if isinstance(v, str) and v.strip()] if isinstance(raw_folder.get("apps", []), list) else []
        cfg["files"] = [_bounded_text(v) for v in raw_folder.get("files", [])[:100]
                        if isinstance(v, str) and v.strip()] if isinstance(raw_folder.get("files", []), list) else []
        raw_icons = raw_folder.get("child_icons", {})
        cfg["child_icons"] = {str(k)[:255]: _bounded_text(v) for k, v in list(raw_icons.items())[:100]
                              if isinstance(k, str) and isinstance(v, str)} if isinstance(raw_icons, dict) else {}
        folders[fid] = cfg
    data["folders"] = folders

    widgets = {}
    for wid, raw_widget in list(data["widgets"].items())[:200]:
        if not isinstance(wid, str) or not _ID_RE.fullmatch(wid) or not isinstance(raw_widget, dict):
            continue
        # A widget's actual type is fixed by its entry; unknown field values are harmlessly dropped
        # here and then restricted again by widget_cfg once the type is known.
        clean_widget = {}
        for k, v in list(raw_widget.items())[:40]:
            if not isinstance(k, str):
                continue
            safe = _json_safe(v)
            if safe is not _INVALID:
                clean_widget[k[:80]] = safe
        widgets[wid] = clean_widget
    data["widgets"] = widgets

    plugins = {}
    for name, conf in list(data["plugins"].items())[:100]:
        if not isinstance(name, str) or not _PLUGIN_RE.fullmatch(name) or not isinstance(conf, dict):
            continue
        raw_config = conf.get("config", {})
        safe_config = _json_safe(raw_config) if isinstance(raw_config, dict) else {}
        plugins[name] = {
            "enabled": conf.get("enabled") is True,
            "config": safe_config if isinstance(safe_config, dict) else {},
        }
    data["plugins"] = plugins
    return data


def load(path=None):
    path = path or PATH
    try:
        with open(path, "r", encoding="utf-8") as stream:
            raw = json.load(stream)
    except (OSError, UnicodeError, ValueError):
        return copy.deepcopy(DEFAULTS)
    return _normalize(raw)


def save(data, path=None):
    path = path or PATH
    normalized = _normalize(data)
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, mode=0o700, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="." + os.path.basename(path) + ".", suffix=".tmp", dir=parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(normalized, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def widget_cfg(data, wid, wtype):
    schema = WIDGET_SCHEMA.get(wtype, {})
    raw = data.get("widgets", {}).get(wid, {}) if isinstance(data.get("widgets"), dict) else {}
    return _clean_mapping(raw, schema, defaults_for(schema))


def folder_cfg(data, fid):
    raw = data.get("folders", {}).get(fid, {}) if isinstance(data.get("folders"), dict) else {}
    cfg = _clean_mapping(raw, FOLDER_SCHEMA, defaults_for(FOLDER_SCHEMA))
    cfg["apps"] = list(raw.get("apps", [])) if isinstance(raw, dict) and isinstance(raw.get("apps", []), list) else []
    cfg["files"] = list(raw.get("files", [])) if isinstance(raw, dict) and isinstance(raw.get("files", []), list) else []
    cfg["child_icons"] = dict(raw.get("child_icons", {})) if isinstance(raw, dict) and isinstance(raw.get("child_icons", {}), dict) else {}
    return cfg


def new_id(data, prefix):
    used = {entry.get("id") for entry in data.get("extras", []) if isinstance(entry, dict)}
    n = 1
    while "%s%d" % (prefix, n) in used:
        n += 1
    return "%s%d" % (prefix, n)
