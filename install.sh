#!/usr/bin/env bash
# GlassDock installer. Works from a clone (./install.sh) or straight from GitHub:
#
#   curl -fsSL https://raw.githubusercontent.com/<user>/glassdock/main/install.sh \
#       | GLASSDOCK_REPO=<user>/glassdock bash
#
# Any options are passed on to scripts/install.sh (--deps, --no-autostart, ...).
set -euo pipefail

HERE="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]:-$0}")")" 2>/dev/null && pwd || true)"
if [ -n "$HERE" ] && [ -x "$HERE/scripts/install.sh" ]; then
    exec "$HERE/scripts/install.sh" "$@"
fi

REPO="${GLASSDOCK_REPO:-}"
DEST="${GLASSDOCK_DIR:-$HOME/GlassDock}"
if [ -z "$REPO" ]; then
    echo "Set GLASSDOCK_REPO=<github-user>/glassdock (or run ./install.sh inside a clone)." >&2
    exit 1
fi
command -v git >/dev/null 2>&1 || { echo "git is required to download GlassDock." >&2; exit 1; }
if [ -d "$DEST/.git" ]; then
    git -C "$DEST" pull --ff-only
else
    git clone "https://github.com/$REPO.git" "$DEST"
fi
exec "$DEST/scripts/install.sh" "$@"
