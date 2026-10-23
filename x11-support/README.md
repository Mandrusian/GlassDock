# GlassDock X11 support (i3 / Termux:X11)

This is a separate, lightweight X11 backend for i3 and other EWMH-compatible X11 window managers. It does not import GTK, PyGObject, Cairo, or gtk-layer-shell, so it avoids the missing GTK introspection typelibs seen in some Termux package builds.

## Status and scope

The X11 backend is intentionally independent of the existing Wayland application. It creates a simple dock window, launches configured commands, marks itself as an EWMH dock, and publishes screen-edge struts when reserving space is enabled. It is a functional starter backend, not a port of every GlassDock feature: it currently uses text tiles rather than the full GlassDock icon/theme/animation UI.

## Requirements

- An X11 session and an EWMH-compatible window manager (tested target: i3; not yet device-tested).
- Python 3.9+
- Python package `python-xlib`
- Termux:X11 users need a working Termux:X11 server and an i3 session.

## Install on Termux

From the repository root:

```sh
pkg install python python-pip x11-repo
python -m pip install --user python-xlib
```

If pip reports that it cannot write to the user site, use a virtual environment:

```sh
python -m venv ~/.venvs/glassdock-x11
~/.venvs/glassdock-x11/bin/pip install python-xlib
```

## Run

From the repository root:

```sh
python x11-support/glassdock-x11.py
```

Or with a custom JSON config:

```sh
python x11-support/glassdock-x11.py --config ~/.config/glassdock-x11.json
```

The first run creates `~/.config/glassdock-x11.json` with example launchers if it does not exist. Edit each item's `name` and `command` to match programs installed on your system. Commands are executed without a shell.

## i3 autostart

Add this to `~/.config/i3/config` (adjust the repository path):

```i3
exec_always --no-startup-id python3 /path/to/GlassDock/x11-support/glassdock-x11.py
```

Reload i3 with `$mod+Shift+r`. Avoid adding the same command more than once.

## Configuration

Example:

```json
{
  "edge": "bottom",
  "height": 64,
  "icon_width": 88,
  "gap": 8,
  "margin": 12,
  "reserve_space": true,
  "background": "#202027",
  "foreground": "#ffffff",
  "accent": "#8ab4ff",
  "launchers": [
    {"name": "Terminal", "command": "xterm"},
    {"name": "Browser", "command": "firefox"}
  ]
}
```

- `edge`: `bottom` or `top`
- `height`, `icon_width`, `gap`, and `margin`: dimensions in X11 pixels
- `reserve_space`: publish EWMH struts so tiled windows avoid the dock
- `background`, `foreground`, `accent`: X11 color names or hex colors
- `launchers`: clickable text launchers; commands are split into argument arrays and are not run through a shell

## Limitations

- This backend is for X11; it does not replace or modify the Wayland backend.
- It currently provides basic launchers and EWMH dock placement, not the complete GlassDock GTK UI, icon rendering, magnification, drag-and-drop, or settings GUI.
- Window-manager behavior varies. i3 support is the target but should be verified on the actual desktop before considering it fully supported.
