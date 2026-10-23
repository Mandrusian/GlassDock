#!/usr/bin/env bash
# GlassDock installer: interactive, re-runnable, and careful with your files.
#
#   curl -fsSL https://raw.githubusercontent.com/Mandrusian/GlassDock/master/installer.sh | bash
#   curl -fsSL .../installer.sh | bash -s -- --help
#
# It never deletes or overwrites your work silently: dirty checkouts, local
# commits, odd folders and wrong remotes each get a menu of safe choices.
set -Eeuo pipefail

REPO="Mandrusian/GlassDock"
REPO_URL="${GLASSDOCK_REPO_URL:-https://github.com/$REPO.git}"
BRANCH="${GLASSDOCK_BRANCH:-master}"
BIN="${XDG_BIN_HOME:-$HOME/.local/bin}"
CONF="${XDG_CONFIG_HOME:-$HOME/.config}"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
STATE="${XDG_STATE_HOME:-$HOME/.local/state}"
DEST="${GLASSDOCK_INSTALL_DIR:-$DATA/GlassDock}"
DEST_FORCED=0; [ -z "${GLASSDOCK_INSTALL_DIR:-}" ] || DEST_FORCED=1
APP="$DATA/applications"
AUTO="$CONF/autostart"
STAMP="$(date +%Y%m%d-%H%M%S)"
LOG="$STATE/glassdock/installer.log"

ACTION="${GLASSDOCK_ACTION:-}"
YES="${GLASSDOCK_YES:-0}"
DRY=0
FORCE_DEPS=0
DIRTY_POLICY="${GLASSDOCK_DIRTY:-}"      # stash | skip | discard | fresh | abort (non-interactive)
TMP=""; STASHED=""; PREV_HEAD=""; IN_PLACE=0; CURSOR_HIDDEN=0
PICK=0; ANSWER=""

# ----------------------------------------------------------------- terminal
if [ -t 2 ] && [ -z "${NO_COLOR:-}" ]; then
  B=$'\033[1m'; D=$'\033[2m'; R=$'\033[31m'; G=$'\033[32m'; Y=$'\033[33m'; C=$'\033[36m'; X=$'\033[0m'
else
  B=""; D=""; R=""; G=""; Y=""; C=""; X=""
fi
case "${LC_ALL:-${LC_CTYPE:-${LANG:-}}}" in
  *[Uu][Tt][Ff]-8*|*[Uu][Tt][Ff]8*) S_OK="✓"; S_WARN="!"; S_BAD="✗"; S_ARROW="❯"; S_DOT="·"; S_RULE="────────────────────────────────────";;
  *) S_OK="+"; S_WARN="!"; S_BAD="x"; S_ARROW=">"; S_DOT="-"; S_RULE="------------------------------------";;
esac

TTY=/dev/tty
HAVE_TTY=0
if { : <"$TTY"; } 2>/dev/null && { : >"$TTY"; } 2>/dev/null; then HAVE_TTY=1; fi

interactive() { [ "$HAVE_TTY" = 1 ] && [ "$YES" != 1 ]; }

log()   { mkdir -p "$(dirname "$LOG")" 2>/dev/null || true; printf '%s %s\n' "$(date '+%F %T')" "$*" >>"$LOG" 2>/dev/null || true; }
info()  { printf '%s==>%s %s\n' "$C$B" "$X" "$*" >&2; log "info: $*"; }
ok()    { printf '%s%s%s %s\n' "$G$B" "$S_OK" "$X" "$*" >&2; log "ok: $*"; }
warn()  { printf '%s%s%s %s\n' "$Y$B" "$S_WARN" "$X" "$*" >&2; log "warn: $*"; }
bad()   { printf '%s%s%s %s\n' "$R$B" "$S_BAD" "$X" "$*" >&2; }
note()  { printf '%s    %s%s\n' "$D" "$*" "$X" >&2; }
die()   { printf '%sError:%s %s\n' "$R$B" "$X" "$*" >&2; log "error: $*"; exit 1; }
step()  { printf '\n%s%s%s\n' "$B" "$*" "$X" >&2; }

show_cursor() { if [ "$CURSOR_HIDDEN" = 1 ]; then printf '\033[?25h' >"$TTY" 2>/dev/null || true; CURSOR_HIDDEN=0; fi; }
cleanup() { show_cursor; [ -z "$TMP" ] || rm -rf -- "$TMP"; }
trap cleanup EXIT
trap 'show_cursor; printf "\n" >&2; warn "Cancelled. Nothing further was changed."; exit 130' INT TERM

on_err() {
  local line="$1"
  show_cursor
  printf '\n%sSomething went wrong%s (script line %s).\n' "$R$B" "$X" "$line" >&2
  printf '  Log: %s\n' "$LOG" >&2
  if [ -n "$PREV_HEAD" ] && [ -d "$DEST/.git" ]; then
    printf '  To go back to the previous version: git -C "%s" checkout -f %s\n' "$DEST" "$PREV_HEAD" >&2
  fi
  [ -z "$STASHED" ] || printf '  Your stashed changes are safe: git -C "%s" stash list\n' "$DEST" >&2
  printf '  Preview what the installer would do with: --dry-run\n' >&2
}
trap 'on_err $LINENO' ERR

run() {  # run a command, or just show it with --dry-run
  log "run: $*"
  if [ "$DRY" = 1 ]; then printf '%s[dry-run]%s %s\n' "$Y" "$X" "$*" >&2; return 0; fi
  "$@"
}

# ------------------------------------------------------------------ prompts
confirm() {  # confirm "Question" y|n   -> status 0 for yes
  local q="$1" def="${2:-y}" a hint
  if ! interactive; then [ "$def" = y ]; return; fi
  if [ "$def" = y ]; then hint="[Y/n]"; else hint="[y/N]"; fi
  printf '%s?%s %s %s ' "$C$B" "$X" "$q" "$hint" >"$TTY"
  read -r a <"$TTY" || a=""
  a="${a:-$def}"
  case "$a" in [Yy]*) return 0;; *) return 1;; esac
}

ask() {  # ask "Prompt" default  -> ANSWER
  local q="$1" def="${2:-}"
  ANSWER="$def"
  interactive || return 0
  printf '%s?%s %s %s[%s]%s ' "$C$B" "$X" "$q" "$D" "$def" "$X" >"$TTY"
  read -r ANSWER <"$TTY" || ANSWER=""
  ANSWER="${ANSWER:-$def}"
  ANSWER="${ANSWER/#\~/$HOME}"
}

pick() {  # pick "Title" default_index "label|hint" ...   -> PICK (0-based)
  local title="$1" cur="$2"; shift 2
  local -a opts=("$@"); local n=${#opts[@]} i key rest label hint
  PICK="$cur"
  if ! interactive; then log "pick '$title' -> default $cur"; return 0; fi
  printf '\n%s%s%s\n' "$B" "$title" "$X" >"$TTY"
  if [ -z "${TERM:-}" ] || [ "$TERM" = dumb ]; then
    for ((i = 0; i < n; i++)); do printf '  %d) %s\n' $((i + 1)) "${opts[i]%%|*}" >"$TTY"; done
    printf '  Choose [1-%d] (Enter = %d): ' "$n" $((cur + 1)) >"$TTY"
    read -r key <"$TTY" || key=""
    if [[ "$key" =~ ^[0-9]+$ ]] && [ "$key" -ge 1 ] && [ "$key" -le "$n" ]; then PICK=$((key - 1)); fi
    return 0
  fi
  printf '%s  ↑/↓ move · Enter select · 1-%d jump%s\n' "$D" "$n" "$X" >"$TTY"
  printf '\033[?25l' >"$TTY"; CURSOR_HIDDEN=1
  _draw() {
    local j
    for ((j = 0; j < n; j++)); do
      label="${opts[j]%%|*}"; hint=""
      case "${opts[j]}" in *"|"*) hint="${opts[j]#*|}";; esac
      printf '\r\033[2K' >"$TTY"
      if [ "$j" -eq "$cur" ]; then printf '  %s%s %s%s' "$C$B" "$S_ARROW" "$label" "$X" >"$TTY"
      else printf '    %s' "$label" >"$TTY"; fi
      [ -z "$hint" ] || printf '  %s%s%s' "$D" "$hint" "$X" >"$TTY"
      printf '\n' >"$TTY"
    done
  }
  _draw
  while :; do
    IFS= read -rsn1 key <"$TTY" || key=""
    case "$key" in
      $'\033') IFS= read -rsn2 -t 0.05 rest <"$TTY" || rest=""
               case "$rest" in "[A") cur=$(((cur + n - 1) % n));; "[B") cur=$(((cur + 1) % n));; esac;;
      k|K) cur=$(((cur + n - 1) % n));;
      j|J) cur=$(((cur + 1) % n));;
      [1-9]) if [ "$key" -le "$n" ]; then cur=$((key - 1)); _redraw_pick; break; fi;;
      "") break;;
    esac
    _redraw_pick
  done
  show_cursor
  PICK="$cur"
}
_redraw_pick() { printf '\033[%dA' "$n" >"$TTY"; _draw; }

# ------------------------------------------------------------------ detection
has_glassdock() {
  [ -e "$BIN/glassdock" ] || [ -L "$BIN/glassdock" ] ||
  [ -e "$APP/glassdock-settings.desktop" ] || [ -e "$AUTO/glassdock.desktop" ] ||
  [ -d "$CONF/glassdock" ] || dock_running
}
has_moderndock() {
  [ -e "$BIN/moderndock" ] || [ -L "$BIN/moderndock" ] ||
  [ -e "$BIN/moderndock-ctl" ] || [ -L "$BIN/moderndock-ctl" ] ||
  [ -e "$APP/moderndock-settings.desktop" ] || [ -e "$AUTO/moderndock.desktop" ] ||
  [ -d "$CONF/moderndock" ] || [ -d "$HOME/ModernDock/moderndock" ] ||
  pgrep -u "$(id -u)" -f 'moderndock\.' >/dev/null 2>&1
}
has_glassicon() { [ -e "$BIN/glassicon" ] || [ -L "$BIN/glassicon" ] || [ -e "$APP/glassicon.desktop" ]; }
dock_running() { pgrep -u "$(id -u)" -f 'glassdock\.dock' >/dev/null 2>&1; }
in_session() { [ -n "${WAYLAND_DISPLAY:-}" ] || [ -n "${SWAYSOCK:-}" ]; }

# Where is this script running from? (a checkout, or piped from curl)
LOCAL_ROOT=""
SELF="${BASH_SOURCE[0]:-}"
if [ -n "$SELF" ] && [ -f "$SELF" ]; then
  _d="$(cd "$(dirname "$SELF")" 2>/dev/null && pwd -P || true)"
  if [ -n "$_d" ] && [ -x "$_d/scripts/install.sh" ]; then LOCAL_ROOT="$_d"; fi
fi

CK_STATE=missing; CK_BRANCH=""; CK_HEAD=""; CK_DIRTY=0
dirty_lines() {
  # Ignore Python bytecode: it is regenerated and never worth stopping for.
  git -C "$DEST" status --porcelain -uall 2>/dev/null | grep -Ev '(^|/)__pycache__/|\.py[co]$' || true
}
ck_info() {
  local top origin
  CK_STATE=missing; CK_BRANCH=""; CK_HEAD=""; CK_DIRTY=0
  [ -e "$DEST" ] || return 0
  if ! command -v git >/dev/null 2>&1 || ! top="$(git -C "$DEST" rev-parse --show-toplevel 2>/dev/null)" ||
     [ "$(cd "$DEST" && pwd -P)" != "$(cd "$top" && pwd -P)" ]; then
    CK_STATE=notgit; return 0
  fi
  origin="$(git -C "$DEST" remote get-url origin 2>/dev/null || true)"
  case "$origin" in
    *github.com[/:]"$REPO"*|"$REPO_URL") ;;
    *) CK_STATE=wrongorigin; return 0;;
  esac
  CK_BRANCH="$(git -C "$DEST" symbolic-ref --short -q HEAD || echo 'detached')"
  CK_HEAD="$(git -C "$DEST" rev-parse --short HEAD 2>/dev/null || true)"
  CK_DIRTY="$(dirty_lines | wc -l | tr -d ' ')"
  if [ "$CK_DIRTY" -gt 0 ]; then CK_STATE=dirty; else CK_STATE=clean; fi
}

row() { printf '  %s%-12s%s %s\n' "$D" "$1" "$X" "$2" >&2; }
show_status() {
  ck_info
  printf '\n  %sGlassDock Setup%s\n  %s\n' "$B" "$X" "$S_RULE" >&2
  if has_glassdock; then
    local run=""; dock_running && run=" ${G}running${X}"
    row "GlassDock" "${G}${S_OK} installed${X}${run}"
  else row "GlassDock" "${D}not installed${X}"; fi
  if has_moderndock; then row "ModernDock" "${Y}${S_WARN} legacy install found; install will migrate it${X}"; fi
  if has_glassicon; then row "GlassIcon" "${G}${S_OK} installed${X}"; fi
  case "$CK_STATE" in
    missing) row "Source" "${D}$DEST (not downloaded yet)${X}";;
    notgit) row "Source" "${Y}${S_WARN} $DEST exists but is not a Git checkout${X}";;
    wrongorigin) row "Source" "${Y}${S_WARN} $DEST is a checkout of a different repository${X}";;
    clean) row "Source" "$DEST ${D}($CK_BRANCH @ $CK_HEAD)${X}";;
    dirty) row "Source" "$DEST ${D}($CK_BRANCH @ $CK_HEAD)${X} ${Y}${S_WARN} $CK_DIRTY local change(s)${X}";;
  esac
  [ -z "$LOCAL_ROOT" ] || row "This folder" "${D}$LOCAL_ROOT (a GlassDock checkout)${X}"
  if in_session; then row "Session" "${D}Wayland ${XDG_CURRENT_DESKTOP:-${XDG_SESSION_DESKTOP:-detected}}${X}"; else row "Session" "${D}no Wayland session in this shell${X}"; fi
  printf '\n' >&2
}

# ------------------------------------------------------------------ preflight
PY_OK=1; GI_OK=1; LS_OK=1
preflight() {
  step "Checking your system"
  command -v python3 >/dev/null 2>&1 || PY_OK=0
  if [ "$PY_OK" = 1 ]; then
    python3 -c 'import gi; gi.require_version("Gtk","3.0")' >/dev/null 2>&1 || GI_OK=0
    python3 -c 'import gi; gi.require_version("GtkLayerShell","0.1")' >/dev/null 2>&1 || LS_OK=0
  else GI_OK=0; LS_OK=0; fi
  _check() { if [ "$2" = 1 ]; then ok "$1"; else bad "$1 ${D}(missing)${X}"; fi; }
  _check "python3" "$PY_OK"
  _check "GTK 3 Python bindings (python3-gobject, gtk3)" "$GI_OK"
  _check "gtk-layer-shell" "$LS_OK"
  if command -v git >/dev/null 2>&1; then ok "git"; elif command -v curl >/dev/null 2>&1; then warn "git missing; will download a tarball with curl instead"; else bad "git or curl ${D}(one is required)${X}"; die "Install git or curl first."; fi
  command -v sway >/dev/null 2>&1 && ok "sway" || warn "sway not found on PATH (the dock needs Sway/SwayFX on Wayland)"
  case ":$PATH:" in *":$BIN:"*) ok "$BIN is on your PATH";; *) warn "$BIN is not on your PATH; commands like glassdock won't be found until it is";; esac
}
deps_missing() { [ "$PY_OK" = 0 ] || [ "$GI_OK" = 0 ] || [ "$LS_OK" = 0 ]; }

# --------------------------------------------------------------- source/git
fresh_dir() {  # let the user pick another folder; sets DEST
  local suggested="${DEST}-new"
  [ ! -e "$suggested" ] || suggested="$DEST-$STAMP"
  ask "Install into which folder?" "$suggested"
  [ -n "$ANSWER" ] || die "No folder given."
  [ ! -e "$ANSWER" ] || die "$ANSWER already exists. Pick a folder that doesn't."
  DEST="$ANSWER"
  info "Using $DEST"
}

move_aside() {
  local to="$DEST.backup-$STAMP"
  run mv -- "$DEST" "$to"
  ok "Moved the old folder to $to"
}

clone_fresh() {
  mkdir -p "$(dirname "$DEST")"
  info "Downloading $REPO into $DEST…"
  if command -v git >/dev/null 2>&1; then
    run git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$DEST" >&2 || die "Git clone failed. Check your connection and that $REPO_URL is reachable."
  else
    TMP="$(mktemp -d "${TMPDIR:-/tmp}/glassdock-setup.XXXXXX")"
    run curl -fLsS "https://github.com/$REPO/archive/refs/heads/$BRANCH.tar.gz" -o "$TMP/source.tar.gz" || die "Download failed."
    mkdir "$TMP/unpack"; tar -xzf "$TMP/source.tar.gz" -C "$TMP/unpack"
    local src; src="$(find "$TMP/unpack" -mindepth 1 -maxdepth 1 -type d -name 'GlassDock-*' -print -quit)"
    [ -n "$src" ] || die "The downloaded archive did not contain the expected GlassDock folder."
    run mv "$src" "$DEST"
  fi
}

handle_dirty() {  # the checkout has uncommitted changes
  local lines; lines="$(dirty_lines)"
  warn "$DEST has $CK_DIRTY uncommitted change(s):"
  printf '%s\n' "$lines" | head -n 12 | sed "s/^/      /" >&2
  [ "$CK_DIRTY" -le 12 ] || note "…and $((CK_DIRTY - 12)) more"
  local policy="$DIRTY_POLICY"
  if interactive; then
    pick "What should I do with your changes?" 0 \
      "Stash them, update, keep the stash|safe and reversible (recommended)" \
      "Leave my files as they are|skip updating, install what's here" \
      "Discard them and update|cannot be undone" \
      "Install a fresh copy elsewhere|leaves this folder alone" \
      "Cancel|change nothing"
    case "$PICK" in 0) policy=stash;; 1) policy=skip;; 2) policy=discard;; 3) policy=fresh;; *) policy=abort;; esac
  else
    policy="${policy:-stash}"
    info "Non-interactive: applying policy '$policy' (set GLASSDOCK_DIRTY=stash|skip|discard|fresh|abort)."
  fi
  case "$policy" in
    stash)
      run git -C "$DEST" -c user.name=glassdock-installer -c user.email=installer@localhost \
        stash push -u -m "glassdock installer $STAMP" >/dev/null
      STASHED="glassdock installer $STAMP"
      ok "Stashed your changes (git -C \"$DEST\" stash list)";;
    skip) SKIP_UPDATE=1; warn "Keeping your files; not updating from GitHub.";;
    discard)
      if ! interactive || confirm "Really delete $CK_DIRTY local change(s) in $DEST? This cannot be undone." n; then
        run git -C "$DEST" reset --hard -q
        run git -C "$DEST" clean -fdq
        ok "Discarded local changes."
      else die "Cancelled. Nothing was changed."; fi;;
    fresh) fresh_dir;;
    *) die "Cancelled. Nothing was changed.";;
  esac
}

SKIP_UPDATE=0
existing_checkout() {
  ck_info
  case "$CK_STATE" in
    notgit)
      warn "$DEST exists but isn't a Git checkout."
      if interactive; then
        pick "What should I do with it?" 0 \
          "Move it aside and download fresh|kept as $(basename "$DEST").backup-$STAMP" \
          "Use a different folder|leaves it alone" \
          "Cancel|change nothing"
        case "$PICK" in 0) move_aside;; 1) fresh_dir;; *) die "Cancelled. Nothing was changed.";; esac
      else info "Non-interactive: moving it aside."; move_aside; fi;;
    wrongorigin)
      warn "$DEST is a Git checkout of a different repository ($(git -C "$DEST" remote get-url origin 2>/dev/null || echo unknown))."
      if interactive; then
        pick "What should I do?" 0 \
          "Use a different folder|recommended" \
          "Move it aside and download fresh|kept as a .backup folder" \
          "Cancel|change nothing"
        case "$PICK" in 0) fresh_dir;; 1) move_aside;; *) die "Cancelled. Nothing was changed.";; esac
      else die "$DEST belongs to another repository. Re-run with --dir PATH to choose a different folder."; fi;;
    dirty) handle_dirty;;
  esac
  # Regenerated bytecode never blocks an update.
  [ ! -d "$DEST" ] || find "$DEST" -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
}

update_checkout() {
  [ -d "$DEST/.git" ] || return 0
  [ "$SKIP_UPDATE" = 0 ] || return 0
  local cur sha ahead
  PREV_HEAD="$(git -C "$DEST" rev-parse HEAD)"
  cur="$(git -C "$DEST" symbolic-ref --short -q HEAD || echo detached)"
  if [ "$cur" != "$BRANCH" ]; then
    warn "The checkout is on '$cur', not '$BRANCH'."
    if interactive; then
      pick "Which version do you want installed?" 0 \
        "Switch to $BRANCH and update|your branch '$cur' is kept" \
        "Stay on $cur|no update" \
        "Cancel|change nothing"
      case "$PICK" in 0) ;; 1) SKIP_UPDATE=1; return 0;; *) die "Cancelled. Nothing was changed.";; esac
    else info "Non-interactive: switching to $BRANCH (your branch '$cur' is kept)."; fi
  fi
  # Count unpushed local commits using the last known origin/$BRANCH, *before* fetching:
  # a shallow fetch rewrites the boundary and would make old commits look local.
  ahead=0
  if git -C "$DEST" rev-parse -q --verify "refs/heads/$BRANCH" >/dev/null 2>&1 &&
     git -C "$DEST" rev-parse -q --verify "origin/$BRANCH" >/dev/null 2>&1; then
    ahead="$(git -C "$DEST" rev-list --count "origin/$BRANCH..refs/heads/$BRANCH" 2>/dev/null || echo 0)"
  fi
  info "Checking GitHub for updates…"
  if [ "$(git -C "$DEST" rev-parse --is-shallow-repository 2>/dev/null)" = true ]; then
    run git -C "$DEST" fetch --depth 1 -q origin "$BRANCH"
  else run git -C "$DEST" fetch -q origin "$BRANCH"; fi
  sha="$(git -C "$DEST" rev-parse FETCH_HEAD 2>/dev/null || true)"
  if [ -z "$sha" ]; then
    [ "$DRY" = 1 ] && return 0
    die "Could not read $BRANCH from GitHub."
  fi
  if [ "$ahead" -gt 0 ]; then
    warn "You have $ahead local commit(s) on $BRANCH that are not on GitHub."
    if interactive; then
      pick "How should I handle your commits?" 0 \
        "Back them up to a branch, then update|safe (recommended)" \
        "Keep them and skip the update|install what's here" \
        "Cancel|change nothing"
      case "$PICK" in 0) ;; 1) SKIP_UPDATE=1; return 0;; *) die "Cancelled. Nothing was changed.";; esac
    fi
    run git -C "$DEST" branch "glassdock-local-$STAMP" "refs/heads/$BRANCH"
    ok "Backed up to branch glassdock-local-$STAMP"
  fi
  if [ "$sha" = "$PREV_HEAD" ] && [ "$cur" = "$BRANCH" ]; then
    ok "Already up to date ($(git -C "$DEST" rev-parse --short HEAD))."
    return 0
  fi
  run git -C "$DEST" checkout -q -B "$BRANCH" FETCH_HEAD
  ok "Updated to $(git -C "$DEST" rev-parse --short HEAD 2>/dev/null || echo "$sha")."
  git -C "$DEST" log -n 5 --pretty='      %h %s' 2>/dev/null >&2 || true
}

prepare_source() {
  if [ "$IN_PLACE" = 1 ]; then info "Using $DEST in place (no download, git untouched)."; return 0; fi
  step "Getting the source"
  mkdir -p "$DATA"
  if [ -e "$DEST" ]; then existing_checkout; fi
  if [ ! -e "$DEST" ]; then clone_fresh; else update_checkout; fi
  [ "$DRY" = 1 ] || [ -x "$DEST/scripts/install.sh" ] || die "$DEST/scripts/install.sh is missing; is this the right repository?"
}

choose_source() {
  if [ "$DEST_FORCED" = 0 ] && [ -n "$LOCAL_ROOT" ]; then
    if interactive; then
      pick "You're running this from a GlassDock checkout. Install from…" 0 \
        "This checkout, in place|$LOCAL_ROOT (git untouched)" \
        "A managed copy from GitHub|$DEST (updated automatically)"
      if [ "$PICK" = 0 ]; then IN_PLACE=1; DEST="$LOCAL_ROOT"; fi
    else IN_PLACE=1; DEST="$LOCAL_ROOT"; fi
  elif [ "$DEST_FORCED" = 1 ] && [ -n "$LOCAL_ROOT" ] && [ "$(cd "$DEST" 2>/dev/null && pwd -P || true)" = "$LOCAL_ROOT" ]; then
    IN_PLACE=1
  fi
}

# --------------------------------------------------------------- install
supports() { grep -q -- "$1" "$DEST/scripts/install.sh" 2>/dev/null; }

maybe_install_deps() {
  local want=0
  if [ "$FORCE_DEPS" = 1 ] || [ "${GLASSDOCK_INSTALL_DEPS:-}" = y ] || [ "${GLASSDOCK_INSTALL_DEPS:-}" = Y ]; then want=1
  elif deps_missing; then
    step "Dependencies"
    warn "Some required packages are missing (see the checklist above)."
    if interactive; then
      if confirm "Install them now with scripts/install-deps.sh? (asks for your sudo password)" y; then want=1; fi
    else note "Not installing them unattended. Re-run with --deps (or GLASSDOCK_INSTALL_DEPS=y) to allow sudo."; fi
  fi
  if [ "$want" = 1 ]; then
    if [ -x "$DEST/scripts/install-deps.sh" ]; then run "$DEST/scripts/install-deps.sh"
    else warn "$DEST/scripts/install-deps.sh not found; install the packages from the checklist manually."; fi
  elif deps_missing; then
    warn "Continuing without them; install.sh will tell you exactly what is missing."
  fi
}

INSTALL_ARGS=()
ask_options() {
  if supports '--autostart' && [ ! -e "$AUTO/glassdock.desktop" ]; then
    if confirm "Start GlassDock automatically when you log in?" y; then INSTALL_ARGS+=(--autostart)
    elif supports '--no-autostart'; then INSTALL_ARGS+=(--no-autostart); fi
  fi
}

confirm_plan() {
  step "Plan"
  if has_moderndock; then note "Replaces ModernDock's command links and launchers; your settings are migrated."; fi
  if [ "$IN_PLACE" = 1 ]; then note "Source:  $DEST ${S_DOT} in place"; else note "Source:  $REPO ($BRANCH) ${S_DOT} $DEST"; fi
  note "Actions: check dependencies ${S_DOT} link commands into $BIN ${S_DOT} add the Settings launcher"
  [ "$DRY" = 0 ] || note "Dry run: nothing will actually be changed."
  confirm "Continue?" y
}

run_installer() {
  step "Installing"
  if ! run "$DEST/scripts/install.sh" ${INSTALL_ARGS[@]+"${INSTALL_ARGS[@]}"}; then
    bad "install.sh failed."
    [ -z "$PREV_HEAD" ] || note "Roll back with: git -C \"$DEST\" checkout -f $PREV_HEAD"
    [ -z "$STASHED" ] || note "Your stashed changes are safe: git -C \"$DEST\" stash list"
    exit 1
  fi
}

restart_dock() {
  command -v "$BIN/glassdock" >/dev/null 2>&1 || [ -x "$BIN/glassdock" ] || return 0
  if dock_running; then
    if confirm "GlassDock is running. Restart it to load the update?" y; then
      if [ -x "$BIN/glassdock-ctl" ]; then run "$BIN/glassdock-ctl" quit >/dev/null 2>&1 || true; else run pkill -u "$(id -u)" -f 'glassdock\.dock' || true; fi
      [ "$DRY" = 1 ] || sleep 1
      if [ "$DRY" = 1 ]; then run setsid nohup "$BIN/glassdock"; else setsid nohup "$BIN/glassdock" >/dev/null 2>&1 </dev/null & fi
      ok "Dock restarted."
    fi
  elif in_session && confirm "Start the dock now?" y; then
    if [ "$DRY" = 1 ]; then run setsid nohup "$BIN/glassdock"; else setsid nohup "$BIN/glassdock" >/dev/null 2>&1 </dev/null & fi
    ok "Dock started."
  fi
}

restore_stash() {
  [ -n "$STASHED" ] || return 0
  printf '\n' >&2
  info "Your earlier local changes are saved in a Git stash."
  if confirm "Re-apply them on top of the new version now?" n; then
    if git -C "$DEST" -c user.name=glassdock-installer -c user.email=installer@localhost stash pop; then ok "Local changes restored."
    else warn "They conflict with the update. Nothing was lost; resolve with: git -C \"$DEST\" stash list"; fi
  else note "Restore later with: git -C \"$DEST\" stash pop"; fi
}

install_dock() {
  preflight
  choose_source
  confirm_plan || { info "Cancelled. Nothing was changed."; return 0; }
  prepare_source
  maybe_install_deps
  ask_options
  run_installer
  ok "GlassDock installed from $DEST."
  restart_dock
  restore_stash
  printf '\n  %sStart%s     glassdock &\n  %sSettings%s  glassdock-settings\n  %sStatus%s    glassdock-ctl status\n  %sLog%s       %s\n\n' "$B" "$X" "$B" "$X" "$B" "$X" "$B" "$X" "$LOG" >&2
}

install_glassicon() {
  preflight
  choose_source
  prepare_source
  local root="$DEST/extras/GlassIcon"
  [ "$DRY" = 1 ] || [ -x "$root/install.sh" ] || die "GlassIcon Studio was not found at $root/install.sh in the checkout."
  note "GlassIcon Studio manages icon themes, launcher icons, and user-level file-manager icons."
  if [ "$FORCE_DEPS" = 1 ] || confirm "Install GlassIcon system dependencies too? (may use sudo)" n; then run "$root/install.sh" --deps; else run "$root/install.sh"; fi
  ok "GlassIcon Studio installed."
  restore_stash
  note "Launch: glassicon"
}

# --------------------------------------------------------------- uninstall
safe_to_delete() {  # refuse anything that isn't clearly a GlassDock folder
  local p="$1"
  [ -n "$p" ] && [ "$p" != "/" ] && [ "$p" != "$HOME" ] && [ -d "$p" ] &&
  { [ -x "$p/scripts/install.sh" ] || [ -d "$p/.git" ]; }
}

stop_dock() {
  if dock_running; then
    info "Stopping the running dock…"
    if [ -x "$BIN/glassdock-ctl" ]; then run "$BIN/glassdock-ctl" quit >/dev/null 2>&1 || true; fi
    pkill -u "$(id -u)" -f 'glassdock\.dock' >/dev/null 2>&1 || true
  fi
}

uninstall_dock() {
  if ! has_glassdock && ! has_moderndock; then warn "No obvious installation detected."; fi
  step "Uninstall"
  note "Removes command links, launchers and autostart. Project folders stay unless you say otherwise."
  local purge=0 delete_src=0
  confirm "Continue with uninstall?" y || { info "Cancelled."; return 0; }
  if interactive; then
    if confirm "Also remove saved settings? (a .tar.gz backup is made first)" n; then purge=1; fi
  elif [ "${GLASSDOCK_PURGE_CONFIG:-n}" = y ]; then purge=1; fi
  ck_info
  if [ "$CK_STATE" != missing ] && [ "$CK_STATE" != notgit ] && safe_to_delete "$DEST"; then
    if [ "$CK_STATE" = dirty ]; then note "$DEST has $CK_DIRTY local change(s); deleting it would lose them."; fi
    if confirm "Also delete the downloaded source folder $DEST?" n; then delete_src=1; fi
  fi
  stop_dock
  local name target resolved
  for name in glassdock glassdock-ctl glassdock-settings moderndock moderndock-ctl moderndock-settings; do
    target="$BIN/$name"
    if [ -L "$target" ]; then
      resolved="$(readlink -f "$target" 2>/dev/null || true)"
      [ -n "$resolved" ] || resolved="$(readlink "$target" 2>/dev/null || true)"   # dangling link
      case "$resolved" in *GlassDock*|*ModernDock*|*glassdock*|*moderndock*) run rm -f -- "$target"; ok "Removed $target";; esac
    fi
  done
  run rm -f -- "$APP/glassdock-settings.desktop" "$APP/moderndock-settings.desktop" "$AUTO/glassdock.desktop" "$AUTO/moderndock.desktop"
  local root
  for root in "$DEST" "$HOME/GlassDock" "$HOME/ModernDock"; do
    if [ -x "$root/scripts/uninstall.sh" ]; then run "$root/scripts/uninstall.sh" || true; fi
  done
  if [ "$purge" = 1 ]; then
    local cfg backup
    for cfg in "$CONF/glassdock" "$CONF/moderndock"; do
      if [ -d "$cfg" ]; then
        backup="$HOME/$(basename "$cfg")-backup-$STAMP.tar.gz"
        run tar -czf "$backup" -C "$(dirname "$cfg")" "$(basename "$cfg")"
        run rm -rf -- "$cfg"; ok "Removed settings; backup: $backup"
      fi
    done
  else info "Settings preserved."; fi
  if [ "$delete_src" = 1 ]; then run rm -rf -- "$DEST"; ok "Deleted $DEST"; fi
  ok "Uninstall complete."
}

uninstall_glassicon() {
  local linked_root="" resolved
  if [ -L "$BIN/glassicon" ]; then
    resolved="$(readlink -f -- "$BIN/glassicon" 2>/dev/null || true)"
    case "$resolved" in */extras/GlassIcon/bin/glassicon) linked_root="${resolved%/bin/glassicon}";; esac
  fi
  if [ -n "$linked_root" ] && [ -x "$linked_root/uninstall.sh" ]; then
    run "$linked_root/uninstall.sh"
  else
    choose_source; prepare_source
    [ -x "$DEST/extras/GlassIcon/uninstall.sh" ] || die "GlassIcon uninstaller not found in $DEST."
    run "$DEST/extras/GlassIcon/uninstall.sh"
  fi
  ok "GlassIcon Studio launcher removed; settings and icon overrides were preserved."
}

# --------------------------------------------------------------- main
usage() {
  cat <<EOF
GlassDock installer

Usage: installer.sh [options]
  --action NAME    install | glassicon | uninstall | uninstall-glassicon | status
  --dir PATH       where the managed source checkout lives (default: $DATA/GlassDock)
  --branch NAME    branch to install (default: $BRANCH)
  --deps           also install system dependencies (uses sudo)
  -y, --yes        accept the safe default for every question (no prompts)
  -n, --dry-run    show what would happen without changing anything
  --no-color       plain output
  -h, --help       this help

With curl:  curl -fsSL <url>/installer.sh | bash -s -- --action install -y

Environment: GLASSDOCK_DIRTY=stash|skip|discard|fresh|abort  decides what to do with
uncommitted changes when no one can be asked (default: stash).
EOF
}

parse_args() {
  while [ $# -gt 0 ]; do
    case "$1" in
      --action) [ $# -ge 2 ] || die "--action needs a value"; ACTION="$2"; shift;;
      --action=*) ACTION="${1#*=}";;
      --dir) [ $# -ge 2 ] || die "--dir needs a path"; DEST="${2/#\~/$HOME}"; DEST_FORCED=1; shift;;
      --dir=*) DEST="${1#*=}"; DEST="${DEST/#\~/$HOME}"; DEST_FORCED=1;;
      --branch) [ $# -ge 2 ] || die "--branch needs a name"; BRANCH="$2"; shift;;
      --deps) FORCE_DEPS=1;;
      -y|--yes) YES=1;;
      -n|--dry-run) DRY=1;;
      --no-color) B=""; D=""; R=""; G=""; Y=""; C=""; X="";;
      -h|--help) usage; exit 0;;
      *) usage >&2; die "Unknown option: $1";;
    esac
    shift
  done
}

choose_action() {
  if interactive; then
    local def=0
    pick "What would you like to do?" "$def" \
      "Install / upgrade GlassDock|also migrates ModernDock" \
      "Install / upgrade GlassIcon Studio|icon themes and launcher icons" \
      "Check status|dependencies, install and checkout state" \
      "Uninstall GlassDock / ModernDock" \
      "Uninstall GlassIcon Studio" \
      "Exit|change nothing"
    case "$PICK" in 0) ACTION=install;; 1) ACTION=glassicon;; 2) ACTION=status;; 3) ACTION=uninstall;; 4) ACTION=uninstall-glassicon;; *) ACTION=quit;; esac
  else
    [ -n "$ACTION" ] || die "No interactive terminal was found. Run this from a terminal, or pass --action install|glassicon|uninstall|uninstall-glassicon|status."
    warn "No terminal attached; using action '$ACTION'."
  fi
}

main() {
  parse_args "$@"
  [ "$(id -u)" -ne 0 ] || die "Run as your normal user, not root."
  case "$ACTION" in ""|install|glassicon|uninstall|uninstall-glassicon|status|quit) ;; *) die "Unknown action '$ACTION'.";; esac
  log "start action='${ACTION:-menu}' dest=$DEST yes=$YES dry=$DRY tty=$HAVE_TTY"
  show_status
  [ -n "$ACTION" ] || choose_action
  case "$ACTION" in
    install) install_dock;;
    glassicon) install_glassicon;;
    uninstall) uninstall_dock;;
    uninstall-glassicon) uninstall_glassicon;;
    status) preflight; printf '\n' >&2;;
    *) printf 'No changes made.\n' >&2;;
  esac
}

main "$@"
