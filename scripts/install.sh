#!/usr/bin/env bash
# Install ModernDock for the current user. Runs in place from this directory:
# nothing is copied system-wide and no root access is needed (except the
# optional --deps step, which uses sudo dnf).
#
#   ./scripts/install.sh             link commands, add the Settings launcher
#   ./scripts/install.sh --deps      also install Fedora dependencies first
#   ./scripts/install.sh --autostart also enable autostart in your Sway config
#   ./scripts/install.sh --no-check  skip the dependency check (packaging/CI only)
set -euo pipefail

ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
BIN_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"
APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
DO_DEPS=0
DO_AUTOSTART=0
NO_CHECK=0

for arg in "$@"; do
    case "$arg" in
        --deps) DO_DEPS=1 ;;
        --autostart) DO_AUTOSTART=1 ;;
        --no-check) NO_CHECK=1 ;;
        -h|--help) sed -n '2,11p' "${BASH_SOURCE[0]}"; exit 0 ;;
        *) echo "unknown option: $arg" >&2; exit 2 ;;
    esac
done

if [ "$(id -u)" -eq 0 ] && [ -z "${MODERNDOCK_ALLOW_ROOT:-}" ]; then
    echo "Run this as your normal user, not root." >&2
    exit 1
fi

chmod +x "$ROOT"/bin/* "$ROOT"/scripts/*.sh

if [ "$DO_DEPS" = 1 ]; then
    "$ROOT/scripts/install-deps.sh"
fi

if [ "$NO_CHECK" = 0 ]; then
    echo "==> Checking build and dependencies"
    "$ROOT/scripts/build.sh"
fi

echo "==> Linking commands into $BIN_DIR"
mkdir -p "$BIN_DIR"
for cmd in moderndock moderndock-ctl moderndock-settings; do
    target="$BIN_DIR/$cmd"
    if [ -e "$target" ] && [ ! -L "$target" ]; then
        echo "  skipping $target: a regular file already exists there" >&2
        continue
    fi
    ln -sfn "$ROOT/bin/$cmd" "$target"
    echo "  $target -> $ROOT/bin/$cmd"
done

echo "==> Adding the Settings launcher"
mkdir -p "$APP_DIR"
cat >"$APP_DIR/moderndock-settings.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=ModernDock Settings
Comment=Customize the ModernDock dock
Exec="$ROOT/bin/moderndock-settings"
Icon=$ROOT/assets/moderndock.svg
Terminal=false
Categories=Settings;DesktopSettings;GTK;
Keywords=dock;panel;launcher;
EOF
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APP_DIR" 2>/dev/null || true

if [ "$DO_AUTOSTART" = 1 ]; then
    echo "==> Enabling autostart"
    "$ROOT/scripts/sway-integration.sh" enable-autostart
fi

case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *) echo "NOTE: $BIN_DIR is not on your PATH in this shell. Add it with:"
       echo "      echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc" ;;
esac

cat <<EOF

Installed. Try it:
  moderndock &            # start the dock (inside your Sway session)
  moderndock-settings     # open the settings app
  moderndock-ctl status   # ask the running dock how it is doing

Autostart with Sway (optional, after you have verified it works):
  $ROOT/scripts/sway-integration.sh enable-autostart
EOF
