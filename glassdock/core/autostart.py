"""Decide whether the dock should start in the current session.

`bin/glassdock --autostart` runs this first; exit status 0 = start, 1 = do not.
GTK-free so it is fast and unit-testable.
"""
import os
import re
import sys

from . import config as C

ALIASES = {"swayfx": "sway", "i3wm": "i3", "plasma": "kde", "plasmawayland": "kde",
           "hypr": "hyprland", "gnome-wayland": "gnome", "gnome-xorg": "gnome"}


def _norm(name):
    name = name.strip().lower()
    return ALIASES.get(name, name)


def parse_list(text):
    return [_norm(t) for t in re.split(r"[,;:\s]+", str(text or "")) if t.strip()]


def session_names(env=None):
    """Lower-case names describing the running session/window manager."""
    env = os.environ if env is None else env
    names = set()
    for var in ("XDG_CURRENT_DESKTOP", "XDG_SESSION_DESKTOP", "DESKTOP_SESSION"):
        for tok in re.split(r"[:;]", env.get(var, "")):
            if tok.strip():
                names.add(_norm(tok))
    if env.get("SWAYSOCK"):
        names.add("sway")
    if env.get("HYPRLAND_INSTANCE_SIGNATURE"):
        names.add("hyprland")
    if env.get("NIRI_SOCKET"):
        names.add("niri")
    if env.get("I3SOCK"):
        names.add("i3")
    return names


def should_start(cfg, env=None):
    """(bool, reason)"""
    if not C.get_path(cfg, "behavior.autostart"):
        return False, "autostart is switched off in the settings"
    wanted = parse_list(C.get_path(cfg, "behavior.autostart_wms"))
    if not wanted:
        return False, "no window manager is listed for autostart"
    if "*" in wanted or "any" in wanted or "all" in wanted:
        return True, "autostart is enabled for every session"
    have = session_names(env)
    hit = sorted(set(wanted) & have)
    if hit:
        return True, "session matches %s" % ", ".join(hit)
    return False, "current session (%s) is not in the autostart list (%s)" % (
        ", ".join(sorted(have)) or "unknown", ", ".join(wanted))


def main():
    ok, reason = should_start(C.load_config())
    print("[glassdock] autostart: %s" % reason, file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
