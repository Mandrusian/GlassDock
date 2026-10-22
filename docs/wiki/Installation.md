# Install and update

## Requirements

- Wayland session with layer-shell support
- Python 3.9 or newer
- GTK 3 and PyGObject
- Pycairo
- gtk-layer-shell
- Sway or SwayFX for Sway IPC integration

Transparency depends on compositor support. Background blur requires SwayFX and its `layer_effects` support.

## Guided installer

```bash
curl -fsSL https://raw.githubusercontent.com/Mandrusian/GlassDock/master/installer.sh | bash
```

Choose an action from the menu. You can install/update GlassDock or GlassIcon Studio, uninstall either app, or exit. Dependency installation is optional and may use `sudo`.

Review [installer.sh](../../installer.sh) before running it if you want to inspect the script first.

## Manual install

```bash
git clone https://github.com/Mandrusian/GlassDock.git
cd GlassDock
./scripts/install-deps.sh
./install.sh
```

The dependency helper supports Fedora, Debian/Ubuntu, Arch, and openSUSE. System package installation may need root access. The app itself is installed for your user.

The installer links commands into `~/.local/bin`, adds a Settings launcher, and configures login autostart. Keep the project directory in place because the command links point into it.

## Run

```bash
glassdock &
glassdock-settings
glassdock-ctl status
```

Run GlassDock from inside your Wayland session.

## Update

From the cloned project directory:

```bash
git pull --ff-only
./install.sh
```

Your configuration is stored separately in `~/.config/glassdock/`.

## Uninstall

```bash
./scripts/uninstall.sh
```

This removes command links, launchers, and autostart entries but keeps settings. To also back up and remove settings:

```bash
./scripts/uninstall.sh --purge
```

The project directory is not deleted. Remove it yourself if you no longer need it.
