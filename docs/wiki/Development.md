# Development

## Source layout

```text
assets/       Website and app assets
bin/          Command launchers
extras/       Companion tools, including GlassIcon Studio
glassdock/    Dock, Settings, CLI, and core modules
scripts/      Build, dependency, install, uninstall, and Sway helpers
tests/        Unit tests and test helpers
```

## Setup

Clone the repo and install dependencies:

```bash
git clone https://github.com/Mandrusian/GlassDock.git
cd GlassDock
./scripts/install-deps.sh
```

## Build checks and tests

```bash
./scripts/run-tests.sh
```

The build helper byte-compiles Python sources and checks runtime dependencies. Tests cover configuration and migration, desktop entries, Sway IPC parsing, dock models and geometry, icons, and installer scripts.

GTK smoke tests need a suitable Wayland session and may be skipped when session support is unavailable. Test actual layer-shell placement, rendering, and SwayFX blur in a real session too.

## Before opening an issue

Include:
- What you ran and what you expected
- Terminal output or relevant logs
- Output from `glassdock-ctl status`
- Compositor and distribution details

Remove private information from logs before sharing.
