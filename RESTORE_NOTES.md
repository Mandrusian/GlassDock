# GlassDock finalization notes

The advanced widget/folder/icon/plugin code from the uploaded test pack has been promoted into the normal `glassdock` package. No `*_test.py` runtime modules or separate experimental UI are required at runtime.

## Integration

- The usual `bin/glassdock` launcher starts `glassdock.dock_extensions`, which subclasses and extends the existing dock runtime.
- The existing Settings sidebar is retained. Advanced controls appear inside the Launchers page expander; basic extension preferences remain grouped within Behavior.
- Advanced persistent data is stored atomically in `~/.config/glassdock/extensions.json`; app-launch usage counts are stored in `~/.config/glassdock/usage.json`.
- Plugins load only by explicit enable/allowlist. They are trusted Python code running with the current user's permissions, not a sandbox.
- Media metadata refreshes and weather lookups run off the GTK event loop; music controls use asynchronous D-Bus calls.

## Verification

- `python3 -m compileall -q glassdock tests plugins`
- `bash scripts/run-tests.sh`
- The unit/static test suite passed (full result captured when packaging). Two GTK smoke tests require a live Sway/wlr-layer-shell session and are skipped outside that session.

Interactive runtime smoke testing still needs to be done on the target desktop, because this packaging environment does not have PyGObject/GTK introspection installed.
