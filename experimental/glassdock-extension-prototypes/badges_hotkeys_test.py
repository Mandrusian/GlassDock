# TEST FILE — safe to delete; does not affect originals
"""Notification badge formatting and compositor-independent keybinding parsing."""

import re

_MODIFIERS = {"Super", "Ctrl", "Alt", "Shift"}
_KEY_PATTERN = re.compile(r"(?:[A-Za-z0-9]|F(?:[1-9]|1[0-2])|Space|Escape|Return)\\Z")


def _integer(value, label):
    if isinstance(value, bool):
        raise ValueError(f"{label} must be an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and re.fullmatch(r"[+-]?\\d+", value.strip()):
        return int(value.strip())
    raise ValueError(f"{label} must be an integer")


def badge_text(count, max_count=99):
    """Return an empty string for zero, a number, or a capped N+ label."""
    count = max(0, _integer(count, "count"))
    max_count = _integer(max_count, "max_count")
    if max_count < 1:
        raise ValueError("max_count must be at least 1")
    if count == 0:
        return ""
    return f"{max_count}+" if count > max_count else str(count)


def parse_binding(binding):
    """Parse a small portable keybinding grammar without registering a hotkey."""
    if not isinstance(binding, str):
        raise ValueError("binding must be a string")
    parts = binding.strip().split("+")
    if len(parts) < 2 or any(not part or part != part.strip() for part in parts):
        raise ValueError("expected modifier+key with no empty parts or surrounding spaces")

    modifiers, key = parts[:-1], parts[-1]
    if len(set(modifiers)) != len(modifiers):
        raise ValueError("duplicate modifiers are not allowed")
    if not set(modifiers) <= _MODIFIERS:
        raise ValueError("unsupported modifier")
    if not _KEY_PATTERN.fullmatch(key):
        raise ValueError("unsupported key")
    return {"modifiers": sorted(modifiers), "key": key}


def badge_accessible_label(app_name, count):
    """Build a concise label suitable for assistive technology."""
    if not isinstance(app_name, str) or not app_name.strip():
        raise ValueError("app_name must be a non-empty string")
    count = _integer(count, "count")
    name = app_name.strip()
    return name if count <= 0 else f"{name}, {count} notifications"


if __name__ == "__main__":
    print({"badge": badge_text(123), "hotkey": parse_binding("Super+Shift+D")})
