# Third-party notices

ModernDock's source code is original and contains no code copied from other projects.
It **uses** the following software at runtime. None of it is bundled in this archive;
it is installed from the Fedora repositories by `scripts/install-deps.sh`, and remains
under its own license.

| Component | Used for | License |
|---|---|---|
| GTK 3 / GDK / GdkPixbuf | UI toolkit, icon loading | LGPL-2.1-or-later |
| PyGObject (python3-gobject) | Python bindings for GTK | LGPL-2.1-or-later |
| pycairo (python3-cairo) | Drawing | LGPL-2.1 / MPL-1.1 |
| Pango / PangoCairo | Text rendering | LGPL-2.0-or-later |
| gtk-layer-shell | Wayland layer-shell surfaces | MIT |
| Sway / SwayFX | Compositor; IPC protocol and `layer_effects` (not bundled) | MIT |

Optional, not required: fuzzel (default "Applications" button command, MIT), foot (terminal, MIT),
libnotify (`notify-send` launch-error notifications, LGPL-2.1).

"macOS" and "Liquid Glass" are trademarks of Apple Inc. The themes with these names are original
styles *inspired by* those designs; ModernDock is not affiliated with or endorsed by Apple.
