<h1 align="center"><img src="assets/glassdock.svg" alt="GlassDock app icon" width="56" align="middle" />&nbsp;GlassDock</h1>

<p align="center">A dock for Wayland desktops.</p>

<p align="center"><code>curl -fsSL https://raw.githubusercontent.com/Mandrusian/GlassDock/master/installer.sh | bash</code></p>

<p align="center"><a href="https://raw.githubusercontent.com/Mandrusian/GlassDock/master/installer.sh">View installer source</a></p>

<!-- AUTO-MAINSCREENSHOTS:BEGIN -->
## Screenshots

<details>
<summary>View all 4 screenshots</summary>

<table>
<tr><td><img src="assets/mainscreenshots/about.png" alt="about" width="420"></td><td><img src="assets/mainscreenshots/iconname.png" alt="iconname" width="420"></td></tr>
<tr><td><img src="assets/mainscreenshots/liquidglass.png" alt="liquidglass" width="420"></td><td><img src="assets/mainscreenshots/themes.png" alt="themes" width="420"></td></tr>
</table>

</details>
<!-- AUTO-MAINSCREENSHOTS:END -->

## Requirements

- A Wayland session with layer-shell support.
- Python 3.9+, GTK 3, PyGObject, Pycairo, and gtk-layer-shell.
- Sway or SwayFX is recommended. Background blur requires SwayFX.

## Start

After installation:

```bash
glassdock &
glassdock-settings
glassdock-ctl status
```

## Built-in widgets and extensions

The normal dock and attached Settings app support clock, calendar, music-control, folder, badge, and trusted Python-plugin items. Add them from **Settings → Launchers → Add other**; they live in the main dock configuration, not a separate prototype directory. Extension preferences are in **Settings → Widgets & Extensions**.

Music actions use `playerctl` with an MPRIS-compatible player. User plugins are deliberately allowlisted and run as your user; they are not sandboxed. See the [advanced guide](README-advanced.md#widgets-and-extensions) before enabling plugin code.

## Manual installation

```bash
git clone https://github.com/Mandrusian/GlassDock.git
cd GlassDock
./scripts/install-deps.sh
./install.sh
```

## Other links

- [Advanced README](README-advanced.md) — setup, controls, configuration, autostart, updates, uninstalling, and troubleshooting.
- [GlassIcon Studio](extras/GlassIcon/README.md) — companion icon tool.
- [License](LICENSE)
- [Third-party notices](THIRD_PARTY_NOTICES.md)
