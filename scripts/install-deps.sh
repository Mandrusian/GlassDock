#!/usr/bin/env bash
# Install GlassDock's runtime dependencies (Fedora/Asahi, Debian/Ubuntu, Arch, openSUSE).
set -euo pipefail

if command -v dnf >/dev/null 2>&1; then
    REQUIRED=(python3 python3-gobject python3-cairo gtk3 gtk-layer-shell gobject-introspection adwaita-icon-theme)
    OPTIONAL=(fuzzel foot libnotify xdg-utils git)
    echo "==> Installing required packages (dnf): ${REQUIRED[*]}"
    sudo dnf install -y "${REQUIRED[@]}"
    echo "==> Installing optional packages (missing ones are skipped): ${OPTIONAL[*]}"
    sudo dnf install -y --skip-unavailable "${OPTIONAL[@]}" || \
        echo "Some optional packages could not be installed; GlassDock still works."
elif command -v apt-get >/dev/null 2>&1; then
    REQUIRED=(python3 python3-gi python3-gi-cairo python3-cairo gir1.2-gtk-3.0 gir1.2-gtklayershell-0.1 adwaita-icon-theme)
    echo "==> Installing required packages (apt): ${REQUIRED[*]}"
    sudo apt-get update
    sudo apt-get install -y "${REQUIRED[@]}"
    sudo apt-get install -y fuzzel foot libnotify-bin xdg-utils git || true
elif command -v pacman >/dev/null 2>&1; then
    REQUIRED=(python python-gobject python-cairo gtk3 gtk-layer-shell adwaita-icon-theme)
    echo "==> Installing required packages (pacman): ${REQUIRED[*]}"
    sudo pacman -S --needed --noconfirm "${REQUIRED[@]}"
    sudo pacman -S --needed --noconfirm fuzzel foot libnotify xdg-utils git || true
elif command -v zypper >/dev/null 2>&1; then
    REQUIRED=(python3 python3-gobject python3-gobject-Gdk python3-cairo typelib-1_0-Gtk-3_0 typelib-1_0-GtkLayerShell-0_1 adwaita-icon-theme)
    echo "==> Installing required packages (zypper): ${REQUIRED[*]}"
    sudo zypper --non-interactive install "${REQUIRED[@]}"
    sudo zypper --non-interactive install fuzzel foot libnotify-tools xdg-utils git || true
else
    echo "No supported package manager found. Install the equivalents of:" >&2
    echo "  python3 python3-gobject python3-cairo gtk3 gtk-layer-shell" >&2
    exit 1
fi

echo "==> Done. Next: ./install.sh"
