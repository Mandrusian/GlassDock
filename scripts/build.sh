#!/usr/bin/env bash
# "Build" step. GlassDock is Python + GTK3, so nothing is compiled to machine
# code: this byte-compiles the sources and verifies every runtime dependency.
set -euo pipefail
ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
cd "$ROOT"

IS_TERMUX=0
if [ -n "${TERMUX_VERSION:-}" ] || [ "${PREFIX:-}" = "/data/data/com.termux/files/usr" ] || [ -n "${ANDROID_ROOT:-}" ]; then
    IS_TERMUX=1
fi

command -v python3 >/dev/null || { echo "python3 not found" >&2; exit 1; }
python3 - <<'PY'
import sys
if sys.version_info < (3, 9):
    sys.exit("Python 3.9+ required, found %s" % sys.version.split()[0])
PY

echo "==> Byte-compiling sources"
python3 -m compileall -q glassdock

echo "==> Checking runtime dependencies"
set +e
python3 - <<'PY'
import sys
problems = []
try:
    import gi
except ImportError:
    sys.exit("  MISSING PyGObject (gi). On Termux try: pkg install pygobject gobject-introspection; on desktop Linux install python3-gobject.")
checks = [("Gtk", "3.0", "gtk3"), ("Gdk", "3.0", "gtk3"), ("Pango", "1.0", "pango"),
          ("PangoCairo", "1.0", "pango"), ("GtkLayerShell", "0.1", "gtk-layer-shell")]
for ns, ver, pkg in checks:
    try:
        gi.require_version(ns, ver)
        print("  ok       %s %s" % (ns, ver))
    except ValueError:
        print("  MISSING  %s %s  ->  %s" % (ns, ver, ("pkg install gtk3 gtk-layer-shell" if sys.platform.startswith("linux") and (__import__("os").environ.get("TERMUX_VERSION") or __import__("os").environ.get("PREFIX", "").startswith("/data/data/com.termux/") or __import__("os").environ.get("PREFIX", "").startswith("/data/user/0/com.termux/") or __import__("os").environ.get("ANDROID_ROOT")) else "install package: " + pkg)))
        problems.append(ns)
try:
    import cairo  # noqa: F401
    print("  ok       pycairo")
except ImportError:
    print("  MISSING  pycairo  ->  " + ("pkg install pycairo" if (__import__("os").environ.get("TERMUX_VERSION") or __import__("os").environ.get("PREFIX", "").startswith("/data/data/com.termux/") or __import__("os").environ.get("PREFIX", "").startswith("/data/user/0/com.termux/") or __import__("os").environ.get("ANDROID_ROOT")) else "install python3-cairo using your distribution package manager"))
    problems.append("cairo")
sys.exit(1 if problems else 0)
PY
status=$?
set -e
if [ "$status" -ne 0 ]; then
    echo "Dependencies missing. Run ./scripts/install-deps.sh and build again." >&2
    exit 1
fi
chmod +x bin/* scripts/*.sh
echo "==> Build OK. Next: ./scripts/run-tests.sh"
