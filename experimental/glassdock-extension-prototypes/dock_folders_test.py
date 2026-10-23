# TEST FILE — safe to delete; does not affect originals
"""Folder persistence and fan-out geometry prototype."""

import json
import math
import os
import tempfile
from pathlib import Path
from collections.abc import Mapping


def folder_item(path, name=None, icon="", child_icon_overrides=None):
    folder_path = Path(path).expanduser().resolve()
    if not folder_path.is_dir():
        raise ValueError(f"not a directory: {folder_path}")
    if name is not None and (not isinstance(name, str) or not name.strip()):
        raise ValueError("name must be a non-empty string when provided")
    if not isinstance(icon, str):
        raise ValueError("icon must be a string")
    if child_icon_overrides is None:
        child_icon_overrides = {}
    if not isinstance(child_icon_overrides, dict) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in child_icon_overrides.items()
    ):
        raise ValueError("child_icon_overrides must map string paths to string icons")
    return {
        "type": "folder",
        "path": str(folder_path),
        "name": folder_path.name if name is None else name.strip(),
        "icon": icon,
        "child_icon_overrides": dict(child_icon_overrides),
    }


def children_for(item, show_hidden=False):
    if not isinstance(item, Mapping):
        raise ValueError("folder item must be an object")
    if not isinstance(show_hidden, bool):
        raise ValueError("show_hidden must be a boolean")
    folder_path = item.get("path")
    if not isinstance(folder_path, str) or not folder_path.strip():
        raise ValueError("folder item must contain a non-empty path")
    root = Path(folder_path).expanduser()
    if not root.is_dir():
        raise ValueError(f"not a directory: {root}")
    overrides = item.get("child_icon_overrides", {})
    if not isinstance(overrides, Mapping) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in overrides.items()
    ):
        raise ValueError("child_icon_overrides must map string paths to string icons")

    paths = [path for path in root.iterdir() if show_hidden or not path.name.startswith(".")]
    paths.sort(key=lambda path: (not path.is_dir(), path.name.casefold(), path.name))
    return [
        {
            "name": path.name,
            "path": str(path),
            "is_dir": path.is_dir(),
            "icon": overrides.get(str(path), ""),
        }
        for path in paths
    ]


def _finite_number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    if not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return float(value)


def fan_positions(
    count,
    origin,
    radius=112,
    angle_degrees=110,
    start_degrees=-145,
    stagger_ms=28,
    stiffness=220,
    damping=22,
):
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError("count must be a non-negative integer")
    radius = _finite_number(radius, "radius")
    angle_degrees = _finite_number(angle_degrees, "angle_degrees")
    start_degrees = _finite_number(start_degrees, "start_degrees")
    stiffness = _finite_number(stiffness, "stiffness")
    damping = _finite_number(damping, "damping")
    stagger_ms = _finite_number(stagger_ms, "stagger_ms")
    if radius <= 0 or not 30 <= angle_degrees <= 180:
        raise ValueError("invalid fan geometry")
    if stagger_ms < 0 or stiffness <= 0 or damping < 0:
        raise ValueError("invalid animation parameters")
    if not isinstance(origin, (tuple, list)) or len(origin) != 2:
        raise ValueError("origin must contain x and y coordinates")
    ox, oy = (_finite_number(value, "origin coordinate") for value in origin)
    if count == 0:
        return []
    if count == 1:
        angles = [start_degrees + angle_degrees / 2]
    else:
        angles = [start_degrees + i * angle_degrees / (count - 1) for i in range(count)]
    return [
        {
            "index": index,
            "x": ox + radius * math.cos(math.radians(angle)),
            "y": oy + radius * math.sin(math.radians(angle)),
            "angle": angle,
            "delay_ms": index * stagger_ms,
            "spring": {"stiffness": stiffness, "damping": damping},
        }
        for index, angle in enumerate(angles)
    ]


class FolderStore:
    def __init__(self, config_path):
        self.path = Path(config_path).expanduser()

    def load(self):
        if not self.path.exists():
            return {"items": []}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid dock config at {self.path}: {exc}") from exc
        if not isinstance(data, dict) or not isinstance(data.get("items", []), list):
            raise ValueError("invalid dock config: expected an object with an items list")
        if any(not isinstance(item, dict) for item in data.get("items", [])):
            raise ValueError("invalid dock config: every item must be an object")
        return data

    def _save(self, data):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(data, stream, indent=2, ensure_ascii=False)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_name, self.path)
        except Exception:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise

    def add(self, path, **kwargs):
        data = self.load()
        item = folder_item(path, **kwargs)
        for existing in data.setdefault("items", []):
            if existing.get("type") == "folder" and existing.get("path") == item["path"]:
                return existing
        data["items"].append(item)
        self._save(data)
        return item


if __name__ == "__main__":
    import json

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        folder = root / "Folder"
        folder.mkdir()
        (folder / "Readme.txt").write_text("demo", encoding="utf-8")
        item = FolderStore(root / "config.json").add(folder, icon="folder-symbolic")
        print(json.dumps({"item": item, "children": children_for(item), "fan": fan_positions(5, (500, 400))}, indent=2))
