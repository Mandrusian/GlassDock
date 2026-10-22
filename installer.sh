#!/usr/bin/env bash
set -Eeuo pipefail
REPO="Mandrusian/GlassDock"
BRANCH="master"
BIN="${XDG_BIN_HOME:-$HOME/.local/bin}"
CONF="${XDG_CONFIG_HOME:-$HOME/.config}"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
DEST="${GLASSDOCK_INSTALL_DIR:-$DATA/GlassDock}"
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
has_glassicon() {
 [ -e "$BIN/glassicon" ] || [ -L "$BIN/glassicon" ] ||
 [ -e "$APP/glassicon.desktop" ]
}

menu() {
 printf '\n\033[1;37m  GlassDock Setup\033[0m\n  ────────────────────────────────────\n'
 if has_moderndock; then warn "ModernDock detected — install will migrate it to GlassDock."
 elif has_glassdock; then info "Existing GlassDock installation detected."
 else printf 'A floating dock and icon tools for Wayland.\n'; fi
 if has_glassicon; then info "GlassIcon Studio installation detected."; fi
 if command -v whiptail >/dev/null 2>&1 && [ -r /dev/tty ] && [ -w /dev/tty ]; then
  CHOICE="$(whiptail --title 'GlassDock Setup' --menu 'Choose an action' 18 68 5 \
    install 'Install / Upgrade GlassDock' \
    glassicon 'Install / Upgrade GlassIcon Studio' \
    uninstall 'Uninstall GlassDock / ModernDock' \
    uninstall-glassicon 'Uninstall GlassIcon Studio' \
    quit 'Exit without changes' </dev/tty 3>&1 1>&2 2>&3)" || CHOICE=quit
 elif command -v dialog >/dev/null 2>&1 && [ -r /dev/tty ] && [ -w /dev/tty ]; then
  CHOICE="$(dialog --title 'GlassDock Setup' --menu 'Choose an action' 18 68 5 \
    install 'Install / Upgrade GlassDock' \
    glassicon 'Install / Upgrade GlassIcon Studio' \
    uninstall 'Uninstall GlassDock / ModernDock' \
    uninstall-glassicon 'Uninstall GlassIcon Studio' \
    quit 'Exit without changes' </dev/tty 3>&1 1>&2 2>&3)" || CHOICE=quit
 elif [ -r /dev/tty ] && [ -w /dev/tty ]; then
  printf '\n  1) Install / Upgrade GlassDock\n  2) Install / Upgrade GlassIcon Studio\n  3) Uninstall GlassDock / ModernDock\n  4) Uninstall GlassIcon Studio\n  5) Exit\n'
  read -r -p 'Choose [1-5]: ' a </dev/tty
  case "$a" in 1) CHOICE=install;; 2) CHOICE=glassicon;; 3) CHOICE=uninstall;; 4) CHOICE=uninstall-glassicon;; *) CHOICE=quit;; esac
 else
  CHOICE="${GLASSDOCK_ACTION:-}"
  case "$CHOICE" in install|glassicon|uninstall|uninstall-glassicon|quit) warn "No terminal attached; using GLASSDOCK_ACTION=$CHOICE";;
   *) die "No interactive terminal was found. Run this from a terminal, or set GLASSDOCK_ACTION=install|glassicon|uninstall|uninstall-glassicon explicitly.";;
  esac
 fi
}
fetch_source() {
 mkdir -p "$DATA"
 if [ -e "$DEST" ]; then
  if ! command -v git >/dev/null 2>&1 || ! git -C "$DEST" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
   die "$DEST already exists and is not a Git checkout. Move it, or set GLASSDOCK_INSTALL_DIR to another path."
  fi
  local origin
  origin="$(git -C "$DEST" remote get-url origin 2>/dev/null || true)"
  case "$origin" in *github.com/$REPO*) ;; *) die "$DEST is a Git checkout, but its origin is not the GlassDock repository.";; esac
  if [ -n "$(git -C "$DEST" status --porcelain)" ]; then
   die "The existing checkout at $DEST has local changes. Commit/stash them or set GLASSDOCK_INSTALL_DIR to a fresh path."
  fi
  info "Updating existing GlassDock checkout at $DEST…"
  git -C "$DEST" fetch --depth 1 origin "$BRANCH"
  git -C "$DEST" checkout -B "$BRANCH" "origin/$BRANCH"
  return
 fi
 info "Downloading $REPO into persistent directory $DEST…"
 if command -v git >/dev/null 2>&1; then
  git clone --depth 1 --branch "$BRANCH" "https://github.com/$REPO.git" "$DEST" >&2 || die "Git clone failed."
 else
  command -v curl >/dev/null 2>&1 || die "Install git or curl first."
  TMP="$(mktemp -d "${TMPDIR:-/tmp}/glassdock-setup.XXXXXX")"
  curl -fLsS "https://github.com/$REPO/archive/refs/heads/$BRANCH.tar.gz" -o "$TMP/source.tar.gz" || die "Download failed."
  mkdir "$TMP/unpack"; tar -xzf "$TMP/source.tar.gz" -C "$TMP/unpack"
  local src
  src="$(find "$TMP/unpack" -mindepth 1 -maxdepth 1 -type d -name 'GlassDock-*' -print -quit)"
  [ -n "$src" ] || die "The downloaded archive did not contain the expected GlassDock source folder."
  mv "$src" "$DEST"
 fi
}
install_dock() {
 fetch_source
 local root="$DEST"
 if has_moderndock; then
  printf '\nModernDock detected. GlassDock will replace the old command links and launchers; settings will be preserved for migration.\n'
 fi
 local deps=n
 if [ -r /dev/tty ] && [ -w /dev/tty ]; then
  read -r -p 'Install system dependencies too? (may use sudo) [y/N]: ' deps </dev/tty
 else
  deps="${GLASSDOCK_INSTALL_DEPS:-n}"
 fi
 if [[ "$deps" =~ ^[Yy]$ ]]; then "$root/scripts/install-deps.sh"; fi
 info "Checking dependencies and installing…"
 "$root/scripts/install.sh"
 ok "GlassDock installed in $root."
 printf '\nStart:    glassdock &\nSettings: glassdock-settings\nStatus:   glassdock-ctl status\n'
}
install_glassicon() {
 fetch_source
 local root="$DEST/extras/GlassIcon"
 [ -x "$root/install.sh" ] || die "GlassIcon Studio was not found at $root/install.sh in the downloaded checkout."
 printf '\nGlassIcon Studio manages icon themes, launcher icons, and user-level file-manager icons.\n'
 local deps=n
 if [ -r /dev/tty ] && [ -w /dev/tty ]; then
  read -r -p 'Install GlassIcon system dependencies too? (may use sudo) [y/N]: ' deps </dev/tty
 else
  deps="${GLASSDOCK_INSTALL_DEPS:-n}"
 fi
 if [[ "$deps" =~ ^[Yy]$ ]]; then "$root/install.sh" --deps; else "$root/install.sh"; fi
 ok "GlassIcon Studio installed."
 printf '\nLaunch: glassicon\nSettings and backups stay in your user directories.\n'
}
uninstall_glassicon() {
 local linked_root=""
 if [ -L "$BIN/glassicon" ]; then
  local resolved
  resolved="$(readlink -f -- "$BIN/glassicon" 2>/dev/null || true)"
  case "$resolved" in */extras/GlassIcon/bin/glassicon) linked_root="${resolved%/bin/glassicon}";; esac
 fi
 if [ -n "$linked_root" ] && [ -x "$linked_root/uninstall.sh" ]; then
  "$linked_root/uninstall.sh"
  ok "GlassIcon Studio launcher removed; settings and icon overrides were preserved."
  return
 fi
 fetch_source
 local root="$DEST/extras/GlassIcon"
 [ -x "$root/uninstall.sh" ] || die "GlassIcon uninstaller was not found at $root/uninstall.sh."
 "$root/uninstall.sh"
 ok "GlassIcon Studio launcher removed; settings and icon overrides were preserved."
}

uninstall_dock() {
 if ! has_glassdock && ! has_moderndock; then warn "No obvious installation detected."; fi
 printf '\nThis removes known command links and launchers; project folders are not deleted.\n'
 local purge=n
 if [ -r /dev/tty ] && [ -w /dev/tty ]; then read -r -p 'Also remove saved settings after making backups? [y/N]: ' purge </dev/tty
 else purge="${GLASSDOCK_PURGE_CONFIG:-n}"; fi
 for name in glassdock glassdock-ctl glassdock-settings moderndock moderndock-ctl moderndock-settings; do
  target="$BIN/$name"
  if [ -L "$target" ]; then
   resolved="$(readlink -f "$target" 2>/dev/null || true)"
   case "$resolved" in *GlassDock*|*ModernDock*|*glassdock*|*moderndock*) rm -f -- "$target"; ok "Removed $target";; esac
  fi
 done
 rm -f -- "$APP/glassdock-settings.desktop" "$APP/moderndock-settings.desktop" "$AUTO/glassdock.desktop" "$AUTO/moderndock.desktop"
 for root in "$DEST" "$HOME/GlassDock" "$HOME/ModernDock"; do
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
case "$CHOICE" in
 install) install_dock;;
 glassicon) install_glassicon;;
 uninstall) uninstall_dock;;
 uninstall-glassicon) uninstall_glassicon;;
 *) printf 'No changes made.\n';;
esac
