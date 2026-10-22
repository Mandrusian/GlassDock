#!/usr/bin/env python3
"""Safe, per-user Linux icon theme and launcher icon management for GlassIcon."""
from __future__ import annotations

import configparser
import json
import os
import posixpath
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

APP_ID = "org.mandrus.glassicon"
APP_NAME = "GlassIcon Studio"
VERSION = "1.0.0"
SUPPORTED_IMAGE_EXTENSIONS = {".svg", ".svgz", ".png", ".xpm"}
STATE_VERSION = 1

SYSTEM_ICON_ROLES = [
    {"label": "Folder", "name": "folder", "context": "places"},
    {"label": "Open folder", "name": "folder-open", "context": "places"},
    {"label": "Home", "name": "user-home", "context": "places"},
    {"label": "Desktop", "name": "user-desktop", "context": "places"},
    {"label": "Documents", "name": "folder-documents", "context": "places"},
    {"label": "Downloads", "name": "folder-download", "context": "places"},
    {"label": "Pictures", "name": "folder-pictures", "context": "places"},
    {"label": "Music", "name": "folder-music", "context": "places"},
    {"label": "Videos", "name": "folder-videos", "context": "places"},
    {"label": "Trash", "name": "user-trash", "context": "places"},
    {"label": "Full trash", "name": "user-trash-full", "context": "places"},
    {"label": "Computer", "name": "computer", "context": "devices"},
    {"label": "Hard drive", "name": "drive-harddisk", "context": "devices"},
    {"label": "Removable drive", "name": "drive-removable-media", "context": "devices"},
    {"label": "Optical disc", "name": "drive-optical", "context": "devices"},
    {"label": "Network server", "name": "network-server", "context": "places"},
    {"label": "Applications menu", "name": "start-here", "context": "places"},
    {"label": "Generic document", "name": "text-x-generic", "context": "mimetypes"},
    {"label": "Image file", "name": "image-x-generic", "context": "mimetypes"},
    {"label": "Audio file", "name": "audio-x-generic", "context": "mimetypes"},
    {"label": "Video file", "name": "video-x-generic", "context": "mimetypes"},
    {"label": "Archive file", "name": "application-x-archive", "context": "mimetypes"},
    {"label": "PDF document", "name": "application-pdf", "context": "mimetypes"},
]
ROLE_BY_NAME = {role["name"]: role for role in SYSTEM_ICON_ROLES}


def home_dir() -> Path:
    return Path(os.environ.get("HOME") or str(Path.home())).expanduser()


def config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or home_dir() / ".config").expanduser()


def data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or home_dir() / ".local/share").expanduser()


def state_home() -> Path:
    return Path(os.environ.get("XDG_STATE_HOME") or home_dir() / ".local/state").expanduser()


def app_config_dir() -> Path:
    return config_home() / "glassicon"


def state_dir() -> Path:
    return state_home() / "glassicon"


def _unique_paths(paths: list[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        try:
            key = str(path.expanduser().resolve())
        except OSError:
            key = str(path.expanduser())
        if key not in seen:
            seen.add(key)
            result.append(path.expanduser())
    return result


def icon_theme_roots() -> list[Path]:
    roots = [data_home() / "icons"]
    for base in (os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":"):
        if base:
            roots.append(Path(base) / "icons")
    roots.extend([
        home_dir() / ".icons",
        home_dir() / ".local/share/flatpak/exports/share/icons",
        Path("/var/lib/flatpak/exports/share/icons"),
        Path("/var/lib/snapd/desktop/icons"),
    ])
    return _unique_paths(roots)


def application_roots() -> list[Path]:
    roots = [data_home() / "applications"]
    for base in (os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":"):
        if base:
            roots.append(Path(base) / "applications")
    roots.extend([
        home_dir() / ".local/share/flatpak/exports/share/applications",
        Path("/var/lib/flatpak/exports/share/applications"),
        Path("/var/lib/snapd/desktop/applications"),
    ])
    return _unique_paths(roots)


def read_ini(path: Path) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            parser.read_file(handle)
    except (OSError, configparser.Error):
        pass
    return parser


def read_theme_info(path: Path) -> dict[str, Any] | None:
    index = path / "index.theme"
    if not path.is_dir() or not index.is_file():
        return None
    parser = read_ini(index)
    section = parser["Icon Theme"] if parser.has_section("Icon Theme") else {}
    name = path.name
    label = section.get("Name", name)
    comment = section.get("Comment", "")
    inherits = [entry.strip() for entry in section.get("Inherits", "").split(",") if entry.strip()]
    generated = section.get("X-GlassIcon-Generated", "false").lower() == "true"
    return {
        "name": name,
        "label": label,
        "comment": comment,
        "path": str(path),
        "inherits": inherits,
        "generated": generated,
    }


def discover_icon_themes() -> list[dict[str, Any]]:
    """List available freedesktop icon themes, preferring user copies."""
    themes: dict[str, dict[str, Any]] = {}
    for root in icon_theme_roots():
        if not root.is_dir():
            continue
        try:
            children = sorted(root.iterdir(), key=lambda item: item.name.casefold())
        except OSError:
            continue
        for child in children:
            info = read_theme_info(child)
            if info and info["name"] not in themes:
                themes[info["name"]] = info
    return sorted(themes.values(), key=lambda item: (item["label"].casefold(), item["name"].casefold()))


def _run(args: list[str], timeout: float = 2.5) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(args, check=False, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None


def _value_from_command(args: list[str]) -> str | None:
    result = _run(args)
    if not result or result.returncode != 0:
        return None
    value = result.stdout.strip().strip("\"'")
    return value or None


def _read_theme_from_ini(path: Path, section: str, keys: tuple[str, ...]) -> str | None:
    parser = read_ini(path)
    if not parser.has_section(section):
        return None
    for key in keys:
        value = parser.get(section, key, fallback="").strip().strip("\"'")
        if value:
            return value
    return None


def detect_icon_theme() -> str | None:
    """Detect the current icon theme from the active desktop/session settings."""
    current_desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    session = os.environ.get("DESKTOP_SESSION", "").lower()
    is_kde = "kde" in current_desktop or "plasma" in current_desktop or "plasma" in session
    is_xfce = "xfce" in current_desktop or "xfce" in session
    is_lxqt = "lxqt" in current_desktop or "lxqt" in session
    is_gnome_like = any(name in current_desktop for name in ("gnome", "cinnamon", "mate", "unity"))

    if is_kde:
        value = _read_theme_from_ini(config_home() / "kdeglobals", "Icons", ("Theme",))
        if value:
            return value
    if is_xfce:
        value = _value_from_command(["xfconf-query", "-c", "xsettings", "-p", "/Net/IconThemeName"])
        if value:
            return value
    if is_lxqt:
        value = _read_theme_from_ini(config_home() / "lxqt/lxqt.conf", "General", ("icon_theme", "iconTheme"))
        if value:
            return value
    if is_gnome_like:
        value = _value_from_command(["gsettings", "get", "org.gnome.desktop.interface", "icon-theme"])
        if value:
            return value

    xsettings_path = config_home() / "xsettingsd/xsettingsd.conf"
    if xsettings_path.is_file():
        try:
            content = xsettings_path.read_text(encoding="utf-8", errors="replace")
            match = re.search(r'^\s*Net/IconThemeName\s+["\']([^"\']+)["\']', content, re.MULTILINE)
            if match:
                return match.group(1).strip()
        except OSError:
            pass

    for path in (config_home() / "gtk-3.0/settings.ini", config_home() / "gtk-4.0/settings.ini"):
        value = _read_theme_from_ini(path, "Settings", ("gtk-icon-theme-name",))
        if value:
            return value

    if not is_xfce:
        value = _value_from_command(["xfconf-query", "-c", "xsettings", "-p", "/Net/IconThemeName"])
        if value:
            return value
    if not is_kde:
        value = _read_theme_from_ini(config_home() / "kdeglobals", "Icons", ("Theme",))
        if value:
            return value
    value = _value_from_command(["gsettings", "get", "org.gnome.desktop.interface", "icon-theme"])
    if value and value not in ("default", "hicolor"):
        return value
    return value


def load_state() -> dict[str, Any]:
    path = state_dir() / "state.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    data.setdefault("version", STATE_VERSION)
    data.setdefault("application_overrides", {})
    data.setdefault("system_overrides", {})
    return data


def save_state(state: dict[str, Any]) -> None:
    state["version"] = STATE_VERSION
    state_dir().mkdir(parents=True, exist_ok=True)
    atomic_write(state_dir() / "state.json", json.dumps(state, indent=2, ensure_ascii=False) + "\n")


def atomic_write(path: Path, content: str | bytes, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    previous_mode = mode
    if previous_mode is None and path.exists():
        try:
            previous_mode = path.stat().st_mode & 0o777
        except OSError:
            previous_mode = None
    binary = isinstance(content, bytes)
    fd, temporary = tempfile.mkstemp(prefix="." + path.name + ".", dir=str(path.parent))
    try:
        if binary:
            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
        else:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
                handle.write(content)
        if previous_mode is not None:
            os.chmod(temporary, previous_mode)
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def set_ini_setting(path: Path, section: str, key: str, value: str) -> None:
    """Update one INI key without reserializing or discarding unrelated settings/comments."""
    try:
        original = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        original = ""
    lines = original.splitlines()
    if original and original.endswith("\n"):
        trailing_newline = True
    else:
        trailing_newline = False
    section_header = re.compile(r"^\s*\[([^]]+)\]\s*(?:[;#].*)?$")
    key_pattern = re.compile(r"^\s*" + re.escape(key) + r"\s*=")
    target_section: int | None = None
    next_section: int | None = None
    key_line: int | None = None
    for index, line in enumerate(lines):
        match = section_header.match(line)
        if match:
            if target_section is not None:
                next_section = index
                break
            if match.group(1).strip().casefold() == section.casefold():
                target_section = index
            continue
        if target_section is not None and key_pattern.match(line):
            key_line = index
            break
    if target_section is not None and key_line is not None:
        lines[key_line] = f"{key}={value}"
    elif target_section is not None:
        insertion = next_section if next_section is not None else len(lines)
        lines.insert(insertion, f"{key}={value}")
    else:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend([f"[{section}]", f"{key}={value}"])
    result = "\n".join(lines)
    if trailing_newline or result:
        result += "\n"
    atomic_write(path, result)


def _desktop_parser(path: Path) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            parser.read_file(handle)
    except (OSError, configparser.Error):
        pass
    return parser


def _bool_desktop(value: str) -> bool:
    return value.strip().lower() == "true"


def discover_applications() -> list[dict[str, Any]]:
    """Discover visible .desktop launchers using XDG precedence (user entries first)."""
    found: dict[str, dict[str, Any]] = {}
    overridden_ids = set(load_state().get("application_overrides", {}))
    for root in application_roots():
        if not root.is_dir():
            continue
        for directory, subdirs, filenames in os.walk(root, followlinks=False):
            subdirs[:] = sorted(name for name in subdirs if name not in {".hidden", "__pycache__"})
            for filename in sorted(filenames, key=str.casefold):
                if not filename.endswith(".desktop"):
                    continue
                source = Path(directory) / filename
                try:
                    relative = source.relative_to(root)
                except ValueError:
                    continue
                desktop_id = "-".join(relative.parts)
                if desktop_id in found:
                    continue
                parser = _desktop_parser(source)
                if not parser.has_section("Desktop Entry"):
                    continue
                entry = parser["Desktop Entry"]
                if entry.get("Type", "Application") != "Application":
                    continue
                if _bool_desktop(entry.get("Hidden", "false")) or _bool_desktop(entry.get("NoDisplay", "false")):
                    continue
                name = entry.get("Name", "").strip() or source.stem
                icon = entry.get("Icon", "").strip()
                found[desktop_id] = {
                    "id": desktop_id,
                    "name": name,
                    "icon": icon,
                    "exec": entry.get("Exec", "").strip(),
                    "source_path": str(source),
                    "user_path": str(data_home() / "applications" / desktop_id),
                    "is_user_source": source == data_home() / "applications" / desktop_id,
                    "overridden": desktop_id in overridden_ids,
                }
    return sorted(found.values(), key=lambda item: (item["name"].casefold(), item["id"].casefold()))


def _replace_desktop_icon(content: str, icon_path: str) -> str:
    lines = content.splitlines()
    section_re = re.compile(r"^\s*\[([^]]+)\]\s*$")
    active = False
    key_line: int | None = None
    section_end: int | None = None
    for index, line in enumerate(lines):
        match = section_re.match(line)
        if match:
            if active:
                section_end = index
                break
            active = match.group(1).strip() == "Desktop Entry"
            continue
        if active and re.match(r"^\s*Icon\s*=", line):
            key_line = index
    if key_line is not None:
        lines[key_line] = "Icon=" + icon_path
    elif active and section_end is not None:
        insertion = section_end
        while insertion > 0 and not lines[insertion - 1].strip():
            insertion -= 1
        lines.insert(insertion, "Icon=" + icon_path)
    elif active:
        lines.append("Icon=" + icon_path)
    elif section_end is not None:
        lines.insert(section_end, "Icon=" + icon_path)
    else:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend(["[Desktop Entry]", "Icon=" + icon_path])
    return "\n".join(lines) + "\n"


def _refresh_desktop_database(directory: Path) -> None:
    if shutil.which("update-desktop-database"):
        _run(["update-desktop-database", str(directory)], timeout=5.0)


def set_application_icon(desktop_id: str, icon_path: str | Path) -> Path:
    """Create/update a user-local launcher override; never edits /usr/share."""
    chosen = Path(icon_path).expanduser()
    if not chosen.is_file():
        raise FileNotFoundError(f"Icon file does not exist: {chosen}")
    if chosen.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
        raise ValueError("Choose an SVG, SVGZ, PNG, or XPM image.")
    app = next((entry for entry in discover_applications() if entry["id"] == desktop_id), None)
    if not app:
        raise ValueError(f"Desktop entry not found: {desktop_id}")

    destination = data_home() / "applications" / desktop_id
    state = load_state()
    overrides = state.setdefault("application_overrides", {})
    if desktop_id not in overrides:
        had_original = destination.is_file()
        backup_path = state_dir() / "backups/apps" / (desktop_id.replace("/", "_") + ".desktop")
        if had_original:
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(destination, backup_path)
        overrides[desktop_id] = {
            "had_original_user_file": had_original,
            "backup_path": str(backup_path) if had_original else "",
        }
    source = destination if destination.is_file() else Path(app["source_path"])
    try:
        source_content = source.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise OSError(f"Unable to read launcher {source}: {exc}") from exc
    updated = _replace_desktop_icon(source_content, str(chosen.resolve()))
    atomic_write(destination, updated, mode=0o644)
    save_state(state)
    _refresh_desktop_database(destination.parent)
    return destination


def reset_application_icon(desktop_id: str) -> bool:
    state = load_state()
    overrides = state.setdefault("application_overrides", {})
    record = overrides.get(desktop_id)
    if not record:
        return False
    destination = data_home() / "applications" / desktop_id
    if record.get("had_original_user_file"):
        backup = Path(record.get("backup_path", ""))
        if not backup.is_file():
            raise FileNotFoundError(f"Saved launcher backup is missing: {backup}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup, destination)
        backup.unlink(missing_ok=True)
    else:
        destination.unlink(missing_ok=True)
    overrides.pop(desktop_id, None)
    save_state(state)
    _refresh_desktop_database(destination.parent)
    return True


def reset_all_application_icons() -> int:
    state = load_state()
    ids = list(state.setdefault("application_overrides", {}))
    changed = 0
    for desktop_id in ids:
        try:
            changed += int(reset_application_icon(desktop_id))
        except OSError:
            continue
    return changed


def _get_theme_original(state: dict[str, Any]) -> str | None:
    value = state.get("original_theme")
    return value if isinstance(value, str) and value else None


def apply_icon_theme(theme_name: str, remember_original: bool = True) -> dict[str, Any]:
    """Set the user's icon theme across common desktop settings and GTK toolkits."""
    theme_name = (theme_name or "").strip()
    if not theme_name or "/" in theme_name or "\x00" in theme_name:
        raise ValueError("Choose a valid icon theme from the installed theme list.")
    themes = {theme["name"] for theme in discover_icon_themes()}
    if theme_name not in themes:
        raise ValueError(f"Icon theme '{theme_name}' was not found on this system.")

    state = load_state()
    current = detect_icon_theme()
    if remember_original and not _get_theme_original(state) and current and current != theme_name:
        state["original_theme"] = current

    requested_theme = theme_name
    overlay_name = state.get("overlay_theme")
    overlay_dir = data_home() / "icons" / overlay_name if overlay_name else None
    if (overlay_name and theme_name != overlay_name and state.get("system_overrides")
            and overlay_dir and _is_generated_overlay(overlay_dir)):
        # Preserve custom folder/file roles when the user changes the underlying icon pack.
        state["base_theme"] = theme_name
        _write_overlay_index(overlay_dir, overlay_name, theme_name)
        theme_name = overlay_name
    state["active_theme"] = theme_name
    save_state(state)

    written: list[str] = []
    warnings: list[str] = []
    current_desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    session = os.environ.get("DESKTOP_SESSION", "").lower()
    is_kde = "kde" in current_desktop or "plasma" in current_desktop or "plasma" in session
    is_lxqt = "lxqt" in current_desktop or "lxqt" in session

    gsettings_result = _run(["gsettings", "set", "org.gnome.desktop.interface", "icon-theme", theme_name])
    if gsettings_result and gsettings_result.returncode == 0:
        written.append("GNOME/Cinnamon/MATE settings (gsettings)")

    xfconf = shutil.which("xfconf-query")
    if xfconf:
        exists = _run([xfconf, "-c", "xsettings", "-p", "/Net/IconThemeName"])
        if exists and exists.returncode == 0:
            changed = _run([xfconf, "-c", "xsettings", "-p", "/Net/IconThemeName", "-s", theme_name])
        else:
            changed = _run([xfconf, "-c", "xsettings", "-p", "/Net/IconThemeName", "--create", "-t", "string", "-s", theme_name])
        if changed and changed.returncode == 0:
            written.append("Xfce/XSettings (xfconf)")

    kwriteconfig = shutil.which("kwriteconfig6") or shutil.which("kwriteconfig5")
    if kwriteconfig:
        result = _run([kwriteconfig, "--file", "kdeglobals", "--group", "Icons", "--key", "Theme", theme_name])
        if result and result.returncode == 0:
            written.append("KDE Plasma (kdeglobals)")
    elif is_kde:
        set_ini_setting(config_home() / "kdeglobals", "Icons", "Theme", theme_name)
        written.append("KDE Plasma configuration file")

    for version in ("gtk-3.0", "gtk-4.0"):
        settings_path = config_home() / version / "settings.ini"
        set_ini_setting(settings_path, "Settings", "gtk-icon-theme-name", theme_name)
        written.append(f"GTK {version.removeprefix('gtk-')} user settings")

    xsettings_path = config_home() / "xsettingsd/xsettingsd.conf"
    if xsettings_path.is_file() or shutil.which("xsettingsd"):
        try:
            original = xsettings_path.read_text(encoding="utf-8", errors="replace") if xsettings_path.is_file() else ""
        except OSError:
            original = ""
        lines = original.splitlines()
        setting = f'Net/IconThemeName "{theme_name}"'
        matched = False
        for index, line in enumerate(lines):
            if re.match(r"^\s*Net/IconThemeName\s+", line):
                lines[index] = setting
                matched = True
                break
        if not matched:
            lines.append(setting)
        atomic_write(xsettings_path, "\n".join(lines).rstrip() + "\n")
        written.append("xsettingsd")

    lxqt_path = config_home() / "lxqt/lxqt.conf"
    if lxqt_path.is_file() or is_lxqt:
        set_ini_setting(lxqt_path, "General", "icon_theme", theme_name)
        written.append("LXQt settings")

    if not written:
        warnings.append("Only GTK 3/4 user settings files were updated; no live desktop settings utility was available.")
    return {"theme": theme_name, "base_theme": requested_theme if theme_name != requested_theme else state.get("base_theme", theme_name),
            "written": written, "warnings": warnings}


def restore_original_icon_theme() -> dict[str, Any] | None:
    state = load_state()
    original = _get_theme_original(state)
    if not original:
        return None
    # Remove only GlassIcon-generated system overrides; app launcher customizations are separate.
    state = load_state()
    base = state.get("base_theme") or original
    overlay = state.get("overlay_theme")
    overlay_path = data_home() / "icons" / overlay if overlay else None
    if overlay_path and _is_generated_overlay(overlay_path):
        shutil.rmtree(overlay_path, ignore_errors=True)
    state["system_overrides"] = {}
    state.pop("overlay_theme", None)
    state.pop("base_theme", None)
    state.pop("original_theme", None)
    state["active_theme"] = original
    save_state(state)
    if any(theme["name"] == original for theme in discover_icon_themes()):
        return apply_icon_theme(original, remember_original=False)
    if any(theme["name"] == base for theme in discover_icon_themes()):
        return apply_icon_theme(base, remember_original=False)
    return None


def _is_generated_overlay(path: Path) -> bool:
    info = read_theme_info(path)
    return bool(info and info.get("generated"))


def _safe_theme_dir(base_name: str) -> tuple[str, Path]:
    root = data_home() / "icons"
    root.mkdir(parents=True, exist_ok=True)
    candidate = root / base_name
    if not candidate.exists() or _is_generated_overlay(candidate):
        return base_name, candidate
    suffix = "GlassDock"
    candidate_name = f"{base_name}-{suffix}"
    candidate = root / candidate_name
    index = 2
    while candidate.exists() and not _is_generated_overlay(candidate):
        candidate_name = f"{base_name}-{suffix}-{index}"
        candidate = root / candidate_name
        index += 1
    return candidate_name, candidate


def _write_overlay_index(theme_dir: Path, theme_name: str, base_theme: str) -> None:
    directory_entries = [
        ("48x48/places", "Places", 48, "Fixed"),
        ("scalable/places", "Places", 48, "Scalable"),
        ("48x48/devices", "Devices", 48, "Fixed"),
        ("scalable/devices", "Devices", 48, "Scalable"),
        ("48x48/mimetypes", "MimeTypes", 48, "Fixed"),
        ("scalable/mimetypes", "MimeTypes", 48, "Scalable"),
    ]
    inherits = [base_theme] if base_theme and base_theme != theme_name else []
    if "hicolor" not in inherits and theme_name != "hicolor":
        inherits.append("hicolor")
    lines = [
        "[Icon Theme]",
        f"Name={theme_name}",
        "Comment=Per-user icon overrides managed by GlassIcon Studio",
        "Inherits=" + ",".join(inherits),
        "Directories=" + ",".join(item[0] for item in directory_entries),
        "X-GlassIcon-Generated=true",
        "",
    ]
    for directory, context, size, kind in directory_entries:
        lines.extend([
            f"[{directory}]",
            f"Size={size}",
            f"Context={context}",
            f"Type={kind}",
            "",
        ])
    atomic_write(theme_dir / "index.theme", "\n".join(lines))


def set_system_icon(icon_name: str, image_path: str | Path) -> dict[str, Any]:
    role = ROLE_BY_NAME.get(icon_name)
    if not role:
        raise ValueError("Choose a supported system icon role.")
    source = Path(image_path).expanduser()
    if not source.is_file():
        raise FileNotFoundError(f"Icon file does not exist: {source}")
    extension = source.suffix.lower()
    if extension not in SUPPORTED_IMAGE_EXTENSIONS:
        raise ValueError("Choose an SVG, SVGZ, PNG, or XPM image.")

    state = load_state()
    current = detect_icon_theme()
    previous_overlay = state.get("overlay_theme")
    if previous_overlay and current == previous_overlay and state.get("base_theme"):
        base_theme = state["base_theme"]
        overlay_name = previous_overlay
        overlay_dir = data_home() / "icons" / overlay_name
        if not _is_generated_overlay(overlay_dir):
            overlay_name, overlay_dir = _safe_theme_dir("GlassIcon-Overrides")
    else:
        base_theme = current or "hicolor"
        overlay_name, overlay_dir = _safe_theme_dir("GlassIcon-Overrides")

    overlay_dir.mkdir(parents=True, exist_ok=True)
    _write_overlay_index(overlay_dir, overlay_name, base_theme)
    context = role["context"]
    target_dir = overlay_dir / ("scalable" if extension in {".svg", ".svgz"} else "48x48") / context
    target_dir.mkdir(parents=True, exist_ok=True)
    for stale in target_dir.glob(icon_name + ".*"):
        if stale.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS:
            stale.unlink(missing_ok=True)
    target = target_dir / (icon_name + extension)
    shutil.copy2(source, target)

    state.setdefault("system_overrides", {})[icon_name] = {
        "label": role["label"],
        "name": icon_name,
        "context": context,
        "source": str(source.resolve()),
        "installed_path": str(target),
    }
    state["overlay_theme"] = overlay_name
    state["base_theme"] = base_theme
    save_state(state)
    result = apply_icon_theme(overlay_name, remember_original=True)
    result["base_theme"] = base_theme
    result["installed_path"] = str(target)
    return result


def reset_system_icon(icon_name: str) -> bool:
    state = load_state()
    overrides = state.setdefault("system_overrides", {})
    record = overrides.pop(icon_name, None)
    if not record:
        return False
    installed = Path(record.get("installed_path", ""))
    if installed.is_file():
        installed.unlink(missing_ok=True)
    save_state(state)
    remaining = state.get("system_overrides", {})
    overlay_name = state.get("overlay_theme")
    overlay_dir = data_home() / "icons" / overlay_name if overlay_name else None
    if remaining and overlay_dir and _is_generated_overlay(overlay_dir):
        _write_overlay_index(overlay_dir, overlay_name, state.get("base_theme") or "hicolor")
        active = detect_icon_theme()
        if active != overlay_name:
            apply_icon_theme(overlay_name, remember_original=False)
    elif overlay_dir and _is_generated_overlay(overlay_dir):
        shutil.rmtree(overlay_dir, ignore_errors=True)
        base = state.get("base_theme") or "hicolor"
        state.pop("overlay_theme", None)
        state.pop("base_theme", None)
        save_state(state)
        if any(theme["name"] == base for theme in discover_icon_themes()):
            apply_icon_theme(base, remember_original=False)
    return True


def reset_all_system_icons() -> int:
    state = load_state()
    names = list(state.setdefault("system_overrides", {}))
    removed = 0
    for name in names:
        try:
            removed += int(reset_system_icon(name))
        except OSError:
            continue
    return removed



MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
MAX_EXTRACTED_BYTES = 1024 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 100_000


def _archive_path(staging: Path, name: str) -> Path:
    if "\\" in name:
        raise ValueError("Archive contains a path with a backslash; refusing an ambiguous path.")
    raw_parts = name.split("/")
    if name.startswith("/") or any(part == ".." for part in raw_parts):
        raise ValueError(f"Unsafe path in icon theme archive: {name}")
    pure = PurePosixPath(name)
    if pure.is_absolute() or not pure.parts:
        raise ValueError(f"Unsafe path in icon theme archive: {name}")
    destination = staging.joinpath(*pure.parts)
    if not destination.resolve().is_relative_to(staging.resolve()):
        raise ValueError(f"Path escapes the extraction directory: {name}")
    return destination


def _archive_symlink_target(staging: Path, link_path: Path, name: str) -> Path:
    if not name or name.startswith("/") or "\\" in name:
        raise ValueError("Icon theme archive contains an absolute or invalid symbolic link.")
    link_relative = link_path.relative_to(staging).as_posix()
    normalized = posixpath.normpath(posixpath.join(posixpath.dirname(link_relative), name))
    if normalized in ("", ".", "..") or normalized.startswith("../") or normalized.startswith("/"):
        raise ValueError("Icon theme archive contains a symbolic link escaping the theme folder.")
    target = staging.joinpath(*PurePosixPath(normalized).parts)
    if not target.resolve().is_relative_to(staging.resolve()):
        raise ValueError("Icon theme archive contains a symbolic link escaping the theme folder.")
    return target


def _safe_extract_archive(archive: Path, staging: Path) -> None:
    if archive.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("The icon theme archive is over 256 MiB; unpack it yourself and import the theme folder.")
    symlinks: list[tuple[Path, str]] = []
    seen: set[str] = set()
    total_bytes = 0
    count = 0

    def reserve(name: str, size: int = 0) -> Path:
        nonlocal total_bytes, count
        count += 1
        total_bytes += max(0, size)
        if count > MAX_ARCHIVE_ENTRIES:
            raise ValueError("The archive contains too many entries to install safely.")
        if total_bytes > MAX_EXTRACTED_BYTES:
            raise ValueError("The unpacked theme would exceed 1 GiB; installation was stopped.")
        path = _archive_path(staging, name.rstrip("/"))
        key = path.relative_to(staging).as_posix()
        if key in seen:
            raise ValueError(f"Archive contains duplicate paths: {name}")
        seen.add(key)
        return path

    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as bundle:
            infos = bundle.infolist()
            if len(infos) > MAX_ARCHIVE_ENTRIES:
                raise ValueError("The archive contains too many entries to install safely.")
            for info in infos:
                if info.filename.rstrip("/") in ("", "."):
                    continue
                mode = (info.external_attr >> 16) & 0o170000
                path = reserve(info.filename, info.file_size)
                if info.is_dir():
                    path.mkdir(parents=True, exist_ok=True)
                    continue
                if mode == stat.S_IFLNK:
                    link_name = bundle.read(info).decode("utf-8", errors="strict")
                    symlinks.append((path, link_name))
                    continue
                if mode not in (0, stat.S_IFREG):
                    raise ValueError(f"Archive contains an unsupported special file: {info.filename}")
                path.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(info) as source, path.open("xb") as destination:
                    shutil.copyfileobj(source, destination, length=1024 * 1024)
    else:
        try:
            bundle = tarfile.open(archive, mode="r:*")
        except (tarfile.TarError, OSError) as exc:
            raise ValueError("Choose a ZIP, TAR, TAR.GZ, TAR.BZ2, or TAR.XZ icon theme archive.") from exc
        with bundle:
            members = bundle.getmembers()
            if len(members) > MAX_ARCHIVE_ENTRIES:
                raise ValueError("The archive contains too many entries to install safely.")
            regulars: list[tuple[tarfile.TarInfo, Path]] = []
            for member in members:
                if member.name.rstrip("/") in ("", "."):
                    continue
                path = reserve(member.name, member.size if member.isfile() else 0)
                if member.isdir():
                    path.mkdir(parents=True, exist_ok=True)
                elif member.isfile():
                    regulars.append((member, path))
                elif member.issym():
                    symlinks.append((path, member.linkname))
                else:
                    raise ValueError(f"Archive contains an unsupported special file: {member.name}")
            for member, path in regulars:
                path.parent.mkdir(parents=True, exist_ok=True)
                source = bundle.extractfile(member)
                if source is None:
                    raise ValueError(f"Unable to read archive entry: {member.name}")
                with source, path.open("xb") as destination:
                    shutil.copyfileobj(source, destination, length=1024 * 1024)

    for link, link_name in symlinks:
        if link.exists() or link.is_symlink():
            raise ValueError("Archive has a symbolic link that collides with another entry.")
        target = _archive_symlink_target(staging, link, link_name)
        link.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(os.path.relpath(target, link.parent), link)
    for link, _link_name in symlinks:
        try:
            target = link.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise ValueError("Archive contains a broken or cyclic symbolic link.") from exc
        if not target.is_relative_to(staging.resolve()) or not target.is_file():
            raise ValueError("Archive contains a symbolic link that does not point to an internal icon file.")


def _validate_theme_tree(source: Path) -> None:
    if not read_theme_info(source):
        raise ValueError(f"No valid index.theme was found in {source}.")
    resolved_source = source.resolve()
    for directory, subdirs, filenames in os.walk(source, followlinks=False):
        parent = Path(directory)
        for name in list(subdirs):
            child = parent / name
            if child.is_symlink():
                raise ValueError("This theme uses a symbolic link for a directory; import a standard icon-theme archive instead.")
        for name in filenames:
            child = parent / name
            if child.is_symlink():
                try:
                    link_target = os.readlink(child)
                    resolved = child.resolve(strict=True)
                except (OSError, RuntimeError) as exc:
                    raise ValueError("Theme contains a broken symbolic link; it was not imported.") from exc
                if os.path.isabs(link_target) or not resolved.is_relative_to(resolved_source) or not resolved.is_file():
                    raise ValueError("Theme contains a broken or external symbolic link; it was not imported.")


def _available_theme_folder_name(preferred: str) -> str:
    preferred = re.sub(r"[^A-Za-z0-9_. -]+", "-", preferred).strip(" .-") or "Imported-Icon-Theme"
    preferred = preferred.replace(" ", "-")
    existing = {theme["name"] for theme in discover_icon_themes()}
    candidate = preferred
    suffix = 2
    while candidate in existing or (data_home() / "icons" / candidate).exists():
        candidate = f"{preferred}-GlassIcon" if suffix == 2 else f"{preferred}-GlassIcon-{suffix}"
        suffix += 1
    return candidate


def install_icon_theme(source_path: str | Path) -> list[dict[str, str]]:
    """Import an icon theme directory or archive safely into the current user's icon folder."""
    source = Path(source_path).expanduser()
    if not source.exists():
        raise FileNotFoundError(f"Theme source does not exist: {source}")
    icon_root = data_home() / "icons"
    icon_root.mkdir(parents=True, exist_ok=True)
    installed: list[dict[str, str]] = []

    def import_tree(theme_source: Path) -> None:
        _validate_theme_tree(theme_source)
        info = read_theme_info(theme_source) or {}
        display_label = str(info.get("label") or theme_source.name)
        desired = display_label if theme_source.name.startswith(".glassicon-import-") else theme_source.name
        target_name = _available_theme_folder_name(desired)
        target = icon_root / target_name
        shutil.copytree(theme_source, target, symlinks=False)
        # Make the actual theme ID visible in the index while preserving the theme's label.
        index_path = target / "index.theme"
        try:
            text = index_path.read_text(encoding="utf-8", errors="replace")
            text = re.sub(r"(?m)^Name\s*=.*$", "Name=" + display_label, text, count=1)
            atomic_write(index_path, text)
        except OSError:
            shutil.rmtree(target, ignore_errors=True)
            raise
        installed.append({"name": target_name, "label": display_label, "path": str(target)})

    if source.is_dir():
        if read_theme_info(source):
            import_tree(source)
        else:
            candidates = sorted((path.parent for path in source.rglob("index.theme") if path.is_file()), key=lambda path: (len(path.parts), str(path)))
            unique: list[Path] = []
            for candidate in candidates:
                if not any(candidate == existing for existing in unique):
                    unique.append(candidate)
            if not unique:
                raise ValueError("This folder does not contain an index.theme icon theme.")
            for candidate in unique:
                import_tree(candidate)
        return installed

    if not source.is_file():
        raise ValueError("Choose an icon theme folder or an archive file.")
    with tempfile.TemporaryDirectory(prefix=".glassicon-import-", dir=icon_root) as temporary:
        staging = Path(temporary)
        _safe_extract_archive(source, staging)
        candidates = sorted((path.parent for path in staging.rglob("index.theme") if path.is_file()), key=lambda path: (len(path.parts), str(path)))
        unique = []
        for candidate in candidates:
            if not any(candidate == existing for existing in unique):
                unique.append(candidate)
        if not unique:
            raise ValueError("No valid icon theme (with index.theme) was found in this archive.")
        for candidate in unique:
            import_tree(candidate)
    return installed

def open_directory(path: Path) -> bool:
    path.mkdir(parents=True, exist_ok=True)
    opener = shutil.which("xdg-open") or shutil.which("gio")
    if not opener:
        return False
    args = [opener, "open", str(path)] if Path(opener).name == "gio" else [opener, str(path)]
    try:
        subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return True
    except OSError:
        return False


def desktop_environment_label() -> str:
    current = os.environ.get("XDG_CURRENT_DESKTOP", "").strip()
    session = os.environ.get("DESKTOP_SESSION", "").strip()
    wm = os.environ.get("XDG_SESSION_TYPE", "").strip()
    label = current or session or "Standalone window manager"
    if wm:
        label += f" · {wm}"
    return label
