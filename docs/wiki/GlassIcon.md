# GlassIcon Studio

GlassIcon Studio is the companion app in `extras/GlassIcon/`. It manages icon themes, per-application launcher icons, and user-level folder, Home, Trash, drive, and file-type icons.

It uses Python and GTK 3. Icon changes are made for your user; it does not need a background daemon.

## Install

From the repository root:

```bash
./extras/GlassIcon/install.sh
```

To install its system dependencies too:

```bash
./extras/GlassIcon/install.sh --deps
```

The dependency option may use `sudo`.

## Launch

```bash
glassicon
```

The main guided installer also has install/update and uninstall actions for GlassIcon Studio.

## Notes

- Settings and icon backups are stored in user directories.
- The app is useful with Thunar and lightweight window-manager setups.
- Read the [GlassIcon README](../../extras/GlassIcon/README.md) for the current feature list and limitations.
