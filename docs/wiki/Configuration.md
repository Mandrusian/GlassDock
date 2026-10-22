# Configuration

GlassDock stores its configuration in:

```text
~/.config/glassdock/config.json
```

The app validates configuration when loading it. Invalid or unknown values fall back to defaults. Changes made in Settings apply live, and manual config edits are picked up automatically.

## Settings app

Use `glassdock-settings` to change options including:

- Dock edge, alignment, margins, and exclusive zone
- Icon size, spacing, and corner radius
- Colors, gradients, opacity, borders, and shadows
- Hover effects, animation, and running-app indicators
- Auto-hide and fullscreen behavior
- Per-monitor overrides
- Launchers and application-button command
- Autostart session filters

Exact options can vary with the version installed. Check the Settings app for the current list.

## Autostart

The installer adds a login entry. By default, GlassDock only autostarts in sessions listed under Settings → Behavior → Only auto-start in these sessions/WMs. The default session is `sway`; use `*` to allow all sessions.

For compositors that do not run XDG autostart, add a startup command to the compositor config.

Hyprland:

```ini
exec-once = glassdock --autostart
```

niri:

```kdl
spawn-at-startup "glassdock" "--autostart"
```

For Sway, use the helper to add a managed autostart block. It backs up the config and validates the result:

```bash
./scripts/sway-integration.sh enable-autostart
swaymsg reload
```

Remove the managed block with:

```bash
./scripts/sway-integration.sh disable-autostart
```

## Transparency and blur

GlassDock can draw a translucent surface on supported compositors. Background blur requires SwayFX with `layer_effects`; plain Sway does not provide the same blur effect.

Check support:

```bash
./scripts/sway-integration.sh check-blur
```

Reload the dock after changing relevant settings:

```bash
glassdock-ctl reload
```
