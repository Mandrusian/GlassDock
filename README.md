<h1 align="center"><img src="assets/glassdock.svg" alt="GlassDock app icon" width="56" align="middle" />&nbsp;GlassDock</h1>

<p align="center">A dock for Wayland desktops, with a separate experimental X11 backend for i3.</p>

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

GlassDock's normal dock and Settings app include clock, calendar, music-control, folder, badge, and trusted user-plugin items. Add or reorder them in **Settings → Launchers → Add other**; the options are part of the main app and config format.

- **Clock and calendar:** native dock icons, configurable time format/seconds, and a calendar popup.
- **Music:** play/pause from the dock, with previous/next/stop in the right-click menu. Requires `playerctl` and an MPRIS-compatible player.
- **Folders:** choose a directory in Settings; click its icon to browse children, or open it in your file manager. Hidden-file visibility and menu limits are configurable.
- **Badges:** right-click a pinned item and choose **Set badge count…**. Other applications may set a badge through `glassdock-ctl badge INDEX COUNT` (INDEX is the 1-based row in Settings → Launchers; 0 clears the badge).
- **Trusted plugins:** install reviewed Python modules in `~/.config/glassdock/plugins/`, list their module names in **Settings → Widgets & Extensions → Allowed plugin module names**, then add them as items. Example plugins are in `examples/plugins/`. Plugins execute with your user's permissions and are not sandboxed.
- **Compositor hotkeys:** Wayland compositors own global shortcuts; bind them to `glassdock-ctl toggle`, `show`, `hide`, `launch N`, or other supported commands.

## X11 / i3 (experimental)

For i3 and other X11 sessions, use the standalone backend in [`x11-support/`](x11-support/README.md). It does not require GTK introspection or gtk-layer-shell:

```bash
python -m pip install --user python-xlib
python x11-support/glassdock-x11.py
```

This is a separate starter backend with configurable text launchers and EWMH dock placement; it is not yet a full feature-for-feature port of the Wayland dock.

## Manual installation

```bash
git clone https://github.com/Mandrusian/GlassDock.git
cd GlassDock
./scripts/install-deps.sh
./install.sh
```

## Other links

- [X11 / i3 support](x11-support/README.md) — standalone experimental X11 backend.
- [Advanced README](README-advanced.md) — setup, controls, configuration, autostart, updates, uninstalling, and troubleshooting.
- [GlassIcon Studio](extras/GlassIcon/README.md) — companion icon tool.
- [License](LICENSE)
- [Third-party notices](THIRD_PARTY_NOTICES.md)


-----------------------------------------------------------------------------------------------------------------------------------
<p align="center"><img src="https://github.com/user-attachments/assets/7c054541-2a65-477d-9f87-c70fa5d8e190" alt="glassdockbanner" width="250" /></p>
