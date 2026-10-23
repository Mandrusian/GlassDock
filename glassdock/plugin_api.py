# Integrated GlassDock extension module.
"""Plugin API: drop a .py into plugins/ (project dir or ~/.config/glassdock/plugins/).

A plugin module defines ONE subclass of PluginBase. The dock never crashes because of a plugin:
every call is wrapped; 3 exceptions disable that plugin and the error shows in Settings > Plugins.
No GTK knowledge needed: render() gets a plain cairo context.
"""
import importlib.util
import math
import os
import re
import shlex
import subprocess
import sys
import traceback

ALLOWED_STATS = {"now", "cpu", "ram", "temp", "battery", "uptime", "net", "usage", "usage_top"}
NET_STATS = {"weather"}
PERMISSIONS = ("network", "run_commands")
MAX_ERRORS = 3
_PLUGIN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}\Z")
DEFAULT_COLORS = {"accent": (0.35, 0.65, 1.0, 1.0), "fg": (1, 1, 1, 0.95), "bg": (0.11, 0.11, 0.13, 1.0),
                  "warn": (1.0, 0.27, 0.23, 1.0), "ok": (0.2, 0.84, 0.4, 1.0)}


class StatsView:
    """Permission-gated window onto stats.Stats."""

    def __init__(self, stats, perms):
        self._s, self._perms = stats, set(perms)

    def __getattr__(self, name):
        if name in ALLOWED_STATS or (name in NET_STATS and "network" in self._perms):
            return getattr(self._s, name)
        if name in NET_STATS:
            raise PermissionError("plugin needs PERMISSIONS = ['network'] to use stats.%s" % name)
        raise AttributeError(name)


class PluginContext:
    def __init__(self, name, stats, config, perms, host):
        self.name, self.stats, self._config, self._perms, self._host = name, StatsView(stats, perms), config, perms, host

    def cfg(self, key):
        return self._config.get(key)

    @property
    def colors(self):
        return self._host.colors() if self._host else dict(DEFAULT_COLORS)

    def redraw(self):
        if self._host:
            self._host.redraw()

    def notify(self, msg):
        if self._host:
            self._host.notify("%s: %s" % (self.name, msg))

    def run(self, cmd, terminal=False):
        """Launch a command detached. Needs 'run_commands' permission."""
        if "run_commands" not in self._perms:
            raise PermissionError("plugin needs PERMISSIONS = ['run_commands'] to call ctx.run")
        argv = shlex.split(cmd) if isinstance(cmd, str) else list(cmd)
        if not argv or any(not isinstance(part, str) or "\x00" in part for part in argv):
            raise ValueError("ctx.run requires a non-empty argument list of strings")
        if terminal and self._host:
            argv = self._host.terminal_prefix() + argv
        try:
            subprocess.Popen(argv, start_new_session=True, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, ValueError) as exc:
            self.notify("Could not start command: %s" % exc)
            raise


class PluginBase:
    NAME = "Unnamed plugin"
    TICK = 1.0            # seconds between on_tick calls (min 0.2)
    PERMISSIONS = []      # subset of ("network", "run_commands")
    TRANSPARENT = False   # True = you draw the whole tile yourself (no default dark glass tile)
    CONFIG = {}           # key -> {"type": bool|int|float|str|choice|color, "default":…, "label":…, "min","max","choices"}

    def __init__(self, ctx):
        self.ctx = ctx

    def on_load(self): pass
    def on_tick(self): pass
    def render(self, cr, w, h): pass               # draw on a w x h cairo context (origin top-left)
    def on_click(self, button): return None        # button 1 = click, 2 = middle/shift-click; may return list[str] for a popup
    def tooltip(self): return self.NAME


class PluginInstance:
    def __init__(self, name, cls, stats, config, host):
        self.name, self.cls, self.errors, self.last_error, self.disabled = name, cls, 0, "", False
        merged = {k: v.get("default") for k, v in cls.CONFIG.items()}
        merged.update({k: v for k, v in (config or {}).items() if k in merged})
        self.plugin = cls(PluginContext(name, stats, merged, cls.PERMISSIONS, host))
        self.next_tick = 0.0
        self.call("on_load")

    def call(self, method, *args, default=None):
        if self.disabled:
            return default
        try:
            return getattr(self.plugin, method)(*args)
        except Exception:  # noqa: BLE001 - plugin code is untrusted
            self.errors += 1
            self.last_error = traceback.format_exc(limit=3)
            print("[glassdock] plugin %s.%s failed:\n%s" % (self.name, method, self.last_error), file=sys.stderr)
            if self.errors >= MAX_ERRORS:
                self.disabled = True
            return default


def discover(dirs, allowlist=None):
    """Load only explicitly enabled plugin modules.

    ``allowlist`` is a collection of reviewed/enabled module names. Passing an
    empty collection loads nothing, so disabled modules are not executed merely
    because the settings page scans their directory. If the same module name is
    present in multiple directories, only the last directory's file is loaded.
    """
    if allowlist is None:
        allowed = set()
    else:
        allowed = set()
        for name in allowlist:
            if not isinstance(name, str) or not _PLUGIN_RE.fullmatch(name):
                raise ValueError("invalid plugin name: %r" % (name,))
            allowed.add(name)

    selected = {}
    for directory in dirs:
        if not os.path.isdir(directory):
            continue
        try:
            filenames = sorted(os.listdir(directory))
        except OSError:
            continue
        for filename in filenames:
            if filename.endswith(".py") and not filename.startswith("_"):
                name = filename[:-3]
                if name in allowed:
                    selected[name] = os.path.join(directory, filename)

    classes, errors = {}, {}
    for name, path in sorted(selected.items()):
        module_name = "glassdock_plugin_" + name
        try:
            spec = importlib.util.spec_from_file_location(module_name, path)
            if spec is None or spec.loader is None:
                raise ImportError("could not create a Python module loader")
            mod = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = mod
            spec.loader.exec_module(mod)
            candidates = [value for value in vars(mod).values()
                          if isinstance(value, type) and issubclass(value, PluginBase)
                          and value is not PluginBase and value.__module__ == mod.__name__]
            if len(candidates) != 1:
                raise ValueError("expected exactly one PluginBase subclass; found %d" % len(candidates))
            cls = candidates[0]
            perms = getattr(cls, "PERMISSIONS", [])
            if not isinstance(perms, (list, tuple, set)) or not set(perms) <= set(PERMISSIONS):
                raise ValueError("PERMISSIONS may contain only: %s" % ", ".join(PERMISSIONS))
            tick = getattr(cls, "TICK", 1.0)
            if isinstance(tick, bool) or not isinstance(tick, (int, float)) or not math.isfinite(tick) or tick < 0:
                raise ValueError("TICK must be a finite non-negative number")
            schema = getattr(cls, "CONFIG", {})
            if not isinstance(schema, dict) or len(schema) > 100:
                raise ValueError("CONFIG must be a mapping with at most 100 settings")
            for key, conf in schema.items():
                if not isinstance(key, str) or not _PLUGIN_RE.fullmatch(key) or not isinstance(conf, dict):
                    raise ValueError("CONFIG keys must be identifiers with mapping values")
                typ = conf.get("type", "str")
                if typ not in ("bool", "int", "float", "str", "choice", "color"):
                    raise ValueError("unsupported setting type %r for %s" % (typ, key))
                if "default" not in conf:
                    raise ValueError("setting %s must define a default" % key)
                default = conf.get("default")
                if typ == "bool" and not isinstance(default, bool):
                    raise ValueError("bool setting %s must have a boolean default" % key)
                if typ == "str" and (not isinstance(default, str) or len(default) > 4096):
                    raise ValueError("string setting %s must have a bounded string default" % key)
                if typ == "color" and (not isinstance(default, str) or not re.fullmatch(r"#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})", default)):
                    raise ValueError("color setting %s must have a hexadecimal default" % key)
                if typ == "choice":
                    choices = conf.get("choices")
                    if (not isinstance(choices, (list, tuple)) or not choices or len(choices) > 64
                            or any(not isinstance(value, str) or len(value) > 100 for value in choices)
                            or default not in choices):
                        raise ValueError("choice setting %s needs bounded string choices including its default" % key)
                if typ in ("int", "float"):
                    low, high = conf.get("min", 0), conf.get("max", 100)
                    if (isinstance(low, bool) or isinstance(high, bool) or isinstance(default, bool)
                            or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (low, high, default))
                            or (typ == "int" and any(int(v) != v for v in (low, high, default)))
                            or low > high or not low <= default <= high):
                        raise ValueError("invalid numeric setting range for %s" % key)
                label = conf.get("label", key)
                if not isinstance(label, str) or len(label) > 120:
                    raise ValueError("setting label for %s must be a bounded string" % key)
            classes[name] = cls
        except Exception as exc:  # plugin failures must not crash GlassDock
            sys.modules.pop(module_name, None)
            errors[name] = "%s: %s" % (type(exc).__name__, exc)
    return classes, errors
