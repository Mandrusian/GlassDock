#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "$(readlink -f -- "${BASH_SOURCE[0]}")")" && pwd)"
BIN_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
DO_DEPS=0

for arg in "$@"; do
    case "$arg" in
        --deps) DO_DEPS=1 ;;
        -h|--help) printf '%s\n' 'Usage: ./install.sh [--deps]' '  --deps  install GTK 3 and Python bindings with the supported package manager'; exit 0 ;;
        *) printf 'Unknown option: %s\n' "$arg" >&2; exit 2 ;;
    esac
done

if [ "$(id -u)" -eq 0 ]; then
    printf '%s\n' 'Run this as your normal user; only dependency installation may use sudo.' >&2
    exit 1
fi
chmod +x "$ROOT/bin/glassicon" "$ROOT/scripts/"*.sh "$ROOT/install.sh"
if [ "$DO_DEPS" -eq 1 ]; then
    "$ROOT/scripts/install-deps.sh"
fi
"$ROOT/scripts/build.sh"
mkdir -p "$BIN_DIR" "$DATA_HOME/applications"
if [ -e "$BIN_DIR/glassicon" ] || [ -L "$BIN_DIR/glassicon" ]; then
    if [ ! -L "$BIN_DIR/glassicon" ] || [ "$(readlink -f -- "$BIN_DIR/glassicon" 2>/dev/null || true)" != "$ROOT/bin/glassicon" ]; then
        printf 'Refusing to replace an existing command: %s\n' "$BIN_DIR/glassicon" >&2
        exit 1
    fi
fi
DESKTOP_FILE="$DATA_HOME/applications/glassicon.desktop"
if [ -e "$DESKTOP_FILE" ] || [ -L "$DESKTOP_FILE" ]; then
    if [ ! -f "$DESKTOP_FILE" ] || [ -L "$DESKTOP_FILE" ] || ! grep -Fq "$ROOT/assets/glassicon.svg" "$DESKTOP_FILE"; then
        printf 'Refusing to replace an existing desktop entry: %s\n' "$DESKTOP_FILE" >&2
        exit 1
    fi
fi
ln -sfn "$ROOT/bin/glassicon" "$BIN_DIR/glassicon"
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=GlassIcon Studio
GenericName=Icon Theme Manager
Comment=Customize application and system icons
Exec="$BIN_DIR/glassicon"
Icon=$ROOT/assets/glassicon.svg
Terminal=false
Categories=Settings;DesktopSettings;Utility;GTK;
Keywords=icons;icon theme;thunar;launcher;glassdock;
EOF
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$DATA_HOME/applications" 2>/dev/null || true
case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *) printf 'Note: add %s to PATH to launch with the command glassicon.\n' "$BIN_DIR" ;;
esac
printf '\n%s\n' 'GlassIcon Studio installed.' "Launch with: $BIN_DIR/glassicon" 'Your icon backups and theme state stay in your home directory.'
