# GlassDock for macOS (experimental preview)

The experimental macOS backend is implemented in [`glassdock/macos.py`](../glassdock/macos.py) with Python and PyObjC (`pyobjc-framework-Cocoa`). It reuses [`glassdock.core.config`](../glassdock/core/config.py), including the shared JSON configuration schema (`~/.config/glassdock/config.json`). The GTK 3 / Sway implementation remains the primary Linux/Wayland backend.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/Mandrusian/GlassDock/master/installer.sh | bash
```

Or from a local checkout:

```bash
./scripts/install.sh
```

The installer creates a Python virtual environment at `.venv-macos` inside the checkout, installs `pyobjc-framework-Cocoa`, and links `glassdock` into `~/.local/bin`. With login autostart enabled, it writes `~/Library/LaunchAgents/com.mandrusian.glassdock.plist`.

Run `~/.local/bin/glassdock` (or `./bin/glassdock`). Right-click the dock to access GlassDock Settings or Quit.

## Implemented in this preview

- Python runtime and PyObjC native floating `NSPanel` dock
- Discovery of running GUI applications and clickable application icons
- Hover magnification using the shared config values
- Right-click context menu with Activate, Settings, and Quit
- Native Settings sliders for icon size, spacing, magnification factor, opacity, and corner radius
- JSON config persistence shared with the Linux application

## Limitations

This preview is experimental and does not have feature parity with the Linux/Wayland dock: pinned launchers, widgets/plugins, full settings panels, drag and drop, intelligent hide, per-app window menus, and spring animation easing are not implemented yet.
