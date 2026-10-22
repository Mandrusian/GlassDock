<h1 align="center"><img src="assets/glassdock.svg" alt="GlassDock icon" width="52" align="middle" />&nbsp;GlassDock</h1>

<p align="center">A floating, glass-style dock for Wayland desktops.</p>

<p align="center">Built with Python, GTK 3 and gtk-layer-shell. Designed for Sway and SwayFX, with a graphical settings app and per-monitor customization.</p>

---

GlassDock brings a clean, macOS-inspired dock to your Wayland desktop without replacing your compositor or desktop shell.

- **Launchers and running apps** — pin applications, group their windows, and see running-app indicators through Sway IPC.
- **Fluid interactions** — hover magnification, smooth animations, launch bounce, app-name labels, and drag-to-reorder launchers.
- **Wayland-native placement** — layer-shell anchoring, edge and alignment controls, margins, exclusive-zone handling, and per-monitor settings.
- **Flexible behavior** — auto-hide, hide on fullscreen, optional overlay stacking, and login autostart controls.
- **Graphical settings** — adjust colors, gradients, opacity, borders, shadows, radius, sizing, animations, indicators, themes, launchers, and monitor overrides with a live preview.
- **Multiple looks** — Smoky Glass, Dark, Light, macOS-inspired, Liquid Glass-inspired, Purple/Pink, and Custom themes.

## Requirements

- A Wayland session with `wlr-layer-shell` support.
- Python 3.9 or newer, GTK 3, PyGObject, Pycairo, and `gtk-layer-shell`.
- Sway or SwayFX is recommended. Sway IPC is used for window and running-application information.

GlassDock does not require GNOME Shell, KDE Plasma, or X11. The dock can be translucent on supported Wayland compositors; **background blur specifically requires SwayFX** and its `layer_effects` support.

## Install

Clone the repository and install the runtime dependencies using the helper for your package manager (Fedora, Debian/Ubuntu, Arch, and openSUSE are supported by the script):

```bash
git clone https://github.com/Mandrusian/GlassDock.git
cd GlassDock
./scripts/install-deps.sh
./install.sh
```

The installer checks the dependencies, links the commands into `~/.local/bin`, adds a Settings launcher, and enables login autostart by default. It runs **in place** from the project directory, so keep that directory where it is. Root access is only needed when installing system packages.

To verify the installation, run the test suite:

```bash
./scripts/run-tests.sh
```

The GTK smoke test runs only in a suitable Wayland session; it is skipped when the required session support is unavailable.

### Start GlassDock

Start the dock from inside your Wayland session:

```bash
glassdock &
glassdock-settings
```

Useful commands:

```bash
glassdock-ctl status
glassdock-ctl reload
glassdock-ctl toggle
glassdock-ctl quit
```

## Autostart

The installer adds a login entry. By default, GlassDock only autostarts in sessions listed in **Settings → Behavior → Only auto-start in these sessions/WMs** (default: `sway`). You can change the list there; use `*` to allow every session.

For compositors that do not run XDG autostart, add the relevant command to the compositor's startup configuration. For example:

```ini
# Hyprland
exec-once = glassdock --autostart
```

```kdl
// niri
spawn-at-startup "glassdock" "--autostart"
```

For Sway, the helper can safely add or remove a managed autostart block in the Sway config. It creates a timestamped backup and validates the edited config before keeping the change:

```bash
./scripts/sway-integration.sh enable-autostart
swaymsg reload
```

Undo it with `./scripts/sway-integration.sh disable-autostart`.

## Using the dock

| Action | Result |
| --- | --- |
| Click an item | Launch the app or focus its window; click again to cycle its windows |
| Middle-click or Shift-click | Open a new window or instance |
| Drag an icon | Reorder pinned items |
| Right-click an item | Open the window list, app actions, pin/unpin controls, Settings, or Quit |
| `glassdock-ctl toggle` | Show or hide the dock |
| `glassdock-ctl launch N` | Activate the Nth dock item |

Example Sway keybindings:

```ini
bindsym $mod+Ctrl+d exec glassdock-ctl toggle
bindsym $mod+Ctrl+1 exec glassdock-ctl launch 1
```

GlassDock also writes commented example bindings to `~/.config/glassdock/sway.conf`.

## Configuration

Settings are stored in `~/.config/glassdock/config.json`. The configuration is validated and migrated on load; unknown or invalid values fall back to defaults. Changes made in the Settings app apply live, and manual edits are picked up automatically.

## Transparency and blur

GlassDock draws a translucent surface. On **SwayFX**, the Background blur option requests a blur effect through `layer_effects`. Plain Sway does not provide that effect, so the dock remains translucent without background blur. To check support, run:

```bash
./scripts/sway-integration.sh check-blur
```

“macOS-inspired” and “Liquid Glass-inspired” refer to visual themes, not exact copies of another operating system's interface.

## Update

From the project directory, update the checkout and rerun the installer:

```bash
git pull --ff-only
./install.sh
```

Your settings in `~/.config/glassdock` are kept separately from the project files.

## Uninstall

```bash
./scripts/uninstall.sh          # remove command links, launchers, and autostart; keep settings
./scripts/uninstall.sh --purge  # also back up and remove settings
```

The project directory is not deleted by the uninstaller; remove it yourself after uninstalling if you no longer need it.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| `GtkLayerShell typelib not found` | Run `./scripts/install-deps.sh`, or install `gtk-layer-shell` and PyGObject using your distribution's package manager. |
| The dock opens as a normal window or appears in the wrong place | Start it from the Wayland session using the `glassdock` launcher; it handles loading `libgtk-layer-shell`. |
| Running-app indicators are missing | Run `glassdock-ctl status` and check that `sway_ipc` is `true`. Start GlassDock inside Sway/SwayFX so `SWAYSOCK` is available. |
| Background blur does nothing | Blur needs SwayFX. Check with `./scripts/sway-integration.sh check-blur`, then reload SwayFX and run `glassdock-ctl reload`. |
| An icon appears as a colored letter tile | The app may not have an icon in your current icon theme; install an icon theme or set an icon in its desktop entry. |
| The Applications button does nothing | Set **Applications button command** in Settings → Behavior. The default is `fuzzel`; install it or choose another launcher such as `wmenu-run`. |
| The dock is hidden behind a fullscreen app | In Settings → Behavior, try **Stacking layer = Overlay** and disable **Hide while fullscreen**. |
| Nothing appears | Run `glassdock` from a terminal and inspect its output, then collect `glassdock-ctl status` when opening an issue. |

## Project layout

```text
assets/       GlassDock icon
bin/          glassdock, glassdock-settings, glassdock-ctl launchers
glassdock/    GTK dock, settings app, CLI, and core modules
scripts/      dependency, build, install, uninstall, Sway integration, and test helpers
tests/        unit tests, mock Sway IPC server, and GTK smoke test
```

## Development notes

GlassDock is Python and GTK 3 rather than a native-code application. The build helper byte-compiles the Python sources and checks runtime dependencies. The test suite covers configuration and migration, desktop entries, Sway IPC parsing, dock models and geometry, icons, and installation scripts. Actual rendering, layer-shell placement, and SwayFX blur should still be verified in your own Wayland session.

## License

MIT. See [`LICENSE`](LICENSE). Runtime dependencies are provided by your distribution and are not bundled; see [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).
