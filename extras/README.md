# GlassDock extras

## GlassIcon Studio

A lightweight GTK 3 companion for GlassDock that manages icon themes, per-application launcher icons, and user-level file-manager/system icon overrides. It is useful with Thunar and standalone window managers when the desktop's native settings panel does not reach every icon.

- Source: [`GlassIcon/`](GlassIcon/)
- Requirements and usage: [`GlassIcon/README.md`](GlassIcon/README.md)
- Install dependencies: `./extras/GlassIcon/scripts/install-deps.sh`
- Install launcher and desktop entry: `./extras/GlassIcon/install.sh`
- Run tests: `./extras/GlassIcon/scripts/run-tests.sh`

GlassIcon runs as the current user. Only its dependency installer may use `sudo`.

You can also install or uninstall GlassIcon Studio from the main guided setup menu:

```sh
curl -fsSL https://raw.githubusercontent.com/Mandrusian/GlassDock/master/installer.sh | bash
```

Choose **Install / Upgrade GlassIcon Studio**. This delegates to `GlassIcon/install.sh` and optionally lets you install dependencies. Use the uninstaller option to remove the command and menu entry while preserving icon themes and backups.
