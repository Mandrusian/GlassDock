# GlassDock for macOS — Python preview

The macOS backend is implemented in `glassdock/macos.py` with Python and PyObjC. It reuses `glassdock.core.config`, including the existing JSON configuration schema. The GTK3 / Sway implementation remains the Linux backend.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/Mandrusian/GlassDock/feature/macos-native-preview/installer.sh | bash -s -- --action install --branch feature/macos-native-preview
```

The installer creates a Python virtual environment at `~/.local/share/GlassDock/.venv-macos`, installs `pyobjc-framework-Cocoa`, and links `glassdock` in `~/.local/bin`.

Run `~/.local/bin/glassdock`. Right-click the dock to access GlassDock Settings or Quit.

## Implemented in this preview

- Python runtime and PyObjC native macOS dock panel
- Discovery of running apps and clickable application icons
- Hover magnification using the shared config values
- Right-click context menu with Settings and Quit
- Native Settings sliders for icon size, spacing, magnification factor, opacity, and corner radius
- JSON config persistence shared with the Linux application

## Limitations

This is not yet feature parity: pinned launchers, advanced Linux plugin/widgets integration, full settings panels, drag and drop, intelligent hide, per-app context menus, and animation easing are still missing. Magnification currently changes immediately rather than with spring animation. The build and UI require testing on a real Mac; the branch has not yet been validated in a macOS CI runner.
