# Review notes

## Fixes applied

- Fixed folder persistence to write valid JSON with an actual trailing newline, using a same-directory temporary file and atomic replacement.
- Added validation for malformed folder config, missing folder paths, invalid overrides, and duplicate folder entries.
- Fixed playerctl action reporting to use the process return code, so successful actions without stdout are not reported as failures.
- Made music rendering and hover handlers data-only; metadata refresh is explicit and throttled.
- Replaced shallow settings merging with recursive default merging and validation.
- Added validation for clock sizes, calendar ranges, fan geometry, spring integration, badge limits, and hotkey syntax.
- Hardened reorder key validation and plugin loading.
- Made plugin loading opt-in with an explicit allowlist, isolated plugin failures, and validated JSON render payloads.
- Expanded the suite from 7 basic tests to 38 tests with 67 subtest cases.

## Verification

- Unit tests passed.
- Pytest passed: 38 passed, 67 subtests passed.
- compileall passed.
- Individual module smoke tests passed.
- Three example plugins loaded and rendered using an explicit allowlist.

## Remaining work

The uploaded archive contained isolated prototypes, not the full local application. This branch does not wire features into the live GTK dock, core configuration schema, model, drawing/input dispatch, or settings UI. Headless tests do not replace Wayland/manual QA.
