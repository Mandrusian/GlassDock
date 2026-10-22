#!/usr/bin/env bash
# Install ModernDock's runtime dependencies on Fedora (incl. Fedora Asahi Remix).
set -euo pipefail

if ! command -v dnf >/dev/null 2>&1; then
    echo "dnf not found. This script targets Fedora; install the equivalents of:" >&2
    echo "  python3 python3-gobject python3-cairo gtk3 gtk-layer-shell" >&2
    exit 1
fi

REQUIRED=(python3 python3-gobject python3-cairo gtk3 gtk-layer-shell gobject-introspection adwaita-icon-theme)
# fuzzel: default "Applications" button; foot: default terminal for terminal apps;
# libnotify: launch-error notifications; zip/unzip: handy for updates.
OPTIONAL=(fuzzel foot libnotify xdg-utils unzip zip)

echo "==> Installing required packages: ${REQUIRED[*]}"
sudo dnf install -y "${REQUIRED[@]}"

echo "==> Installing optional packages (missing ones are skipped): ${OPTIONAL[*]}"
sudo dnf install -y --skip-unavailable "${OPTIONAL[@]}" || \
    echo "Some optional packages could not be installed; ModernDock still works."

echo "==> Done. Next: ./scripts/build.sh"
