#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "$(readlink -f -- "${BASH_SOURCE[0]}")")" && pwd)"
BIN_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"
DESKTOP="${XDG_DATA_HOME:-$HOME/.local/share}/applications/glassicon.desktop"
if [ -L "$BIN_DIR/glassicon" ] && [ "$(readlink -f -- "$BIN_DIR/glassicon")" = "$ROOT/bin/glassicon" ]; then
    rm -- "$BIN_DIR/glassicon"
    printf 'Removed %s\n' "$BIN_DIR/glassicon"
fi
if [ -f "$DESKTOP" ] && grep -Fq "$ROOT/assets/glassicon.svg" "$DESKTOP"; then
    rm -- "$DESKTOP"
    printf 'Removed %s\n' "$DESKTOP"
fi
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$(dirname -- "$DESKTOP")" 2>/dev/null || true
printf '\n%s\n' 'GlassIcon Studio launcher removed. Icon theme selections, custom theme files, and backups were kept so your desktop is not unexpectedly changed.'
