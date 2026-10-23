#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
python3 -m unittest -v test_extensions_test.py
python3 -m compileall -q .
