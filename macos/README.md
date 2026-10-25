# macOS backend preview

GlassDock's existing GTK3 + gtk-layer-shell dock remains Linux-only. This branch adds a separate AppKit desktop backend that can run on macOS without Sway, GTK, or gtk-layer-shell.

## Install on macOS

Requires the Xcode Command Line Tools (`xcode-select --install` provides `swiftc`).

```bash
curl -fsSL https://raw.githubusercontent.com/Mandrusian/GlassDock/feature/macos-native-preview/installer.sh | bash -s -- --action install
```

Then run `~/.local/bin/glassdock` (or `glassdock` if it is on PATH). The installer builds the native executable under `~/.local/share/GlassDock/macos/build/`, links the launcher, and writes a LaunchAgent when autostart is enabled. A logout/login loads the LaunchAgent.

## Current features

- Translucent native macOS floating panel
- Icons of running GUI applications, refreshed on launch/quit
- Click an icon to activate the corresponding application
- Runs without GTK, Wayland or Sway
- Automatically positions near the bottom of the primary visible display

## Not yet implemented

This is a **preview**, not feature parity with GlassDock for Linux. Pinned launchers, live configuration UI, plugins, extension widgets, window indicators, multi-display behavior, magnification, native autohide, drag and drop, and Linux settings/control commands are not supported by this backend yet.

The preview has not been compiled or visually tested on a macOS runner; validate the Swift build on a Mac before merging.
