# GlassDock settings restoration review

This source snapshot restores the attached GTK settings app as the primary UI while retaining extension features inside the normal app.

## Kept in the default application

- Clock and calendar dock items.
- Music controls through `playerctl` and an MPRIS-compatible player, with media commands running outside the GTK event loop.
- Folder items, hidden-file visibility, a folder fan, and a folder context menu.
- Dock item badges and the `glassdock-ctl badge INDEX COUNT` command.
- Trusted Python plugins added through **Settings → Launchers → Add other → Plugin widget…**, with an explicit allowlist and trust warning.
- Existing themes, settings pages, launchers, drag reordering, monitor settings, and live config reload behaviour.

No changes were pushed to GitHub while preparing this snapshot.

## Verification

- `python3 -m compileall -q glassdock tests examples`
- `bash scripts/run-tests.sh`
- Result: 125 tests passed; 2 GTK smoke tests skipped because they require a live Sway/wlr-layer-shell session.

The tests cover the config/model integration, extension helpers, plugin allowlisting, and user-theme save/import/export. Full interactive GTK testing still needs to be run in the target desktop session.
