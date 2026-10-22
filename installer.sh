#!/usr/bin/env bash
set -Eeuo pipefail
REPO="Mandrusian/GlassDock"
BRANCH="master"
BIN="${XDG_BIN_HOME:-$HOME/.local/bin}"
CONF="${XDG_CONFIG_HOME:-$HOME/.config}"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
APP="$DATA/applications"
AUTO="$CONF/autostart"
TMP=""
trap '[ -z "$TMP" ] || rm -rf -- "$TMP"' EXIT
die() { printf '\033[1;31mError:\033[0m %s\n' "$*" >&2; exit 1; }
info() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
ok() { printf '\033[1;32m✓\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!\033[0m %s\n' "$*"; }
[ "$(id -u)" -ne 0 ] || die "Run as your normal user, not root."

has_glassdock() {
 [ -e "$BIN/glassdock" ] || [ -L "$BIN/glassdock" ] ||
 [ -e "$APP/glassdock-settings.desktop" ] || [ -e "$AUTO/glassdock.desktop" ] ||
 [ -d "$CONF/glassdock" ] || pgrep -u "$(id -u)" -f 'glassdock\.dock' >/dev/null 2>&1
}
has_moderndock() {
 [ -e "$BIN/moderndock" ] || [ -L "$BIN/moderndock" ] ||
 [ -e "$BIN/moderndock-ctl" ] || [ -L "$BIN/moderndock-ctl" ] ||
 [ -e "$APP/moderndock-settings.desktop" ] || [ -e "$AUTO/moderndock.desktop" ] ||
 [ -d "$CONF/moderndock" ] || [ -d "$HOME/ModernDock" ] ||
 pgrep -u "$(id -u)" -f 'moderndock\.' >/dev/null 2>&1
}
menu() {
 printf '\n\033[1;37m  GlassDock Setup\033[0m\n  ────────────────────────────────────\n'
 if has_moderndock; then warn "ModernDock detected — install will migrate it to GlassDock."
 elif has_glassdock; then info "Existing GlassDock installation detected."
 else printf 'A floating glass-style dock for Wayland.\n'; fi
 if command -v whiptail >/dev/null 2>&1 && [ -t 0 ] && [ -t 1 ]; then
  CHOICE="$(whiptail --title 'GlassDock Setup' --menu 'Choose an action' 16 62 3 install 'Install / Upgrade GlassDock' uninstall 'Uninstall GlassDock / ModernDock' quit 'Exit without changes' 3>&1 1>&2 2>&3)" || CHOICE=quit
 elif command -v dialog >/dev/null 2>&1 && [ -t 0 ] && [ -t 1 ]; then
  CHOICE="$(dialog --title 'GlassDock Setup' --menu 'Choose an action' 16 62 3 install 'Install / Upgrade GlassDock' uninstall 'Uninstall GlassDock / ModernDock' quit 'Exit without changes' 3>&1 1>&2 2>&3)" || CHOICE=quit
 else
  printf '\n  1) Install / Upgrade GlassDock\n  2) Uninstall GlassDock / ModernDock\n  3) Exit\n'
  if [ ! -t 0 ]; then CHOICE="${GLASSDOCK_ACTION:-install}"; warn "Non-interactive mode: $CHOICE"
  else read -r -p 'Choose [1-3]: ' a; case "$a" in 1) CHOICE=install;; 2) CHOICE=uninstall;; *) CHOICE=quit;; esac; fi
 fi
}
fetch_source() {
 TMP="$(mktemp -d "${TMPDIR:-/tmp}/glassdock-setup.XXXXXX")"
 info "Downloading $REPO…"
 if command -v git >/dev/null 2>&1; then
  git clone --depth 1 --branch "$BRANCH" "https://github.com/$REPO.git" "$TMP/GlassDock" >&2 || die "Git clone failed."
 else
  command -v curl >/dev/null 2>&1 || die "Install git or curl first."
  curl -fLsS "https://github.com/$REPO/archive/refs/heads/$BRANCH.tar.gz" -o "$TMP/source.tar.gz"
  mkdir "$TMP/unpack"; tar -xzf "$TMP/source.tar.gz" -C "$TMP/unpack"
  mv "$TMP/unpack/GlassDock-$BRANCH" "$TMP/GlassDock"
 fi
}
install_dock() {
 fetch_source
 local root="$TMP/GlassDock"
 if has_moderndock; then
  printf '\nModernDock detected. The GlassDock installer replaces old command links and launchers; settings are preserved for migration.\n'
 fi
 local deps=n
 if [ -t 0 ]; then read -r -p 'Install system dependencies too? (may use sudo) [y/N]: ' deps
 else deps="${GLASSDOCK_INSTALL_DEPS:-n}"; fi
 [[ "$deps" =~ ^[Yy]$ ]] && "$root/scripts/install-deps.sh"
 info "Checking dependencies and installing…"
 "$root/scripts/install.sh"
 ok "GlassDock installed."
 printf '\nStart:    glassdock &\nSettings: glassdock-settings\nStatus:   glassdock-ctl status\n'
}
uninstall_dock() {
 if ! has_glassdock && ! has_moderndock; then warn "No obvious installation detected."; fi
 printf '\nThis removes known command links and launchers; project folders are not deleted.\n'
 local purge=n
 if [ -t 0 ]; then read -r -p 'Also remove saved settings after making backups? [y/N]: ' purge
 else purge="${GLASSDOCK_PURGE_CONFIG:-n}"; fi
 for name in glassdock glassdock-ctl glassdock-settings moderndock moderndock-ctl moderndock-settings; do
  target="$BIN/$name"
  if [ -L "$target" ]; then
   resolved="$(readlink -f "$target" 2>/dev/null || true)"
   case "$resolved" in *GlassDock*|*ModernDock*|*glassdock*|*moderndock*) rm -f -- "$target"; ok "Removed $target";; esac
  fi
 done
 rm -f -- "$APP/glassdock-settings.desktop" "$APP/moderndock-settings.desktop" "$AUTO/glassdock.desktop" "$AUTO/moderndock.desktop"
 for root in "$HOME/GlassDock" "$HOME/ModernDock"; do
  if [ -x "$root/scripts/uninstall.sh" ]; then "$root/scripts/uninstall.sh" || true; fi
 done
 if [[ "$purge" =~ ^[Yy]$ ]]; then
  for cfg in "$CONF/glassdock" "$CONF/moderndock"; do
   if [ -d "$cfg" ]; then
    backup="$HOME/$(basename "$cfg")-backup-$(date +%Y%m%d-%H%M%S).tar.gz"
    tar -czf "$backup" -C "$(dirname "$cfg")" "$(basename "$cfg")"
    rm -rf -- "$cfg"; ok "Removed settings; backup: $backup"
   fi
  done
 else info "Settings preserved."; fi
 ok "Cleanup complete. Project directories were preserved."
}
menu
case "$CHOICE" in install) install_dock;; uninstall) uninstall_dock;; *) printf 'No changes made.\n';; esac
