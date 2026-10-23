#!/usr/bin/env python3
"""Minimal EWMH X11 dock backend for i3 and other X11 window managers.

Independent from the GTK/Wayland backend. Requires python-xlib.
"""
import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

try:
    from Xlib import X, Xatom, display
    from Xlib.protocol import event
except ImportError:
    sys.exit("Missing python-xlib. Run: python -m pip install --user python-xlib")

DEFAULTS = {
    "edge": "bottom",
    "height": 64,
    "icon_width": 88,
    "gap": 8,
    "margin": 12,
    "reserve_space": True,
    "background": "#202027",
    "foreground": "#ffffff",
    "accent": "#8ab4ff",
    "launchers": [
        {"name": "Terminal", "command": "xterm"},
        {"name": "Browser", "command": "firefox"},
        {"name": "Files", "command": "thunar"},
    ],
}


def load_config(path):
    path = Path(path).expanduser()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(DEFAULTS, indent=2) + "\n", encoding="utf-8")
        print(f"[glassdock-x11] Created example config: {path}", file=sys.stderr)
        print("[glassdock-x11] Edit launcher commands to match installed applications.", file=sys.stderr)
        return dict(DEFAULTS)
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        sys.exit(f"Cannot read config {path}: {exc}")
    merged = dict(DEFAULTS)
    merged.update(cfg)
    if merged.get("edge") not in ("top", "bottom"):
        sys.exit("Config 'edge' must be 'top' or 'bottom'.")
    merged["launchers"] = [x for x in merged.get("launchers", []) if x.get("name") and x.get("command")]
    return merged


def color_pixel(disp, screen, value):
    try:
        cmap = screen.default_colormap
        return cmap.alloc_named_color(value).pixel
    except Exception:
        return screen.black_pixel


class X11Dock:
    def __init__(self, cfg):
        self.cfg = cfg
        self.disp = display.Display()
        self.screen = self.disp.screen()
        self.root = self.screen.root
        self.width = self.screen.width_in_pixels
        self.height = max(32, int(cfg["height"]))
        self.edge = cfg["edge"]
        self.gap = max(0, int(cfg["gap"]))
        self.margin = max(0, int(cfg["margin"]))
        self.tile_w = max(44, int(cfg["icon_width"]))
        self.launchers = cfg["launchers"]
        self.atom = lambda name: self.disp.intern_atom(name)
        self.bg = color_pixel(self.disp, self.screen, cfg["background"])
        self.fg = color_pixel(self.disp, self.screen, cfg["foreground"])
        self.accent = color_pixel(self.disp, self.screen, cfg["accent"])
        self.gc = self.root.create_gc(foreground=self.fg, background=self.bg)
        self.active_gc = self.root.create_gc(foreground=self.accent, background=self.bg)
        self.font = self.disp.open_font("fixed")
        self.gc.change(font=self.font)
        self.active_gc.change(font=self.font)
        content_w = len(self.launchers) * self.tile_w + max(0, len(self.launchers) - 1) * self.gap
        self.dock_w = min(self.width, content_w + self.margin * 2)
        self.x = max(0, (self.width - self.dock_w) // 2)
        self.y = 0 if self.edge == "top" else self.screen.height_in_pixels - self.height
        self.window = self.root.create_window(
            self.x, self.y, self.dock_w, self.height, 0,
            self.screen.root_depth, X.InputOutput, X.CopyFromParent,
            background_pixel=self.bg,
            event_mask=X.ExposureMask | X.ButtonPressMask | X.StructureNotifyMask,
        )
        self.window.set_wm_name("GlassDock X11")
        self.window.set_wm_class("glassdock-x11", "GlassDock")
        self._set_atom_list("_NET_WM_WINDOW_TYPE", ["_NET_WM_WINDOW_TYPE_DOCK"])
        self._set_atom_list("_NET_WM_STATE", [
            "_NET_WM_STATE_STICKY", "_NET_WM_STATE_ABOVE",
            "_NET_WM_STATE_SKIP_TASKBAR", "_NET_WM_STATE_SKIP_PAGER",
        ])
        self._set_struts()
        self.window.map()
        self.disp.flush()

    def _set_atom_list(self, prop_name, names, type_name="ATOM"):
        prop_type = self.atom(type_name)
        values = [self.atom(n) for n in names]
        self.window.change_property(self.atom(prop_name), prop_type, 32, values)

    def _set_struts(self):
        zeros = [0] * 12
        if self.cfg.get("reserve_space", True):
            if self.edge == "bottom":
                zeros[3] = self.height
                zeros[10] = self.x
                zeros[11] = self.x + self.dock_w - 1
            else:
                zeros[2] = self.height
                zeros[8] = self.x
                zeros[9] = self.x + self.dock_w - 1
        self.window.change_property(self.atom("_NET_WM_STRUT_PARTIAL"), Xatom.CARDINAL, 32, zeros)
        self.window.change_property(self.atom("_NET_WM_STRUT"), Xatom.CARDINAL, 32, zeros[:4])

    def draw(self):
        self.window.clear_area()
        self.window.fill_rectangle(self.gc, 0, 0, self.dock_w, self.height)
        tile_h = max(24, self.height - 12)
        y = (self.height - tile_h) // 2
        for i, item in enumerate(self.launchers):
            x = self.margin + i * (self.tile_w + self.gap)
            self.window.fill_rectangle(self.active_gc, x, y, self.tile_w, tile_h)
            label = str(item["name"])[:max(1, (self.tile_w - 12) // 7)]
            tw = len(label) * 6
            tx = x + max(4, (self.tile_w - tw) // 2)
            ty = y + tile_h // 2 + 4
            self.window.draw_text(self.gc, tx, ty, label)
        self.disp.flush()

    def launch(self, index):
        if not 0 <= index < len(self.launchers):
            return
        command = self.launchers[index]["command"]
        try:
            argv = shlex.split(command)
            if argv:
                subprocess.Popen(argv, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 start_new_session=True, env=os.environ.copy())
        except (OSError, ValueError) as exc:
            print(f"[glassdock-x11] Could not launch {command!r}: {exc}", file=sys.stderr)

    def run(self):
        print("[glassdock-x11] Running. Ctrl+C to stop.", file=sys.stderr)
        self.draw()
        try:
            while True:
                while self.disp.pending_events():
                    ev = self.disp.next_event()
                    if ev.type == X.Expose:
                        if ev.count == 0:
                            self.draw()
                    elif ev.type == X.ButtonPress:
                        local_x = int(ev.event_x) - self.margin
                        stride = self.tile_w + self.gap
                        if local_x >= 0 and stride > 0:
                            index = local_x // stride
                            if local_x % stride < self.tile_w:
                                self.launch(index)
                time.sleep(0.03)
        except KeyboardInterrupt:
            pass
        finally:
            try:
                self.window.destroy()
                self.disp.flush()
                self.disp.close()
            except Exception:
                pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="~/.config/glassdock-x11/config.json",
                        help="Path to JSON configuration (default: ~/.config/glassdock-x11/config.json)")
    args = parser.parse_args()
    cfg = load_config(args.config)
    try:
        X11Dock(cfg).run()
    except Exception as exc:
        sys.exit(f"GlassDock X11 failed: {exc}. Check that DISPLAY points to a working X11 server.")


if __name__ == "__main__":
    main()
