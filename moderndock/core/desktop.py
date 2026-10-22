"""freedesktop.org desktop entry parsing, discovery and Exec expansion."""
import os
import shlex
from dataclasses import dataclass, field


@dataclass
class DesktopAction:
    id: str
    name: str
    exec: str
    icon: str = ""


@dataclass
class DesktopEntry:
    id: str                      # desktop file id, e.g. "org.mozilla.firefox.desktop"
    path: str
    name: str
    generic_name: str = ""
    comment: str = ""
    icon: str = ""
    exec: str = ""
    terminal: bool = False
    no_display: bool = False
    hidden: bool = False
    startup_wm_class: str = ""
    categories: list = field(default_factory=list)
    actions: list = field(default_factory=list)
    only_show_in: list = field(default_factory=list)
    not_show_in: list = field(default_factory=list)


# ----------------------------------------------------------------- locale

def locale_candidates(lang=None):
    """Return localized-key suffixes in priority order, e.g. for de_DE.UTF-8@euro:
    ['de_DE@euro', 'de_DE', 'de@euro', 'de']."""
    if lang is None:
        lang = (os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES")
                or os.environ.get("LANG") or "")
    lang = lang.split(":")[0]
    if not lang or lang in ("C", "POSIX"):
        return []
    modifier = ""
    if "@" in lang:
        lang, modifier = lang.split("@", 1)
    if "." in lang:
        lang = lang.split(".", 1)[0]
    country = ""
    if "_" in lang:
        lang, country = lang.split("_", 1)
    out = []
    if country and modifier:
        out.append("%s_%s@%s" % (lang, country, modifier))
    if country:
        out.append("%s_%s" % (lang, country))
    if modifier:
        out.append("%s@%s" % (lang, modifier))
    out.append(lang)
    return out


# ----------------------------------------------------------------- parsing

def _unescape(value):
    if "\\" not in value:
        return value
    out = []
    i = 0
    while i < len(value):
        ch = value[i]
        if ch == "\\" and i + 1 < len(value):
            nxt = value[i + 1]
            mapping = {"s": " ", "n": "\n", "t": "\t", "r": "\r", "\\": "\\"}
            if nxt in mapping:
                out.append(mapping[nxt])
                i += 2
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def _split_list(value):
    parts = []
    cur = []
    i = 0
    while i < len(value):
        ch = value[i]
        if ch == "\\" and i + 1 < len(value) and value[i + 1] == ";":
            cur.append(";")
            i += 2
            continue
        if ch == ";":
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
        i += 1
    if cur:
        parts.append("".join(cur))
    return [p for p in parts if p]


def _parse_groups(text):
    groups = {}
    order = []
    current = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1]
            if current not in groups:
                groups[current] = {}
                order.append(current)
            continue
        if current is None or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        if key not in groups[current]:
            groups[current][key] = val.strip()
    return groups, order


def _localized(group, key, locales):
    for loc in locales:
        v = group.get("%s[%s]" % (key, loc))
        if v:
            return _unescape(v)
    return _unescape(group.get(key, ""))


def parse_desktop_text(text, entry_id, path="", locales=None):
    """Parse desktop entry text. Returns None if it is not a usable Application."""
    if locales is None:
        locales = locale_candidates()
    groups, order = _parse_groups(text)
    main = groups.get("Desktop Entry")
    if not main:
        return None
    if main.get("Type", "Application") != "Application":
        return None
    name = _localized(main, "Name", locales)
    if not name:
        return None
    entry = DesktopEntry(
        id=entry_id,
        path=path,
        name=name,
        generic_name=_localized(main, "GenericName", locales),
        comment=_localized(main, "Comment", locales),
        icon=_unescape(main.get("Icon", "")),
        exec=main.get("Exec", ""),
        terminal=main.get("Terminal", "false").lower() == "true",
        no_display=main.get("NoDisplay", "false").lower() == "true",
        hidden=main.get("Hidden", "false").lower() == "true",
        startup_wm_class=main.get("StartupWMClass", ""),
        categories=_split_list(main.get("Categories", "")),
        only_show_in=_split_list(main.get("OnlyShowIn", "")),
        not_show_in=_split_list(main.get("NotShowIn", "")),
    )
    for aid in _split_list(main.get("Actions", "")):
        g = groups.get("Desktop Action %s" % aid)
        if not g or not g.get("Exec"):
            continue
        entry.actions.append(DesktopAction(
            id=aid,
            name=_localized(g, "Name", locales) or aid,
            exec=g["Exec"],
            icon=_unescape(g.get("Icon", "")),
        ))
    return entry


def parse_desktop_file(path, entry_id=None, locales=None):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return None
    if entry_id is None:
        entry_id = os.path.basename(path)
    return parse_desktop_text(text, entry_id, path, locales)


# --------------------------------------------------------------- discovery

def application_dirs(env=None):
    env = os.environ if env is None else env
    home = env.get("HOME", os.path.expanduser("~"))
    data_home = env.get("XDG_DATA_HOME") or os.path.join(home, ".local", "share")
    data_dirs = env.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    dirs = [data_home]
    dirs += [d for d in data_dirs.split(":") if d]
    # Flatpak exports (usually already in XDG_DATA_DIRS, harmless if repeated)
    dirs += [os.path.join(home, ".local", "share", "flatpak", "exports", "share"),
             "/var/lib/flatpak/exports/share"]
    seen = []
    for d in dirs:
        p = os.path.join(d, "applications")
        if p not in seen:
            seen.append(p)
    return seen


def _desktop_id(base, path):
    rel = os.path.relpath(path, base)
    return rel.replace(os.sep, "-")


def load_entries(dirs=None, locales=None, desktop_names=None):
    """Return dict id -> DesktopEntry. Earlier directories win (user overrides).
    Hidden=true entries are removed; NoDisplay entries are kept (they can
    still own windows) but flagged."""
    if dirs is None:
        dirs = application_dirs()
    if desktop_names is None:
        desktop_names = [n for n in os.environ.get("XDG_CURRENT_DESKTOP", "").split(":") if n]
    entries = {}
    hidden_ids = set()
    for base in dirs:
        if not os.path.isdir(base):
            continue
        for root, _dirs, files in os.walk(base):
            for fn in files:
                if not fn.endswith(".desktop"):
                    continue
                path = os.path.join(root, fn)
                eid = _desktop_id(base, path)
                if eid in entries or eid in hidden_ids:
                    continue
                entry = parse_desktop_file(path, eid, locales)
                if entry is None:
                    continue
                if entry.hidden:
                    hidden_ids.add(eid)
                    continue
                entries[eid] = entry
    return entries


def is_launchable(entry, desktop_names=()):
    if entry.no_display or entry.hidden or not entry.exec:
        return False
    if entry.only_show_in and desktop_names and not set(entry.only_show_in) & set(desktop_names):
        return False
    if desktop_names and set(entry.not_show_in) & set(desktop_names):
        return False
    return True


def find_entry(entries, desktop_id):
    if desktop_id in entries:
        return entries[desktop_id]
    if not desktop_id.endswith(".desktop") and desktop_id + ".desktop" in entries:
        return entries[desktop_id + ".desktop"]
    return None


# ------------------------------------------------------------ Exec expansion

def expand_exec(exec_line, entry=None, files=()):
    """Expand a desktop-entry Exec line into an argv list.

    %f/%u take the first file/URL, %F/%U all of them, %i expands to
    '--icon NAME', %c to the name, %k to the file path, %% to '%'.
    Deprecated codes are removed."""
    try:
        tokens = shlex.split(exec_line)
    except ValueError:
        tokens = exec_line.split()
    files = list(files)
    out = []
    for tok in tokens:
        if tok in ("%F", "%U"):
            out.extend(files)
            continue
        if tok == "%i":
            if entry is not None and entry.icon:
                out.extend(["--icon", entry.icon])
            continue
        if tok in ("%f", "%u"):
            if files:
                out.append(files[0])
            continue
        if tok in ("%d", "%D", "%n", "%N", "%v", "%m"):
            continue
        res = []
        i = 0
        while i < len(tok):
            ch = tok[i]
            if ch == "%" and i + 1 < len(tok):
                code = tok[i + 1]
                if code == "%":
                    res.append("%")
                elif code in "fF" or code in "uU":
                    res.append(files[0] if files else "")
                elif code == "c":
                    res.append(entry.name if entry else "")
                elif code == "k":
                    res.append(entry.path if entry else "")
                elif code == "i":
                    res.append(entry.icon if entry else "")
                elif code in "dDnNvm":
                    pass
                else:
                    res.append("%" + code)
                i += 2
                continue
            res.append(ch)
            i += 1
        out.append("".join(res))
    return [os.path.expanduser(a) if a.startswith("~") else a for a in out]


def exec_basename(exec_line):
    """Best-effort name of the real program in an Exec line, skipping env
    and flatpak wrappers."""
    try:
        argv = shlex.split(exec_line)
    except ValueError:
        argv = exec_line.split()
    argv = [a for a in argv if not a.startswith("%")]
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "env":
            i += 1
            while i < len(argv) and "=" in argv[i]:
                i += 1
            continue
        if "=" in a and not a.startswith("/") and not a.startswith("-"):
            i += 1
            continue
        if os.path.basename(a) == "flatpak" and "run" in argv[i:]:
            j = argv.index("run", i) + 1
            while j < len(argv) and argv[j].startswith("-"):
                j += 1
            return argv[j].lower() if j < len(argv) else "flatpak"
        return os.path.basename(a).lower()
    return ""
