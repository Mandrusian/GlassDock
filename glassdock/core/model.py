"""Dock data model and geometry. No GTK imports: fully unit-testable.

Coordinates: the dock is laid out in a canonical frame where `m` runs along
the dock's main axis and `c` runs from the screen edge inward. place()
maps canonical rectangles to real widget rectangles for any screen edge.
"""
import math
import os
from dataclasses import dataclass, field

from .config import SPECIAL_KINDS
from .desktop import exec_basename, find_entry
import shlex


# ------------------------------------------------------------------ items

@dataclass
class DockItem:
    key: str
    kind: str                      # app | launcher | special | separator | folder | widget | plugin
    name: str = ""
    icon: str = ""
    entry: object = None           # DesktopEntry or None
    argv: list = None              # for custom launchers
    special: str = ""              # "apps" | "trash"
    extension: str = ""            # clock | calendar | music | plugin module name
    path: str = ""                 # configured folder path
    badge_count: int = 0
    extension_text: str = ""       # dynamic hover label
    pinned: bool = True
    windows: list = field(default_factory=list)
    cfg_index: int = -1            # index into config items (pinned items only)

    @property
    def running(self):
        return bool(self.windows)

    @property
    def active(self):
        return any(w.focused for w in self.windows)

    @property
    def urgent(self):
        return any(w.urgent for w in self.windows)


def _expand_ids(s):
    s = (s or "").strip().lower()
    if not s:
        return set()
    if s.endswith(".desktop"):
        s = s[:-8]
    ids = {s}
    if "." in s:
        last = s.rsplit(".", 1)[-1]
        if len(last) > 2:
            ids.add(last)
    return ids


def entry_identifiers(entry):
    """Return (strong, medium, weak) identifier sets for an entry."""
    strong = _expand_ids(entry.id) | _expand_ids(entry.startup_wm_class)
    medium = {exec_basename(entry.exec)} - {""}
    weak = {entry.name.strip().lower()} - {""}
    return strong, medium, weak


def window_identifiers(win):
    ids = set()
    for s in (win.app_id, win.wm_class):
        ids |= _expand_ids(s)
    return ids


def match_score(identifiers, wids):
    """identifiers: (strong, medium, weak); wids: set of window ids."""
    strong, medium, weak = identifiers
    if wids & strong:
        return 3
    if wids & medium:
        return 2
    if wids & weak:
        return 1
    return 0


def _launcher_identifiers(spec):
    if spec.get("match"):
        return (_expand_ids(spec["match"]), set(), set())
    try:
        base = os.path.basename(shlex.split(spec["exec"])[0]).lower()
    except (ValueError, IndexError):
        base = ""
    return (set(), {base} - {""}, {spec["name"].strip().lower()})


def build_items(cfg_items, entries, windows, show_unpinned=True):
    """Combine configured items with live windows.

    Windows are matched to the best-scoring pinned item; leftovers are
    matched against all installed apps and grouped as running-unpinned items.
    """
    items = []
    idents = []           # parallel to items: identifiers or None
    for idx, spec in enumerate(cfg_items):
        t = spec["type"]
        if t == "separator":
            items.append(DockItem(key="sep:%d" % idx, kind="separator", cfg_index=idx))
            idents.append(None)
        elif t == "special":
            info = SPECIAL_KINDS[spec["kind"]]
            items.append(DockItem(key="special:%s" % spec["kind"], kind="special",
                                  name=info["name"], icon=info["icon"],
                                  special=spec["kind"], badge_count=spec.get("badge_count", 0), cfg_index=idx))
            idents.append(None)
        elif t == "app":
            entry = find_entry(entries, spec["id"])
            if entry is None:
                continue  # not installed: keep in config, hide from dock
            items.append(DockItem(key="app:%s" % entry.id, kind="app", name=spec.get("name") or entry.name,
                                  icon=spec.get("icon") or entry.icon, entry=entry,
                                  badge_count=spec.get("badge_count", 0), cfg_index=idx))
            idents.append(entry_identifiers(entry))
        elif t == "launcher":
            try:
                argv = shlex.split(spec["exec"])
            except ValueError:
                argv = spec["exec"].split()
            items.append(DockItem(key="launcher:%d" % idx, kind="launcher", name=spec["name"],
                                  icon=spec.get("icon", ""), argv=argv,
                                  badge_count=spec.get("badge_count", 0), cfg_index=idx))
            idents.append(_launcher_identifiers(spec))
        elif t == "folder":
            path = spec.get("path", "")
            items.append(DockItem(key="folder:%d" % idx, kind="folder",
                                  name=spec.get("name") or os.path.basename(path) or path,
                                  icon=spec.get("icon", "folder"), path=path,
                                  badge_count=spec.get("badge_count", 0), cfg_index=idx))
            idents.append(None)
        elif t == "widget":
            kind = spec.get("kind", "")
            names = {"clock": "Clock", "calendar": "Calendar", "music": "Music"}
            icons = {"clock": "clock", "calendar": "x-office-calendar", "music": "audio-x-generic"}
            if kind in names:
                items.append(DockItem(key="widget:" + kind, kind="widget", name=names[kind],
                                      icon=icons[kind], extension=kind,
                                      badge_count=spec.get("badge_count", 0), cfg_index=idx))
            idents.append(None)
        elif t == "plugin":
            name = spec.get("name", "")
            items.append(DockItem(key="plugin:" + name, kind="plugin", name=name,
                                  extension=name, icon=spec.get("icon", ""),
                                  badge_count=spec.get("badge_count", 0), cfg_index=idx))
            idents.append(None)

    unclaimed = []
    for win in windows:
        wids = window_identifiers(win)
        best, best_score = None, 0
        for item, ident in zip(items, idents):
            if ident is None:
                continue
            sc = match_score(ident, wids)
            if sc > best_score:
                best, best_score = item, sc
        if best is not None:
            best.windows.append(win)
        else:
            unclaimed.append(win)

    if show_unpinned and unclaimed:
        groups = {}
        order = []
        for win in unclaimed:
            wids = window_identifiers(win)
            best_entry, best_score = None, 0
            for e in entries.values():
                sc = match_score(entry_identifiers(e), wids)
                if sc > best_score:
                    best_entry, best_score = e, sc
            if best_entry is not None:
                gkey = "run:%s" % best_entry.id
                if gkey not in groups:
                    groups[gkey] = DockItem(key=gkey, kind="app", name=best_entry.name,
                                            icon=best_entry.icon, entry=best_entry, pinned=False)
                    order.append(gkey)
            else:
                ident = win.app_id or win.wm_class or str(win.pid)
                gkey = "run:%s" % ident.lower()
                if gkey not in groups:
                    groups[gkey] = DockItem(key=gkey, kind="app", name=ident or "Window",
                                            icon=(win.app_id or win.wm_class or "").lower(),
                                            pinned=False)
                    order.append(gkey)
            groups[gkey].windows.append(win)
        if order:
            if items and items[-1].kind != "separator":
                items.append(DockItem(key="sep:run", kind="separator", pinned=False))
            items.extend(groups[k] for k in order)
    return items


def reorder_items(items, src, before):
    """Move items[src] in front of items[before] (before=None: to the end).

    Returns a new list, or None when the move would not change anything."""
    n = len(items)
    if not 0 <= src < n:
        return None
    if before is None:
        if src == n - 1:
            return None
    elif before in (src, src + 1) or not 0 <= before <= n:
        return None
    out = list(items)
    item = out.pop(src)
    if before is None:
        out.append(item)
    else:
        if before > src:
            before -= 1
        out.insert(before, item)
    return out


# ------------------------------------------------------------- magnification

def magnify_scale(distance, factor, reach):
    """Smooth falloff: 1.0 at/after `reach` slots away, `factor` at 0."""
    if factor <= 1.0 or reach <= 0 or distance >= reach:
        return 1.0
    t = 1.0 - distance / reach
    s = t * t * (3.0 - 2.0 * t)
    return 1.0 + (factor - 1.0) * s


def base_layout(sizes, spacing):
    """Positions of consecutive slots along the main axis (no padding)."""
    pos = []
    m = 0.0
    for s in sizes:
        pos.append(m)
        m += s + spacing
    total = m - spacing if sizes else 0.0
    return pos, total


def pointer_slot(m, positions, sizes):
    """Fractional slot index of main-axis coordinate `m` (relative to the first
    slot start). Slot i spans [i, i+1). Continues linearly outside the ends."""
    if not sizes:
        return None
    if m < positions[0]:
        return (m - positions[0]) / sizes[0]
    for i, (p, s) in enumerate(zip(positions, sizes)):
        nxt = positions[i + 1] if i + 1 < len(sizes) else p + s
        if m < nxt:
            frac = (m - p) / s if s else 0.0
            return i + min(1.0, max(0.0, frac))
    last = len(sizes) - 1
    return last + 1 + (m - (positions[last] + sizes[last])) / sizes[last]


def target_scales(kinds, pointer_pos, factor, reach, enabled=True):
    """Per-item target scale for pointer slot position (None = no pointer)."""
    n = len(kinds)
    if not enabled or pointer_pos is None:
        return [1.0] * n
    out = []
    for i, k in enumerate(kinds):
        if k == "separator":
            out.append(1.0)
        else:
            out.append(magnify_scale(abs(pointer_pos - (i + 0.5)), factor, reach))
    return out


def slot_sizes(kinds, icon, scales=None, sep_width=None):
    if sep_width is None:
        sep_width = max(2, int(icon * 0.22))
    scales = scales or [1.0] * len(kinds)
    return [sep_width if k == "separator" else icon * sc for k, sc in zip(kinds, scales)]


def dock_length(kinds, icon, spacing, padding, scales=None):
    sizes = slot_sizes(kinds, icon, scales)
    _pos, total = base_layout(sizes, spacing)
    return 2 * padding + total


def max_dock_length(kinds, icon, spacing, padding, factor, reach, magnify):
    """Largest length over all pointer positions (for window sizing)."""
    if not kinds:
        return 2 * padding
    if not magnify:
        return dock_length(kinds, icon, spacing, padding)
    best = 0.0
    steps = int((len(kinds) + 2 * reach) * 4) + 1
    for k in range(steps):
        p = -reach + k * 0.25
        sc = target_scales(kinds, p, factor, reach, True)
        best = max(best, dock_length(kinds, icon, spacing, padding, sc))
    return best


# ------------------------------------------------------------ edge mapping

def is_horizontal(edge):
    return edge in ("bottom", "top")


def place(edge, W, H, m, c, mlen, clen):
    """Canonical (m, c, mlen, clen) -> widget rect (x, y, w, h)."""
    if edge == "bottom":
        return (m, H - c - clen, mlen, clen)
    if edge == "top":
        return (m, c, mlen, clen)
    if edge == "left":
        return (c, m, clen, mlen)
    return (W - c - clen, m, clen, mlen)  # right


def unplace(edge, W, H, x, y):
    """Widget point -> canonical (m, c)."""
    if edge == "bottom":
        return (x, H - y)
    if edge == "top":
        return (x, y)
    if edge == "left":
        return (y, x)
    return (y, W - x)


# --------------------------------------------------------------- geometry

@dataclass
class Geometry:
    icon: int
    spacing: int
    padding: int
    margin: int
    shadow: int            # shadow room S around the dock (0 if disabled)
    edge: str
    alignment: str
    n_kinds: int
    thick: float           # dock panel thickness (cross axis)
    ind_room: float        # cross space reserved under icons for indicators
    side_off: float        # distance from window side to dock when aligned start/end
    c0: float              # cross offset of panel from window edge
    layer_margin: int      # margin to give the layer-shell surface (edge side)
    side_margin: int       # margin on alignment side
    max_len: float         # largest dock length (magnified)
    win_main: int          # window size along main axis
    win_cross: int         # window size along cross axis
    base_len: float        # unmagnified dock length

    @property
    def win_size(self):
        """Window (width, height) in pixels."""
        if is_horizontal(self.edge):
            return self.win_main, self.win_cross
        return self.win_cross, self.win_main


def compute_geometry(kinds, *, icon, spacing, padding, margin, shadow_size, edge, alignment,
                     indicator_size, indicator_style, magnify, factor, reach, bounce,
                     labels, max_main=None):
    """Compute dock geometry, optionally fitting the main axis inside a monitor.

    max_main is the maximum window width for top/bottom docks or height for
    left/right docks. If contents would exceed it, icon, spacing and padding are
    scaled together to avoid oversized layer-shell surfaces being rejected or
    clipped by the compositor when many items are pinned.
    """
    S = int(shadow_size)
    if max_main is not None:
        limit = max(1.0, float(max_main))
        S = min(S, max(0, int((limit - 1) / 2)))
        original_icon = float(icon)
        original_spacing = float(spacing)
        original_padding = float(padding)

        def fitted(scale):
            fitted_icon = max(1.0, original_icon * scale)
            fitted_spacing = original_spacing * scale
            fitted_padding = original_padding * scale
            fitted_max = max_dock_length(
                kinds, fitted_icon, fitted_spacing, fitted_padding,
                factor, reach, magnify)
            return fitted_icon, fitted_spacing, fitted_padding, fitted_max + 2 * S

        if fitted(1.0)[3] > limit:
            lo, hi = 0.0, 1.0
            for _ in range(32):
                mid = (lo + hi) / 2.0
                if fitted(mid)[3] <= limit:
                    lo = mid
                else:
                    hi = mid
            icon, spacing, padding, _need = fitted(lo)
    ind_room = 0 if indicator_style == "none" else indicator_size + 4
    thick = icon + 2 * padding + ind_room
    side_off = min(margin, S)
    side_margin = margin - side_off
    c0 = min(margin, S)
    layer_margin = margin - c0
    max_len = max_dock_length(kinds, icon, spacing, padding, factor, reach, magnify)
    base_len = dock_length(kinds, icon, spacing, padding)
    win_main = int(math.ceil(max_len + 2 * S))
    extra = 0.0
    if magnify:
        extra = icon * (factor - 1.0)
    if bounce:
        extra = max(extra, icon * 0.45)
    label_extra = 0
    if labels:
        label_extra = 34 if is_horizontal(edge) else 260
    win_cross = int(math.ceil(c0 + thick + extra + label_extra + 6))
    return Geometry(icon=icon, spacing=spacing, padding=padding, margin=margin, shadow=S,
                    edge=edge, alignment=alignment, n_kinds=len(kinds), thick=thick,
                    ind_room=ind_room, side_off=side_off, c0=c0, layer_margin=layer_margin,
                    side_margin=side_margin, max_len=max_len, win_main=win_main,
                    win_cross=win_cross, base_len=base_len)


def dock_origin(geo, length):
    """Main-axis start of the dock panel inside the window."""
    if geo.alignment == "start":
        return geo.side_off
    if geo.alignment == "end":
        return geo.win_main - geo.side_off - length
    return (geo.win_main - length) / 2.0


def exclusive_zone(geo, enabled, autohide):
    """Distance from the anchored edge to reserve (0 = none)."""
    if not enabled or autohide != "off":
        return 0
    return int(math.ceil(geo.c0 + geo.thick))


def dock_global_rect(out_rect, edge, alignment, margin, length, thick):
    """Resting dock panel rectangle in global compositor coordinates."""
    ox, oy, ow, oh = out_rect
    if is_horizontal(edge):
        if alignment == "start":
            x = ox + margin
        elif alignment == "end":
            x = ox + ow - margin - length
        else:
            x = ox + (ow - length) / 2.0
        y = oy + oh - margin - thick if edge == "bottom" else oy + margin
        return (x, y, length, thick)
    if alignment == "start":
        y = oy + margin
    elif alignment == "end":
        y = oy + oh - margin - length
    else:
        y = oy + (oh - length) / 2.0
    x = ox + margin if edge == "left" else ox + ow - margin - thick
    return (x, y, thick, length)


# ------------------------------------------------------------- visibility

def rects_intersect(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def overlapping_windows(dock_rect, windows, output):
    """True if a visible, non-fullscreen window on `output` overlaps the dock."""
    for w in windows:
        if w.output != output or not w.visible or w.fullscreen:
            continue
        if w.rect[2] <= 0 or w.rect[3] <= 0:
            continue
        if rects_intersect(dock_rect, w.rect):
            return True
    return False


def decide_visibility(*, mode, fullscreen, hide_on_fullscreen, overlapping, pointer_inside,
                      menu_open):
    """Pure decision: should the dock be shown right now?"""
    if fullscreen and hide_on_fullscreen:
        return False
    if mode == "off":
        return True
    if pointer_inside or menu_open:
        return True
    if mode == "always":
        return False
    return not overlapping  # "overlap"


# -------------------------------------------------------------- indicators

def indicator_layout(n_windows, active, style):
    """Return list of 'active'/'normal' markers to draw (max 3 dots; 1 line)."""
    if style == "none" or n_windows <= 0:
        return []
    if style == "line":
        return ["active" if active else "normal"]
    n = min(n_windows, 3)
    return ["active" if (active and i == 0) else "normal" for i in range(n)]


# ----------------------------------------------------------------- easing

def ease(name, t):
    t = min(1.0, max(0.0, t))
    if name == "linear":
        return t
    if name == "ease-in-out":
        return t * t * (3.0 - 2.0 * t)
    return 1.0 - (1.0 - t) ** 3  # ease-out
