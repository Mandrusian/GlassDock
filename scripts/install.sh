#!/usr/bin/env bash
# Install GlassDock for the current user. Runs in place from this directory:
# nothing is copied system-wide and no root access is needed (except --deps).
#
#   ./install.sh                  link commands, add the Settings launcher, enable login autostart
#   ./install.sh --deps           also install dependencies first (dnf / apt / pacman / zypper)
#   ./install.sh --no-autostart   do not set up login autostart
#   ./install.sh --no-check       skip the dependency check (packaging/CI only)
#
# Which window managers the dock starts in is chosen later in
# Settings -> Behavior ("Only auto-start in these sessions/WMs", default: sway).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"
APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
CONF_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
AUTOSTART_DIR="$CONF_HOME/autostart"
OLD="modern""dock"       # previous name of this project
DO_DEPS=0
DO_AUTOSTART=1
NO_CHECK=0

for arg in "$@"; do
    case "$arg" in
        --deps) DO_DEPS=1 ;;
        --autostart) DO_AUTOSTART=1 ;;
        --no-autostart) DO_AUTOSTART=0 ;;
        --no-check) NO_CHECK=1 ;;
        -h|--help) sed -n '2,10p' "${BASH_SOURCE[0]}"; exit 0 ;;
        *) echo "unknown option: $arg" >&2; exit 2 ;;
    esac
done

if [ "$(id -u)" -eq 0 ] && [ -z "${GLASSDOCK_ALLOW_ROOT:-}" ]; then
    echo "Run this as your normal user, not root." >&2
    exit 1
fi

chmod +x "$ROOT"/bin/* "$ROOT"/scripts/*.sh "$ROOT"/install.sh 2>/dev/null || true

if [ "$(uname -s)" = Darwin ]; then
    [ "$DO_DEPS" = 0 ] || echo "macOS uses Xcode Command Line Tools, not gtk-layer-shell."
    command -v swiftc >/dev/null 2>&1 || { echo "Install Xcode Command Line Tools first: xcode-select --install" >&2; exit 1; }
    mkdir -p "$ROOT/macos/build" "${XDG_BIN_HOME:-$HOME/.local/bin}" "$HOME/Library/LaunchAgents"
    swiftc "$ROOT/macos/GlassDock.swift" -o "$ROOT/macos/build/GlassDock" || exit 1
    ln -sfn "$ROOT/bin/glassdock" "${XDG_BIN_HOME:-$HOME/.local/bin}/glassdock"
    if [ "$DO_AUTOSTART" = 1 ]; then
        cat >"$HOME/Library/LaunchAgents/com.mandrusian.glassdock.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>com.mandrusian.glassdock</string>
<key>ProgramArguments</key><array><string>$ROOT/bin/glassdock</string></array>
<key>RunAtLoad</key><true/>
<key>KeepAlive</key><false/>
</dict></plist>
PLIST
    fi
    echo "Native macOS GlassDock preview installed. Run: $ROOT/bin/glassdock"
    echo "This preview shows running apps only; Linux settings and plugins are not yet supported."
    exit 0
fi

if [ "$DO_DEPS" = 1 ]; then
    "$ROOT/scripts/install-deps.sh"
fi

if [ "$NO_CHECK" = 0 ]; then
    echo "==> Checking build and dependencies"
    "$ROOT/scripts/build.sh"
fi

# ---- leftovers of the old name (GlassDock) -------------------------------
if [ -L "$BIN_DIR/$OLD-ctl" ]; then
    echo "==> Found an old $OLD install: stopping it and removing its links"
    "$BIN_DIR/$OLD-ctl" quit >/dev/null 2>&1 || true
fi
for old in "$OLD" "$OLD-ctl" "$OLD-settings"; do
    if [ -L "$BIN_DIR/$old" ]; then rm -f "$BIN_DIR/$old"; echo "  removed $BIN_DIR/$old"; fi
done
rm -f "$APP_DIR/$OLD-settings.desktop" "$AUTOSTART_DIR/$OLD.desktop"
# (the old config is migrated automatically the first time GlassDock starts)

echo "==> Linking commands into $BIN_DIR"
mkdir -p "$BIN_DIR"
for cmd in glassdock glassdock-ctl glassdock-settings; do
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
cat >"$APP_DIR/glassdock-settings.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=GlassDock Settings
Comment=Customize the GlassDock dock
Exec="$ROOT/bin/glassdock-settings"
Icon=$ROOT/assets/glassdock.svg
Terminal=false
Categories=Settings;DesktopSettings;GTK;
Keywords=dock;panel;launcher;glassdock;
EOF
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APP_DIR" 2>/dev/null || true

if [ "$DO_AUTOSTART" = 1 ]; then
    echo "==> Enabling login autostart"
    mkdir -p "$AUTOSTART_DIR"
    cat >"$AUTOSTART_DIR/glassdock.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=GlassDock
Comment=Start the GlassDock dock (only in the sessions chosen in its settings)
Exec="$ROOT/bin/glassdock" --autostart
Icon=$ROOT/assets/glassdock.svg
Terminal=false
NoDisplay=true
X-GNOME-Autostart-enabled=true
EOF
    echo "  $AUTOSTART_DIR/glassdock.desktop"
    # Sway does not run XDG autostart by itself, so also use the safe config include.
    if [ -f "$CONF_HOME/sway/config" ] || [ -f "$HOME/.sway/config" ]; then
        "$ROOT/scripts/sway-integration.sh" enable-autostart || \
            echo "  (could not edit your Sway config; add 'exec \"$ROOT/bin/glassdock\" --autostart' yourself)" >&2
    fi
    cat <<EOF
  The dock only starts in the sessions listed in Settings -> Behavior (default: sway).
  Other compositors that do not run XDG autostart, add one line to their config:
    Hyprland : exec-once = glassdock --autostart
    niri     : spawn-at-startup "glassdock" "--autostart"
    river    : riverctl spawn "glassdock --autostart"
EOF
fi

case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *) echo "NOTE: $BIN_DIR is not on your PATH in this shell. Add it with:"
       echo "      echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc" ;;
esac

cat <<EOF

Installed. Try it:
  glassdock &            # start the dock (inside your Wayland session)
  glassdock-settings     # open the settings app
  glassdock-ctl status   # ask the running dock how it is doing
EOF
