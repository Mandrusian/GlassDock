#!/usr/bin/env bash
set -euo pipefail

if [ -n "${TERMUX_VERSION:-}" ] || [[ "${PREFIX:-}" == *"/com.termux/"* ]]; then
    command -v pkg >/dev/null 2>&1 || { echo "Run this inside Termux." >&2; exit 1; }
    pkg install -y python python-pip x11-repo
    python -m pip install --user python-xlib
else
    command -v python3 >/dev/null 2>&1 || { echo "Python 3 is required." >&2; exit 1; }
    python3 -m pip install --user python-xlib
fi

echo "X11 backend dependencies installed."
