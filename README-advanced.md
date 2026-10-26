<h1 align="center"><img src="assets/glassdock.svg" alt="GlassDock app icon" width="56" align="middle" />&nbsp;GlassDock</h1>

<p align="center"><a href="README.md">← Simple README</a> · Advanced documentation</p>
<p align="center"><strong>Quick installer</strong></p>

<p align="center"><code>curl -fsSL https://raw.githubusercontent.com/Mandrusian/GlassDock/master/installer.sh | bash</code></p>

<p align="center"><a href="https://raw.githubusercontent.com/Mandrusian/GlassDock/master/installer.sh">View installer source</a></p>


<p align="center">A floating, glass-style dock for Wayland desktops.</p>

<p align="center">Built with Python, GTK 3 and gtk-layer-shell. Designed for Sway and SwayFX, with a graphical settings app and per-monitor customization.</p>

<p align="center"><a href="https://mandrusian.github.io/GlassDock/">Project website ↗</a> · <a href="https://github.com/Mandrusian/GlassDock">Source code</a></p>

GlassDock brings a clean, macOS-inspired dock to your Wayland desktop without replacing your compositor or desktop shell.

- **Launchers and running apps** — pin applications, group their windows, and see running-app indicators through Sway IPC.
- **Fluid interactions** — hover magnification, smooth animations, launch bounce, app-name labels, and drag-to-reorder launchers.
- **Wayland-native placement** — layer-shell anchoring, edge and alignment controls, margins, exclusive-zone handling, and per-monitor settings.
- **Flexible behavior** — auto-hide, hide on fullscreen, optional overlay stacking, and login autostart controls.
- **Graphical settings** — adjust colors, gradients, opacity, borders, shadows, radius, sizing, animations, indicators, themes, launchers, and monitor overrides with a live preview.
- **Multiple looks** — Smoky Glass, Dark, Light, macOS-inspired, Liquid Glass-inspired, Purple/Pink, and Custom themes.

## Screenshots

<!-- Add screenshots here once available. Store images in the repository (for example, `docs/screenshots/`) and embed them with Markdown image links. -->

## Requirements

- A Wayland session with `wlr-layer-shell` support.
- Python 3.9 or newer, GTK 3, PyGObject, Pycairo, and `gtk-layer-shell`.
- Sway or SwayFX is recommended. Sway IPC is used for window and running-application information.

GlassDock does not require GNOME Shell, KDE Plasma, or X11. The dock can be translucent on supported Wayland compositors; **background blur specifically requires SwayFX** and its `layer_effects` support.

## Quick installer details

The guided installer lets you install or upgrade GlassDock or GlassIcon Studio, uninstall either app, or exit without making changes.

When run from `curl | bash`, it reads input from your terminal and uses `whiptail` or `dialog` when available, falling back to a simple prompt. It keeps the source checkout in `~/.local/share/GlassDock` (or `$XDG_DATA_HOME/GlassDock`) rather than a temporary directory. If ModernDock is detected, its migration-aware installer replaces old dock links and launchers while preserving settings. Dependency installation is optional. Uninstalling preserves project directories and user settings by default. Without a terminal, the installer exits safely unless `GLASSDOCK_ACTION` is explicitly set.

For a reviewed install, inspect [installer.sh](installer.sh) before running it.

## Companion app: GlassIcon Studio

GlassIcon Studio lives in [`extras/GlassIcon/`](extras/GlassIcon/) and complements the dock by managing icon themes, per-application launcher icons, and user-level file-manager/system icon overrides. It is built with Python and GTK 3, and does not need a background service.

Install it from the repository root:

```bash
./extras/GlassIcon/install.sh
```

Add `--deps` to install its required system packages too (this may use `sudo`):

```bash
./extras/GlassIcon/install.sh --deps
```

Launch it with `glassicon`. Its settings and icon backups are kept in user directories. The main guided installer also offers install/upgrade and uninstall actions for GlassIcon Studio. See the [GlassIcon documentation](extras/GlassIcon/README.md) for its features, requirements, and limitations.

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

## Widgets and extensions

Built-in items are part of the normal dock model and can be added in **Settings → Launchers → Add other**. Clock format, seconds, calendar week start, music refresh, folder menu visibility, badge limits, and the legacy plugin allowlist are grouped within **Settings → Behavior**. Additional analog/digital clock styling, the animated folder fan, native Apps/Trash icon overrides, and advanced plugins are managed from the collapsed **Advanced widgets, fan folders, icon overrides and plugins** expander at the bottom of the existing Launchers page; these controls do not add another sidebar page.

Music controls call `playerctl` directly without a shell. Install `playerctl` and use an MPRIS-compatible player; if no player is available, controls report failure rather than pretending the action succeeded. Media commands run outside the GTK event loop.

Folder items store their directory in the main config. Clicking the item opens a small GTK folder fan; selecting a child opens it through `xdg-open`. Hidden files are filtered by default. The fan previews up to six entries; the context menu can list up to the configured popup limit. Global hotkeys remain compositor-managed, for example:

```ini
bindsym $mod+Ctrl+d exec glassdock-ctl toggle
bindsym $mod+Ctrl+1 exec glassdock-ctl launch 1
```

Right-click a configured item and choose **Set badge count…** for a manual badge. External tools can update one by setting a 1-based row index from **Settings → Launchers** (including separator rows):

```bash
glassdock-ctl badge 2 5
glassdock-ctl badge 2 0
```

The first command sets the badge to five (subject to the configured maximum); the second clears it.

### User plugins

The default plugin directory is `~/.config/glassdock/plugins/`. Copy the reviewed examples into it:

```bash
mkdir -p ~/.config/glassdock/plugins
cp plugins/*.py ~/.config/glassdock/plugins/
```

Then open **Settings → Launchers → Add other → Plugin widget…** and explicitly approve a module. Advanced plugins are configured in the **Plugins** tab in the Launchers advanced expander. The basic plugin allowlist and custom path remain available under **Settings → Behavior** for the original plugin API. Advanced plugin `CONFIG` values are schema-checked and plugin modules are only imported when explicitly enabled. Plugin code still runs with your account permissions and is **not a security sandbox**, so only approve files you have reviewed. The bundled CPU, usage, and weather examples live in `plugins/`; copy only the ones you trust. Usage data is stored locally and survives restart.

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
assets/       GlassDock icon and website assets
extras/       Optional companion tools, including GlassIcon Studio
bin/          glassdock, glassdock-settings, glassdock-ctl launchers
glassdock/    GTK dock, settings app, CLI, and core modules
scripts/      dependency, build, install, uninstall, Sway integration, and test helpers
tests/        unit tests, mock Sway IPC server, and GTK smoke test
```

## Development notes

GlassDock is Python and GTK 3 rather than a native-code application. The build helper byte-compiles the Python sources and checks runtime dependencies. The test suite covers configuration and migration, desktop entries, Sway IPC parsing, dock models and geometry, icons, and installation scripts. Actual rendering, layer-shell placement, and SwayFX blur should still be verified in your own Wayland session.

## License

MIT. See [`LICENSE`](LICENSE). Runtime dependencies are provided by your distribution and are not bundled; see [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

## Extras

- [GlassIcon Studio](extras/GlassIcon/README.md) — change icon themes, application launcher icons, and file-manager icons.


## Plugins

GlassDock plugins are single Python files managed from Settings → Extensions. Bundled, imported, store-installed and self-written plugins are treated identically. See [docs/plugins.md](docs/plugins.md) for the API, the AI prompt and the plugin-store file layout (default store: `https://plugin.mandrusia.tech`).
