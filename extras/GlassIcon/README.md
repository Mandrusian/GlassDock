# GlassIcon Studio

**A lightweight icon changer for Linux desktops, GTK apps, and standalone window managers — made to pair with [GlassDock](https://github.com/Mandrusian/GlassDock).**

GlassIcon is a Python + GTK 3 utility. It has no service running in the background and does not need root privileges for icon changes. It uses the freedesktop icon-theme format and XDG user directories, with desktop-specific settings applied when available.

## Features

- **Icon theme manager:** discovers themes in `~/.local/share/icons`, `~/.icons`, `$XDG_DATA_DIRS/icons`, `/usr/share/icons`, Flatpak exports, and common system locations.
- **Launcher icon editor:** search installed `.desktop` launchers, assign an SVG/SVGZ/PNG/XPM icon, and restore the previous launcher. It uses user-local desktop-file overrides instead of editing system files.
- **File manager and system icons:** layer custom folder, Home, Trash, drive, network, Applications, and common file-type icons over the current theme. This is useful for Thunar and other apps where a native settings panel does not reach every icon.
- **Cross-desktop settings:** writes GTK 3 and GTK 4 user settings and updates GNOME-family `gsettings`, Xfce `xfconf`, KDE Plasma `kdeglobals`, xsettingsd, and LXQt configuration where available.
- **Undo support:** keeps state and necessary user-launcher backups under XDG state directories; removes only generated overlays when resetting them.
- **Small runtime footprint:** Python standard library + GTK 3 / PyGObject. No Electron, browser engine, database server, or always-on daemon.

## Install

From a checkout of this repository:

```sh
cd misc-os-tools/GlassIcon
./scripts/install-deps.sh
./install.sh
glassicon
```

On Fedora / Fedora Asahi Remix, Debian or Ubuntu, Arch Linux, and openSUSE, `install-deps.sh` uses the system package manager. Dependency installation is the only step that may use `sudo`.

To install dependencies and GlassIcon in one run, use `./install.sh --deps` instead. The launcher is placed at `~/.local/bin/glassicon` and a desktop-menu entry is added. The project is run in place, so keep the repository folder. `./uninstall.sh` removes the launcher only; it deliberately preserves your icon settings, user icon layer, and backups.

## Use

- **Icon themes:** select an installed theme and choose **Apply selected theme**. GlassIcon writes per-user GTK 3 and 4 `settings.ini` entries and updates desktop settings it can detect. Restart open apps if they keep cached icons.
- **Application icons:** choose an app, select an image, and apply. Desktop files are overridden in `~/.local/share/applications`; originals in system directories are never changed. **Reset selected icon** removes the generated user copy or restores the user file that existed before the first change.
- **Files & system icons:** select a role such as Folder, Home, Trash, or Hard drive, then choose an image. GlassIcon creates a small inheriting theme in `~/.local/share/icons/GlassIcon-Overrides` (using a collision-safe name if needed). It changes only that named icon; all other icons continue to come from the base theme.
- **Backups & restore:** review all current overrides or restore the icon theme that GlassIcon detected before your first theme change.

### Thunar, Sway, SwayFX, and other lightweight WMs

On a standalone window manager, there may be no desktop settings daemon at all. Applying a theme still writes `~/.config/gtk-3.0/settings.ini` (important for Thunar) and `~/.config/gtk-4.0/settings.ini`. If Xfce/XSettings, GNOME-style settings, KDE Plasma, LXQt, or xsettingsd is present, GlassIcon updates that configuration too. GTK apps already running may need to be restarted; a compositor reload alone does not always refresh their icon cache.

GlassIcon only changes the current user's session and files. It **does not modify `/usr/share/icons`, does not run `sudo` for icon operations, and does not claim to change icons inside already-running window decorations**. Per-app launcher icons affect the app menu, task switchers or docks that honor `.desktop` files; app window icons are controlled by each app itself.

## Requirements / compatibility

- Python 3.10 or newer
- GTK 3 and PyGObject (`python3-gobject` / `python3-gi`)
- Any desktop session or window manager; actual live theme integration depends on which settings services the session runs

Commonly supported package managers: `dnf`, `apt-get`, `pacman`, `zypper`, and Void Linux `xbps-install`. Other distributions may work by installing the equivalent Python 3, GTK 3, and PyGObject packages.

## Tests

```sh
./scripts/run-tests.sh
```

The tests cover theme discovery, preserving unrelated GTK settings, launcher override/restore behavior, system overlay creation/removal, and atomic file writes. Run `./scripts/build.sh` after changes. The GTK UI itself should also be tested in a live desktop session.

## Project files

```text
glassicon_core.py     XDG discovery, theme/launcher changes, backups and restore
glassicon_gui.py      GTK 3 interface
bin/glassicon         launcher
scripts/              dependency install, build, tests
assets/glassicon.svg  app icon
tests/                standard-library unit tests
```

## License

This tool is part of the `Mandrusian/misc-os-tools` repository and follows the repository's license.
