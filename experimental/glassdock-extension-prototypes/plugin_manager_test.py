# TEST FILE — safe to delete; does not affect originals
"""Isolated plugin-host prototype. Python plugins are trusted code, not sandboxed."""

import copy
import hashlib
import importlib.util
import json
import math
import os
import sys
import time
import traceback
from pathlib import Path


class StatsAPI:
    def __init__(self, weather_provider=None):
        if weather_provider is not None and not callable(weather_provider):
            raise ValueError("weather_provider must be callable")
        self._opened = {}
        self._usage = {}
        self._weather_provider = weather_provider

    def record_open(self, key, when=None):
        if not isinstance(key, str) or not key.strip():
            raise ValueError("key must be a non-empty string")
        timestamp = time.time() if when is None else when
        if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)) or not math.isfinite(timestamp):
            raise ValueError("when must be a finite timestamp")
        self._usage[key] = self._usage.get(key, 0) + 1
        self._opened[key] = float(timestamp)

    def usage_count(self, key):
        return self._usage.get(key, 0)

    def last_opened(self, key):
        return self._opened.get(key)

    def cpu_percent(self):
        try:
            load = os.getloadavg()[0]
            count = max(1, os.cpu_count() or 1)
            return max(0.0, min(100.0, load / count * 100))
        except (AttributeError, OSError):
            return None

    def weather(self, location=None):
        if self._weather_provider is None:
            return None
        try:
            return self._weather_provider(location)
        except Exception:
            return None

    def snapshot(self):
        return {
            "usage": dict(self._usage),
            "last_opened": dict(self._opened),
            "cpu_percent": self.cpu_percent(),
        }


class PluginManager:
    REQUIRED = ("on_load", "on_click", "render", "on_tick", "config_schema")

    def __init__(self, directory="plugins_test", stats=None, config=None, allowlist=None, disabled=None):
        self.directory = Path(directory).expanduser()
        self.stats = stats if stats is not None else StatsAPI()
        if config is not None and not isinstance(config, dict):
            raise ValueError("config must be a dictionary")
        self.config = copy.deepcopy(config or {})
        self.allowlist = self._normalize_names(allowlist, "allowlist")
        self.disabled = self._normalize_names(disabled, "disabled")
        self.plugins = {}
        self.errors = {}
        self._module_names = set()

    @staticmethod
    def _normalize_names(values, label):
        if values is None:
            return set()
        if isinstance(values, str) or not isinstance(values, (list, tuple, set, frozenset)):
            raise ValueError(f"{label} must be a collection of plugin names")
        names = set(values)
        if any(not isinstance(name, str) or not name.strip() for name in names):
            raise ValueError(f"{label} entries must be non-empty strings")
        return names

    def discover(self):
        for module_name in self._module_names:
            sys.modules.pop(module_name, None)
        self._module_names.clear()
        self.plugins.clear()
        self.errors.clear()
        self.directory.mkdir(parents=True, exist_ok=True)

        for path in sorted(self.directory.glob("*.py")):
            if path.name.startswith("_"):
                continue
            if path.stem not in self.allowlist or path.stem in self.disabled:
                continue
            module_name = "_glassdock_plugin_" + hashlib.sha256(
                str(path.resolve()).encode("utf-8")
            ).hexdigest()[:16]
            try:
                spec = importlib.util.spec_from_file_location(module_name, path)
                if spec is None or spec.loader is None:
                    raise ImportError("no module loader")
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)
                plugin = getattr(module, "PLUGIN", None)
                missing = [name for name in self.REQUIRED if not callable(getattr(plugin, name, None))]
                if missing:
                    raise TypeError("missing methods: " + ", ".join(missing))
                plugin_config = self.config.get(path.stem, {})
                if not isinstance(plugin_config, dict):
                    raise TypeError(f"config for {path.stem} must be an object")
                config_schema = plugin.config_schema()
                if not isinstance(config_schema, dict):
                    raise TypeError("config_schema() must return an object")
                json.dumps(config_schema, allow_nan=False)
                plugin.on_load({"stats": self.stats, "config": copy.deepcopy(plugin_config)})
                self.plugins[path.stem] = plugin
                self._module_names.add(module_name)
            except Exception:
                sys.modules.pop(module_name, None)
                self.errors[path.stem] = traceback.format_exc(limit=3)
        return dict(self.plugins)

    def call(self, name, method, *args):
        try:
            plugin = self.plugins[name]
            callback = getattr(plugin, method)
            if not callable(callback):
                raise TypeError(f"{method} is not callable")
            result = callback(*args)
            if method == "render":
                json.dumps(result, allow_nan=False)
            self.errors.pop(name, None)
            return result
        except Exception:
            self.errors[name] = traceback.format_exc(limit=3)
            return None

    def tick(self, now=None):
        timestamp = time.time() if now is None else now
        if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)) or not math.isfinite(timestamp):
            raise ValueError("now must be a finite timestamp")
        return {name: self.call(name, "on_tick", float(timestamp)) for name in self.plugins}


PLUGIN_TEMPLATE = '''# TEST FILE — safe to delete; does not affect originals
"""Generated GlassDock plugin template. Replace every {{...}} placeholder."""

PLUGIN_NAME = "{{PLUGIN_NAME}}"
ICON_PATH = r"{{ICON_PATH}}"
CLICK_ACTION = "{{CLICK_ACTION}}"
CONFIG_KEYS = { {{CONFIG_KEYS}} }
STATS_USED = "{{STATS_USED}}"


class Plugin:
    def on_load(self, context):
        self.stats = context["stats"]
        self.config = context.get("config", {})

    def on_click(self, item=None):
        return {"action": CLICK_ACTION, "item": item}

    def render(self, context=None):
        return {
            "name": PLUGIN_NAME,
            "icon": ICON_PATH,
            "config": {key: self.config.get(key, value) for key, value in CONFIG_KEYS.items()},
            "stats": self.stats.snapshot(),
        }

    def on_tick(self, now):
        return None

    def config_schema(self):
        return CONFIG_KEYS


PLUGIN = Plugin()
'''


def write_template(path):
    destination = Path(path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(PLUGIN_TEMPLATE, encoding="utf-8")


if __name__ == "__main__":
    print("Plugin API ready; template length:", len(PLUGIN_TEMPLATE))
