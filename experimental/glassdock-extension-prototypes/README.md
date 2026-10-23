# GlassDock extension prototypes

This directory contains headless, standard-library prototypes for possible GlassDock extensions. They do not patch or replace the live GTK application and are **not yet production-integrated dock features**.

## Test

Run from this directory:

    python3 -m unittest -v test_extensions_test.py
    python3 -m pytest -q
    python3 -m compileall -q .

Python 3.9+ is required. No third-party Python dependency is required for the prototypes. playerctl and an MPRIS-compatible player are optional.

## Modules

- badges_hotkeys_test.py: badge labels, accessible names, and portable keybinding syntax.
- dock_features_test.py: analog/digital clocks, calendar model, and music metadata/control adapter.
- dock_folders_test.py: folder persistence, child enumeration, icon overrides, and fan geometry.
- plugin_manager_test.py: explicitly allowlisted plugin host and lightweight stats API.
- reorder_test.py: stable-key reorder helper and spring step.
- settings_test.py: extension defaults, recursive merging, and settings validation.
- plugins_test/: example plugins.
- test_extensions_test.py: regression suite.

## Integration boundary

These modules return data and model behaviour. They do not wire extensions into the live core/config schema, model types, drawing/input dispatch, or settings UI. The live project must be backed up before integration, and full Wayland/manual tests are still required.

Music metadata refresh is explicit and throttled; call refresh on a scheduled non-draw path. Python plugins execute with the current user's permissions and are not sandboxed. Keep the allowlist explicit and only load reviewed code. StatsAPI.cpu_percent is a normalized load-average estimate, not process CPU usage. Weather data must be injected by the caller.

The live GlassDock architecture remains authoritative. Do not replace core modules wholesale with these prototypes.
