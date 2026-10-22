#!/usr/bin/env sh
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$(readlink -f -- "$0")")/.." && pwd)"
python3 -m py_compile "$ROOT/glassicon_core.py" "$ROOT/glassicon_gui.py"
PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" python3 -m unittest discover -s "$ROOT/tests" -v
if ! python3 -c 'import gi; gi.require_version("Gtk", "3.0")' >/dev/null 2>&1; then
    printf '%s\n' 'GTK 3 runtime not detected; syntax and core tests passed, GUI launch needs PyGObject/GTK 3.'
fi
