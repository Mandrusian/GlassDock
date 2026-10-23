"""Runtime helpers for GlassDock's built-in widgets and trusted user plugins.

The helpers in this module are GTK-independent so the data handling remains
unit-testable. Plugins are ordinary Python modules and are not sandboxed:
only load code the user explicitly places on the allowlist.
"""
import calendar
import datetime as _datetime
import hashlib
import importlib.util
import json
import math
import os
import re
import subprocess
import sys
import time
import traceback
from pathlib import Path


_MODIFIERS = {"Super", "Ctrl", "Alt", "Shift"}
_KEYS = re.compile(r"(?:[A-Za-z0-9]|F(?:[1-9]|1[0-2])|Space|Escape|Return|Tab|Left|Right|Up|Down)\Z")
_PLUGIN_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}\Z")


def parse_hotkey(binding):
    """Validate a portable modifier+key description; registration is compositor-owned."""
    if not isinstance(binding, str):
        raise ValueError("hotkey must be a string")
    parts = binding.strip().split("+")
    if len(parts) < 2 or any(not part or part != part.strip() for part in parts):
        raise ValueError("expected modifier+key")
    modifiers, key = parts[:-1], parts[-1]
    if len(set(modifiers)) != len(modifiers) or not set(modifiers) <= _MODIFIERS:
        raise ValueError("invalid or repeated modifier")
    if not _KEYS.fullmatch(key):
        raise ValueError("unsupported key")
    return {"modifiers": sorted(modifiers), "key": key}


def badge_text(count, maximum=99):
    if isinstance(count, bool) or not isinstance(count, int):
        raise ValueError("badge count must be an integer")
    if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum < 1:
        raise ValueError("badge maximum must be a positive integer")
    count = max(0, count)
    return "" if count == 0 else (str(count) if count <= maximum else f"{maximum}+")


def clock_text(now=None, fmt="24h", show_seconds=False):
    if now is None:
        now = _datetime.datetime.now().astimezone()
    if not isinstance(now, _datetime.datetime):
        raise TypeError("now must be a datetime")
    if fmt not in ("12h", "24h"):
        raise ValueError("fmt must be '12h' or '24h'")
    pattern = "%I:%M" if fmt == "12h" else "%H:%M"
    text = now.strftime(pattern)
    if fmt == "12h":
        text = text.lstrip("0") or "12"
    if show_seconds:
        text += now.strftime(":%S")
    return text


def calendar_month(year=None, month=None, first_weekday=0):
    today = _datetime.date.today()
    year = today.year if year is None else year
    month = today.month if month is None else month
    if isinstance(year, bool) or not isinstance(year, int) or not 1 <= year <= 9999:
        raise ValueError("year must be an integer from 1 to 9999")
    if isinstance(month, bool) or not isinstance(month, int) or not 1 <= month <= 12:
        raise ValueError("month must be an integer from 1 to 12")
    if isinstance(first_weekday, bool) or first_weekday not in (0, 6):
        raise ValueError("first_weekday must be 0 (Monday) or 6 (Sunday)")
    cal = calendar.Calendar(firstweekday=first_weekday)
    headers = [calendar.day_abbr[(first_weekday + i) % 7] for i in range(7)]
    return {
        "year": year,
        "month": month,
        "month_name": calendar.month_name[month],
        "headers": headers,
        "weeks": cal.monthdayscalendar(year, month),
        "today": today.isoformat(),
    }


def folder_children(path, show_hidden=False):
    if not isinstance(show_hidden, bool):
        raise ValueError("show_hidden must be a boolean")
    root = Path(path).expanduser()
    if not root.is_dir():
        raise ValueError(f"folder is unavailable: {root}")
    children = [p for p in root.iterdir() if show_hidden or not p.name.startswith(".")]
    children.sort(key=lambda p: (not p.is_dir(), p.name.casefold(), p.name))
    return [
        {"name": child.name, "path": str(child), "is_dir": child.is_dir()}
        for child in children
    ]


def fan_positions(count, origin, radius=112, angle_degrees=110, start_degrees=-145):
    """Return deterministic radial positions used by animated folder presentations."""
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError("count must be a non-negative integer")
    values = (radius, angle_degrees, start_degrees, *origin)
    if len(origin) != 2 or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
        raise ValueError("geometry values must be finite numbers")
    if radius <= 0 or not 30 <= angle_degrees <= 180:
        raise ValueError("invalid folder fan geometry")
    if not count:
        return []
    angles = [start_degrees + angle_degrees / 2] if count == 1 else [
        start_degrees + i * angle_degrees / (count - 1) for i in range(count)
    ]
    ox, oy = origin
    return [
        {"x": ox + radius * math.cos(math.radians(angle)),
         "y": oy + radius * math.sin(math.radians(angle)), "angle": angle}
        for angle in angles
    ]


class MusicController:
    """Small, timeout-bound playerctl adapter; never called from a draw routine."""
    ACTIONS = {"play-pause", "play", "pause", "next", "previous", "stop"}

    def __init__(self, executable="playerctl", timeout=1.5):
        if not isinstance(executable, str) or not executable.strip():
            raise ValueError("playerctl executable must be non-empty")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be a positive finite number")
        self.executable = executable.strip()
        self.timeout = float(timeout)
        self.status = "Stopped"
        self.title = "Nothing playing"
        self._last_refresh = None
        self._last_error = ""

    def _run(self, *args):
        try:
            proc = subprocess.run(
                [self.executable, *args], capture_output=True, text=True,
                timeout=self.timeout, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            self._last_error = str(exc)
            return False, ""
        if proc.returncode:
            self._last_error = (proc.stderr or "").strip()
            return False, ""
        self._last_error = ""
        return True, proc.stdout.strip()

    def refresh(self, now=None, force=False, interval=2.0):
        now = time.monotonic() if now is None else now
        if isinstance(now, bool) or not isinstance(now, (int, float)) or not math.isfinite(now):
            raise ValueError("now must be a finite timestamp")
        if isinstance(interval, bool) or not isinstance(interval, (int, float)) or not math.isfinite(interval) or interval <= 0:
            raise ValueError("interval must be positive and finite")
        if not force and self._last_refresh is not None and now >= self._last_refresh and now - self._last_refresh < interval:
            return self.snapshot()
        status_ok, status = self._run("status")
        title_ok, title = self._run("metadata", "--format", "{{artist}} — {{title}}")
        self.status = status if status_ok and status else "Stopped"
        self.title = title if title_ok and title else "Nothing playing"
        self._last_refresh = float(now)
        return self.snapshot()

    def command(self, action):
        if action not in self.ACTIONS:
            raise ValueError("unsupported player action")
        ok, _ = self._run(action)
        if ok:
            self._last_refresh = None
        return ok

    def snapshot(self):
        return {"status": self.status, "title": self.title, "error": self._last_error}


class StatsAPI:
    """Small data interface for trusted plugins; no network provider is bundled."""
    def __init__(self):
        self._usage = {}
        self._last_opened = {}

    def record_open(self, key, when=None):
        if not isinstance(key, str) or not key.strip():
            raise ValueError("key must be a non-empty string")
        when = time.time() if when is None else when
        if isinstance(when, bool) or not isinstance(when, (int, float)) or not math.isfinite(when):
            raise ValueError("when must be a finite timestamp")
        self._usage[key] = self._usage.get(key, 0) + 1
        self._last_opened[key] = float(when)

    def usage_count(self, key):
        return self._usage.get(key, 0)

    def last_opened(self, key):
        return self._last_opened.get(key)

    def cpu_percent(self):
        try:
            return max(0.0, min(100.0, os.getloadavg()[0] * 100 / max(1, os.cpu_count() or 1)))
        except (AttributeError, OSError):
            return None

    def snapshot(self):
        return {"usage": dict(self._usage), "last_opened": dict(self._last_opened),
                "cpu_percent": self.cpu_percent()}


class PluginManager:
    """Load explicitly allowlisted Python plugins from a user-owned directory."""
    REQUIRED = ("on_load", "on_click", "render", "on_tick", "config_schema")

    def __init__(self, directory, allowlist=()):
        self.directory = Path(directory).expanduser()
        self.allowlist = set()
        for name in allowlist:
            if not isinstance(name, str) or not _PLUGIN_NAME.fullmatch(name):
                raise ValueError(f"invalid plugin name: {name!r}")
            self.allowlist.add(name)
        self.stats = StatsAPI()
        self.plugins = {}
        self.errors = {}
        self._modules = set()

    def discover(self):
        for module_name in self._modules:
            sys.modules.pop(module_name, None)
        self._modules.clear()
        self.plugins.clear()
        self.errors.clear()
        if not self.directory.is_dir():
            return {}
        for name in sorted(self.allowlist):
            path = (self.directory / (name + ".py")).resolve()
            if path.parent != self.directory.resolve() or not path.is_file():
                self.errors[name] = "Plugin file is missing or outside plugin directory"
                continue
            module_name = "_glassdock_extension_" + hashlib.sha256(str(path).encode()).hexdigest()[:16]
            try:
                spec = importlib.util.spec_from_file_location(module_name, path)
                if spec is None or spec.loader is None:
                    raise ImportError("could not create plugin loader")
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)
                plugin = getattr(module, "PLUGIN", None)
                missing = [method for method in self.REQUIRED if not callable(getattr(plugin, method, None))]
                if missing:
                    raise TypeError("missing methods: " + ", ".join(missing))
                schema = plugin.config_schema()
                json.dumps(schema, allow_nan=False)
                plugin.on_load({"stats": self.stats, "config": {}})
                self.plugins[name] = plugin
                self._modules.add(module_name)
            except Exception:
                sys.modules.pop(module_name, None)
                self.errors[name] = traceback.format_exc(limit=3)
        return dict(self.plugins)

    def render(self, name):
        try:
            value = self.plugins[name].render({})
            json.dumps(value, allow_nan=False)
            if not isinstance(value, dict):
                raise TypeError("render() must return an object")
            label = value.get("label", name)
            icon = value.get("icon", "")
            if not isinstance(label, str) or not isinstance(icon, str):
                raise TypeError("plugin label and icon must be strings")
            return {"label": label[:100], "icon": icon[:500]}
        except Exception:
            self.errors[name] = traceback.format_exc(limit=3)
            return {"label": name, "icon": ""}

    def click(self, name, item=None):
        try:
            result = self.plugins[name].on_click(item)
            json.dumps(result, allow_nan=False)
            return result
        except Exception:
            self.errors[name] = traceback.format_exc(limit=3)
            return None

    def tick(self, now=None):
        now = time.time() if now is None else now
        if isinstance(now, bool) or not isinstance(now, (int, float)) or not math.isfinite(now):
            raise ValueError("now must be finite")
        for name, plugin in self.plugins.items():
            try:
                plugin.on_tick(float(now))
            except Exception:
                self.errors[name] = traceback.format_exc(limit=3)
