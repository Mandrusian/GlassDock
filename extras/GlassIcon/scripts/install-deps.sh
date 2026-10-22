#!/usr/bin/env bash
set -euo pipefail

if command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y python3 python3-gobject gtk3 adwaita-icon-theme
elif command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y python3 python3-gi gir1.2-gtk-3.0 adwaita-icon-theme
elif command -v pacman >/dev/null 2>&1; then
    sudo pacman -S --needed --noconfirm python gtk3 python-gobject adwaita-icon-theme
elif command -v zypper >/dev/null 2>&1; then
    sudo zypper --non-interactive install python3 python3-gobject python3-gobject-Gdk typelib-1_0-Gtk-3_0 libgtk-3-0 adwaita-icon-theme
elif command -v xbps-install >/dev/null 2>&1; then
    sudo xbps-install -S python3 python3-gobject gtk+3 adwaita-icon-theme
else
    printf '%s\n' 'Unsupported package manager. Install Python 3, GTK 3, and PyGObject from your distribution, then run ./scripts/build.sh and ./install.sh.' >&2
    exit 1
fi
printf '\n%s\n' 'Dependencies installed. Run ./scripts/build.sh, then ./install.sh.'
