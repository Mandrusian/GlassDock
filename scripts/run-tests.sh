#!/usr/bin/env bash
# Runs the unit tests. Logic tests need no display. The GTK smoke test runs
# only inside a Wayland session with layer-shell support (e.g. your Sway
# session) and is reported as "skipped" otherwise.
set -euo pipefail
ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
cd "$ROOT"
python3 -m unittest discover -s tests -t . -v 2>&1 | tail -n "${TEST_TAIL:-400}"
exit "${PIPESTATUS[0]}"
