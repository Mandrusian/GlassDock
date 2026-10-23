<h1 align="center"><img src="assets/glassdock.svg" alt="GlassDock app icon" width="56" align="middle" />&nbsp;GlassDock</h1>

<p align="center">A dock for Wayland desktops.</p>

<p align="center"><code>curl -fsSL https://raw.githubusercontent.com/Mandrusian/GlassDock/master/installer.sh | bash</code></p>

<p align="center"><a href="https://raw.githubusercontent.com/Mandrusian/GlassDock/master/installer.sh">View installer source</a></p>

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

## Screenshots

<details>
<summary>View screenshots</summary>

<table>
<tr>
<td><img src="assets/desktop.png" alt="Desktop screenshot" width="420"></td>
<td><img src="assets/themes.png" alt="Available themes" width="420"></td>
</tr>
<tr>
<td><img src="assets/liquidglass.png" alt="Liquid Glass appearance" width="420"></td>
<td><img src="assets/zoomed.png" alt="Magnified dock" width="420"></td>
</tr>
<tr>
<td><img src="assets/iconname.png" alt="Application icon names" width="420"></td>
<td><img src="assets/about.png" alt="About dialog" width="420"></td>
</tr>
</table>

</details>

