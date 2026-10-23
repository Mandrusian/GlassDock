# TEST FILE — safe to delete; does not affect originals
"""Validated extension-settings schema, independent of the live GTK settings UI."""

from copy import deepcopy
import math

from badges_hotkeys_test import parse_binding


EXTENSION_SCHEMA = {
    "icons": {
        "finder": {"path": "", "allow_builtin_fallback": True},
        "trash": {"path": "", "allow_builtin_fallback": True},
        "apps": {"path": "", "allow_builtin_fallback": True},
        "overrides": {},
    },
    "widgets": {
        "enabled": ["analog_clock", "digital_clock", "calendar", "music"],
        "analog_clock": {"format": "12h", "show_seconds": False, "sweep": True},
        "digital_clock": {"format": "%H:%M", "show_seconds": False},
        "calendar": {"first_weekday": 0, "week_starts": "monday"},
        "music": {"provider": "playerctl", "show_controls_on_hover": True},
    },
    "folders": {
        "enabled": True,
        "fan_angle_degrees": 110,
        "radius": 112,
        "stagger_ms": 28,
        "spring": {"stiffness": 220, "damping": 22},
        "custom_icon": "",
        "child_icon_overrides": {},
    },
    "plugins": {
        "enabled": True,
        "directory": "plugins_test",
        "allowlist": [],
        "disabled": [],
        "tick_interval_ms": 250,
    },
    "extras": {
        "reorder": {"enabled": True, "animation_ms": 180, "physics": "spring"},
        "badges": {"enabled": True, "max_count": 99},
        "hotkeys": {"enabled": False, "bindings": {"toggle_dock": "Super+Shift+D"}},
    },
}


def schema():
    return deepcopy(EXTENSION_SCHEMA)


def _merge(defaults, incoming, path):
    for key, value in incoming.items():
        current_path = f"{path}.{key}" if path else key
        if key in defaults and isinstance(defaults[key], dict):
            if not isinstance(value, dict):
                raise ValueError(f"{current_path} must be an object")
            _merge(defaults[key], value, current_path)
        else:
            defaults[key] = deepcopy(value)


def _require_bool(value, path):
    if not isinstance(value, bool):
        raise ValueError(f"{path} must be a boolean")


def _require_string(value, path, allow_empty=False):
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        qualifier = "a string" if allow_empty else "a non-empty string"
        raise ValueError(f"{path} must be {qualifier}")


def _bounded_int(value, path, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{path} must be an integer from {minimum} to {maximum}")


def _bounded_number(value, path, minimum, maximum, include_minimum=True):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{path} must be a finite number")
    valid_min = value >= minimum if include_minimum else value > minimum
    if not valid_min or value > maximum:
        relation = "greater than" if not include_minimum else "at least"
        raise ValueError(f"{path} must be {relation} {minimum} and at most {maximum}")


def _string_list(value, path, allowed=None):
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"{path} must be a list of non-empty strings")
    if len(set(value)) != len(value):
        raise ValueError(f"{path} must not contain duplicates")
    if allowed is not None and any(item not in allowed for item in value):
        raise ValueError(f"{path} contains an unsupported value")


def validate(config):
    """Merge extension settings over defaults and validate known options.

    Unknown top-level keys are ignored so a full application config can be passed in.
    Unknown keys inside extension objects are preserved for forward compatibility.
    """
    if not isinstance(config, dict):
        raise TypeError("config must be a dictionary")

    output = schema()
    for key, value in config.items():
        if key not in output:
            continue
        if not isinstance(value, dict):
            raise ValueError(f"{key} must be an object")
        _merge(output[key], value, key)

    icons = output["icons"]
    for key in ("finder", "trash", "apps"):
        _require_string(icons[key].get("path"), f"icons.{key}.path", allow_empty=True)
        _require_bool(icons[key].get("allow_builtin_fallback"), f"icons.{key}.allow_builtin_fallback")
    if not isinstance(icons["overrides"], dict):
        raise ValueError("icons.overrides must be an object")
    if any(not isinstance(key, str) or not isinstance(value, str) for key, value in icons["overrides"].items()):
        raise ValueError("icons.overrides must map strings to strings")

    widgets = output["widgets"]
    widget_names = {"analog_clock", "digital_clock", "calendar", "music"}
    _string_list(widgets["enabled"], "widgets.enabled", widget_names)
    _require_string(widgets["analog_clock"].get("format"), "widgets.analog_clock.format")
    if widgets["analog_clock"]["format"] not in {"12h", "24h"}:
        raise ValueError("widgets.analog_clock.format must be '12h' or '24h'")
    _require_bool(widgets["analog_clock"].get("show_seconds"), "widgets.analog_clock.show_seconds")
    _require_bool(widgets["analog_clock"].get("sweep"), "widgets.analog_clock.sweep")
    _require_string(widgets["digital_clock"].get("format"), "widgets.digital_clock.format")
    _require_bool(widgets["digital_clock"].get("show_seconds"), "widgets.digital_clock.show_seconds")
    _bounded_int(widgets["calendar"].get("first_weekday"), "widgets.calendar.first_weekday", 0, 6)
    if widgets["calendar"].get("week_starts") not in {"monday", "sunday"}:
        raise ValueError("widgets.calendar.week_starts must be 'monday' or 'sunday'")
    _require_string(widgets["music"].get("provider"), "widgets.music.provider")
    _require_bool(widgets["music"].get("show_controls_on_hover"), "widgets.music.show_controls_on_hover")

    folders = output["folders"]
    _require_bool(folders["enabled"], "folders.enabled")
    _bounded_int(folders["fan_angle_degrees"], "folders.fan_angle_degrees", 30, 180)
    _bounded_int(folders["radius"], "folders.radius", 20, 400)
    _bounded_int(folders["stagger_ms"], "folders.stagger_ms", 0, 1000)
    _bounded_number(folders["spring"].get("stiffness"), "folders.spring.stiffness", 0, 2000, include_minimum=False)
    _bounded_number(folders["spring"].get("damping"), "folders.spring.damping", 0, 500)
    _require_string(folders["custom_icon"], "folders.custom_icon", allow_empty=True)
    if not isinstance(folders["child_icon_overrides"], dict) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in folders["child_icon_overrides"].items()
    ):
        raise ValueError("folders.child_icon_overrides must map strings to strings")

    plugins = output["plugins"]
    _require_bool(plugins["enabled"], "plugins.enabled")
    _require_string(plugins["directory"], "plugins.directory")
    _string_list(plugins["allowlist"], "plugins.allowlist")
    _string_list(plugins["disabled"], "plugins.disabled")
    _bounded_int(plugins["tick_interval_ms"], "plugins.tick_interval_ms", 50, 10000)

    extras = output["extras"]
    _require_bool(extras["reorder"].get("enabled"), "extras.reorder.enabled")
    _bounded_int(extras["reorder"].get("animation_ms"), "extras.reorder.animation_ms", 0, 2000)
    if extras["reorder"].get("physics") not in {"spring", "linear", "none"}:
        raise ValueError("extras.reorder.physics must be 'spring', 'linear', or 'none'")
    _require_bool(extras["badges"].get("enabled"), "extras.badges.enabled")
    _bounded_int(extras["badges"].get("max_count"), "extras.badges.max_count", 1, 9999)
    _require_bool(extras["hotkeys"].get("enabled"), "extras.hotkeys.enabled")
    bindings = extras["hotkeys"].get("bindings")
    if not isinstance(bindings, dict):
        raise ValueError("extras.hotkeys.bindings must be an object")
    for action, binding in bindings.items():
        _require_string(action, "extras.hotkeys binding action")
        parse_binding(binding)
    return output


if __name__ == "__main__":
    import json

    print(json.dumps(validate({}), indent=2))
