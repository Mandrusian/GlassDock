#!/usr/bin/env bash
# Safely uninstall GlassDock's integration. Removes only what install.sh and
# sway-integration.sh created; never deletes this directory.
#
#   ./scripts/uninstall.sh           stop the dock, remove links/launcher/autostart
#   ./scripts/uninstall.sh --purge   additionally remove ~/.config/glassdock
#                                    (a .tar.gz backup is made first)
set -euo pipefail

ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
BIN_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"
APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
CONF_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/glassdock"
AUTOSTART_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/autostart"
PURGE=0

for arg in "$@"; do
    case "$arg" in
        --purge) PURGE=1 ;;
        -h|--help) sed -n '2,8p' "${BASH_SOURCE[0]}"; exit 0 ;;
        *) echo "unknown option: $arg" >&2; exit 2 ;;
    esac
done

echo "==> Stopping the dock (if running)"
"$ROOT/bin/glassdock-ctl" quit >/dev/null 2>&1 || true

echo "==> Removing Sway autostart (if enabled)"
"$ROOT/scripts/sway-integration.sh" disable-autostart || true

echo "==> Removing command links that point into $ROOT"
for cmd in glassdock glassdock-ctl glassdock-settings; do
    target="$BIN_DIR/$cmd"
    if [ -L "$target" ] && [ "$(readlink -f "$target")" = "$ROOT/bin/$cmd" ]; then
        rm -f "$target"
        echo "  removed $target"
    fi
done

echo "==> Removing the Settings launcher"
rm -f "$APP_DIR/glassdock-settings.desktop" "$AUTOSTART_DIR/glassdock.desktop"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APP_DIR" 2>/dev/null || true

if [ "$PURGE" = 1 ] && [ -d "$CONF_DIR" ]; then
    backup="$HOME/glassdock-config-backup-$(date +%Y%m%d-%H%M%S).tar.gz"
    tar -czf "$backup" -C "$(dirname "$CONF_DIR")" "$(basename "$CONF_DIR")"
    rm -rf -- "$CONF_DIR"
    echo "==> Removed $CONF_DIR (backup: $backup)"
else
    echo "==> Your settings in $CONF_DIR were kept (use --purge to remove them)."
fi

echo
echo "Done. This directory was NOT deleted. To remove it as well:"
echo "  rm -rf \"$ROOT\""
