# GlassDock

A floating, macOS-inspired dock for **Wayland / Sway / SwayFX**, with a built-in graphical settings app.
Written for Fedora Asahi Remix (aarch64), works on any Fedora/x86-64 Sway session too.

- Pinned launchers + running-app indicators (via Sway IPC), grouped per application
- Hover magnification, smooth animations, launch bounce, hover name labels
- Real Wayland **layer-shell** surface (`gtk-layer-shell`): correct edge anchoring, margins, exclusive zone
- Any edge (bottom by default), start/center/end alignment, per-monitor docks and overrides
- Auto-hide (always / when a window overlaps), hide on fullscreen, optional overlay layer
- Settings app: colors, gradient, opacity, border, shadow, radius, sizes, animation, indicators,
  position, behavior, themes, launcher editor (drag to reorder), per-monitor overrides, live preview
- Themes: Smoky Glass (default), Dark, Light, macOS-inspired, Liquid Glass-inspired, Purple / Pink, Custom
- Needs no GNOME Shell, KDE or X11

## Honest notes on what it is

- **Python + GTK 3 + gtk-layer-shell.** Nothing is compiled to machine code; the "build" step byte-compiles
  the sources and verifies every dependency. This keeps it simple to run on aarch64.
- **Transparency vs blur.** The dock is always drawn translucent. **Real background blur only exists on SwayFX**:
  the *Background blur* option asks SwayFX (`layer_effects`) to blur behind the dock. On plain Sway the request is
  rejected, the dock stays translucent without blur, and the Status page says so. `scripts/sway-integration.sh check-blur`
  tells you which you have.
- **"Liquid Glass-inspired" / "macOS-inspired"** are visual styles in the spirit of those designs, not copies.
- Tested: configuration, migrations, desktop entries, Sway IPC parsing against a mock socket, dock model/geometry,
  magnification, indicators, settings-schema coverage, and the install/uninstall/Sway-integration scripts.
  **The GTK drawing code was developed without access to a Wayland session**, so rendering, layer-shell placement and
  blur must be validated on your machine. Run the tests (below) inside Sway to include the GTK smoke test.

## Install (Fedora Asahi Remix 44)

```bash
cd ~/GlassDock
./scripts/install-deps.sh      # sudo dnf install: python3-gobject, gtk3, gtk-layer-shell, ...
./install.sh                   # checks deps, links commands into ~/.local/bin, adds a Settings launcher
./scripts/run-tests.sh         # unit tests (GTK smoke test runs only inside a Wayland session)
glassdock &                   # start the dock in your Sway session
glassdock-settings            # open the settings app
```

`install.sh` runs the dock **in place** from `~/GlassDock` (nothing is copied elsewhere), so keep that folder.
Add `--deps` to also install dependencies, `--autostart` to also enable autostart.

### Autostart per window manager

`install.sh` registers GlassDock for login (an XDG autostart entry, plus the safe Sway config include when a
Sway config exists). At login the dock only starts when the current session matches
**Settings → Behavior → "Only auto-start in these sessions/WMs"** (default `sway`; comma-separated, e.g.
`sway, hyprland, niri`; `*` means every session; the master switch is "Start GlassDock automatically at login").
For compositors that do not run XDG autostart, add `glassdock --autostart` to their startup, for example
Hyprland `exec-once = glassdock --autostart`, niri `spawn-at-startup "glassdock" "--autostart"`.

### Publish to GitHub

```bash
scripts/publish.sh              # needs `gh auth login` once; creates github.com/<you>/glassdock and pushes
scripts/publish.sh --private    # private repo
scripts/publish.sh --owner you  # without gh: sets origin to git@github.com:you/glassdock.git and pushes
```

### Manual Sway autostart (optional)

```bash
~/GlassDock/scripts/sway-integration.sh enable-autostart
swaymsg reload
```

This adds one marked `include` block to your Sway config (a timestamped backup is made first, the result is
validated with `sway --validate`, and your original is restored automatically if Sway rejects it).
Undo with `sway-integration.sh disable-autostart`.

## Using it

| Action | Result |
|---|---|
| Click | Launch, or focus the app's window (click again to cycle its windows) |
| Middle-click / Shift+click | Open a new window / instance |
| Drag an icon along the dock | Reorder pinned items (a marker shows where it will land); an open Settings window follows live |
| Right-click | Window list, New Window, app actions, Keep in / Remove from Dock, Close All, Settings, Quit |
| `glassdock-ctl toggle` | Show/hide (bind to a key; see below) |
| `glassdock-ctl launch N` | Activate the Nth item |

Handy Sway keybindings (also written, commented out, to `~/.config/glassdock/sway.conf`):

```
bindsym $mod+Ctrl+d exec glassdock-ctl toggle
bindsym $mod+Ctrl+1 exec glassdock-ctl launch 1
```

`glassdock-ctl` commands: `ping`, `status`, `reload`, `toggle`, `show`, `hide`, `auto`, `launch N`, `quit`.

## Configuration

Settings are stored in `~/.config/glassdock/config.json` (validated and migrated on load; unknown or invalid
values fall back to defaults). Edits made by the settings app apply live; hand edits are picked up automatically.
Reset one setting or everything from the settings app.

## Update

Extract the new ZIP over a fresh `~/GlassDock` (keep a backup of the old folder), then re-run `./scripts/install.sh`.
Your settings live in `~/.config/glassdock` and are unaffected.

## Uninstall

```bash
~/GlassDock/scripts/uninstall.sh            # remove links, launcher, autostart; keeps your settings
~/GlassDock/scripts/uninstall.sh --purge    # also remove settings (a .tar.gz backup is made first)
rm -rf ~/GlassDock                          # the program folder itself is never deleted for you
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `GtkLayerShell typelib not found` | `sudo dnf install gtk-layer-shell python3-gobject` (or `./scripts/install-deps.sh`) |
| `This compositor does not support wlr-layer-shell` | Run inside Sway/SwayFX on Wayland. If `GDK_BACKEND=x11` is set, `unset GDK_BACKEND` |
| Dock appears as a normal window / wrong place | The launcher preloads `libgtk-layer-shell` automatically; if you start `python3 -m glassdock.dock` yourself use `LD_PRELOAD=/usr/lib64/libgtk-layer-shell.so.0` |
| `GlassDock is already running` | `glassdock-ctl quit`, then start again |
| No running-app indicators | `glassdock-ctl status` must show `"sway_ipc": true`. Needs `SWAYSOCK` (start from inside Sway) |
| Blur does nothing | You are on plain Sway; blur needs SwayFX (`sway-integration.sh check-blur`). After `swaymsg reload` run `glassdock-ctl reload` |
| Icon is a coloured letter tile | The app's icon isn't in your icon theme; install an icon theme or set one in the desktop entry |
| "Applications" button does nothing | Set *Applications button command* in Settings → Behavior (default `fuzzel`; install it or use e.g. `wmenu-run`) |
| Dock hidden behind fullscreen app | Settings → Behavior → Stacking layer = Overlay, and turn off *Hide while fullscreen* |
| Nothing at all | Run `glassdock` in a terminal; errors are printed there. Open an issue with the output and `glassdock-ctl status` |

## Layout

```
bin/        glassdock, glassdock-settings, glassdock-ctl (launchers)
glassdock/ dock.py (GTK dock), settings.py (GTK settings), ctl.py
  core/     config (schema, defaults, migration), themes, colors, desktop entries, sway IPC, model, control socket
scripts/    install-deps, build, install, uninstall, sway-integration, run-tests
tests/      unit tests (+ mock Sway IPC server), GTK smoke test
assets/     icon
```

## License

MIT, see `LICENSE`. Runtime dependencies are installed from Fedora, not bundled; see `THIRD_PARTY_NOTICES.md`.
