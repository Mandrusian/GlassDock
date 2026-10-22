"""GTK-free icon discovery shared by the dock and the settings app.

Gtk.IconTheme only knows the directories GTK was told about. Icons that live
in Flatpak/Snap exports, ~/.icons, /usr/share/pixmaps, or that are referenced
by a slightly different name (case, spaces, reverse-DNS prefixes, StartupWMClass,
the executable name...) used to end up as a letter tile. This module builds a
small index of every app icon on disk and produces candidate names to try.
"""
import os
import re
import time

from .desktop import exec_basename

EXTS = (".svg", ".png", ".xpm", ".svgz")
RETRY_SECONDS = 30.0
_SKIP_DIRS = {"symbolic", "cursors", "status", "actions", "devices", "emblems", "mimetypes",
              "places", "panel", "categories", "animations", "emotes", "intl", "stock"}
_state = {"index": None, "built": 0.0, "env": None}


def _bases(env):
    home = env.get("HOME", os.path.expanduser("~"))
    data_home = env.get("XDG_DATA_HOME") or os.path.join(home, ".local", "share")
    data_dirs = (env.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":")
    bases = [data_home] + [d for d in data_dirs if d]
    bases += [os.path.join(home, ".local", "share", "flatpak", "exports", "share"),
              "/var/lib/flatpak/exports/share", "/var/lib/snapd/desktop",
              "/usr/local/share", "/usr/share"]
    out = []
    for b in bases:
        if b not in out:
            out.append(b)
    return home, out


def icon_roots(env=None):
    """Return (icon_theme_roots, pixmap_dirs)."""
    env = os.environ if env is None else env
    home, bases = _bases(env)
    roots, pix = [], []
    for b in bases:
        p = os.path.join(b, "icons")
        if p not in roots:
            roots.append(p)
        p = os.path.join(b, "pixmaps")
        if p not in pix:
            pix.append(p)
    roots.append(os.path.join(home, ".icons"))
    return roots, pix


def strip_ext(name):
    low = name.lower()
    for ext in EXTS:
        if low.endswith(ext):
            return name[:-len(ext)]
    return name


def _size_of(path):
    if "scalable" in path or path.lower().endswith((".svg", ".svgz")):
        return 4096
    m = re.search(r"(\d+)x\d+", path)
    return int(m.group(1)) if m else 0


def build_index(env=None):
    """Map lower-case icon name -> list of (score, path)."""
    roots, pix = icon_roots(env)
    index = {}

    def add(path, filename, bonus):
        stem, ext = os.path.splitext(filename)
        if ext.lower() not in EXTS or stem.endswith("-symbolic"):
            return
        index.setdefault(stem.lower(), []).append(((bonus, _size_of(path)), path))

    for root in roots:
        if not os.path.isdir(root):
            continue
        for dirpath, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d.lower() not in _SKIP_DIRS]
            leaf = os.path.basename(dirpath)
            if leaf == "apps" or dirpath == root:
                for f in files:
                    add(os.path.join(dirpath, f), f, 2)
    for d in pix:
        if os.path.isdir(d):
            for f in os.listdir(d):
                full = os.path.join(d, f)
                if os.path.isfile(full):
                    add(full, f, 1)
    return index


def _get_index(env=None, force=False):
    if force or _state["index"] is None:
        _state["index"] = build_index(env)
        _state["built"] = time.monotonic()
    return _state["index"]


def find_icon_file(name, env=None):
    """Return the path of the best image file for an icon name, or None."""
    name = (name or "").strip()
    if not name:
        return None
    if os.path.isabs(name):
        if os.path.exists(name):
            return name
        name = os.path.basename(name)
    key = strip_ext(name).lower()
    for attempt in (0, 1):
        hits = _get_index(env).get(key)
        if hits:
            return max(hits, key=lambda h: h[0])[1]
        # a freshly installed app may not be indexed yet: rebuild, but rarely
        if attempt == 0 and time.monotonic() - _state["built"] > RETRY_SECONDS:
            _get_index(env, force=True)
        else:
            break
    return None


def _variants(value):
    value = (value or "").strip()
    if not value:
        return []
    if os.path.isabs(value):
        return [value]
    value = strip_ext(value)
    out = [value]
    low = value.lower()
    if low not in out:
        out.append(low)
    dashed = low.replace(" ", "-").replace("_", "-")
    if dashed not in out:
        out.append(dashed)
    if "." in low:
        last = low.rsplit(".", 1)[-1]
        if len(last) > 2 and last not in out:
            out.append(last)
    return out


def candidate_names(icon="", entry=None, windows=(), name=""):
    """Every plausible icon name for an item, best guess first."""
    out = []

    def add(v):
        for x in _variants(v):
            if x not in out:
                out.append(x)

    add(icon)
    if entry is not None:
        add(getattr(entry, "icon", ""))
        add(os.path.splitext(getattr(entry, "id", "") or "")[0])
        add(getattr(entry, "startup_wm_class", ""))
        add(exec_basename(getattr(entry, "exec", "") or ""))
    for w in windows or ():
        add(getattr(w, "app_id", ""))
        add(getattr(w, "wm_class", ""))
    add(name)
    return out
