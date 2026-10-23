# i3 / X11 support

This directory contains the i3-specific integration notes for GlassDock.

## Why a separate backend is needed

The current GlassDock application targets Wayland and uses `gtk-layer-shell` to place the dock above or below other surfaces. i3 is an X11 window manager, so the Wayland layer-shell backend cannot work in an i3 session.

A real i3 implementation must use an X11 dock window and set the appropriate EWMH properties (including `_NET_WM_WINDOW_TYPE_DOCK` and struts) so i3 can place it in its dock area and reserve screen space. An i3 configuration rule alone cannot convert the existing Wayland window into an X11 dock.

## Current status

**Scaffold only — X11 dock rendering is not implemented yet.** The existing Wayland application and its installation path are unchanged. Do not run the normal GlassDock installer expecting it to work in i3 based on this directory alone.

## Verify the current session

From a terminal inside i3:

```sh
printf 'XDG_SESSION_TYPE=%s\nDISPLAY=%s\nWAYLAND_DISPLAY=%s\n' \
  "${XDG_SESSION_TYPE:-}" "${DISPLAY:-}" "${WAYLAND_DISPLAY:-}"
i3 --version
```

For a typical i3/X11 session, `DISPLAY` is set and `WAYLAND_DISPLAY` is empty.

## Planned implementation

- Add an X11 backend that does not import or require `GtkLayerShell`.
- Create a dock-type window with EWMH dock hints and partial struts.
- Keep the existing GlassDock UI, settings, and Wayland backend where practical.
- Add separate dependency checks and launch instructions for i3/X11.
- Test on a real i3 session before describing the backend as supported.
