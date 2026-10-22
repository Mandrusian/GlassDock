# Troubleshooting

## The dock does not appear

Start it from a terminal inside the Wayland session:

```bash
glassdock
glassdock-ctl status
```

Check the terminal output for missing GTK or layer-shell dependencies.

## GtkLayerShell typelib is missing

Install the runtime dependencies using the helper:

```bash
./scripts/install-deps.sh
```

Or install GTK 3, PyGObject, Pycairo, and gtk-layer-shell using your distribution's package manager.

## Running-app indicators are missing

GlassDock uses Sway IPC for window and running-app information. Start it from Sway/SwayFX so `SWAYSOCK` is available, then check:

```bash
glassdock-ctl status
```

Look for `sway_ipc` in the status output.

## Background blur does not work

Blur requires SwayFX and `layer_effects`. Plain Sway can show a translucent dock but does not provide the same background blur.

```bash
./scripts/sway-integration.sh check-blur
glassdock-ctl reload
```

## Apps show letter icons

The app may not have an icon in the active icon theme. Install an icon theme or set an icon in the application's desktop entry. GlassIcon Studio can also manage app and file-manager icons.

## Applications button does nothing

Open Settings → Behavior and check **Applications button command**. The default is `fuzzel`; install it or choose another launcher, such as `wmenu-run`.

## Dock is behind fullscreen windows

In Settings → Behavior, try **Stacking layer = Overlay** and check **Hide while fullscreen**.

## Report a bug

Include the output from `glassdock` and `glassdock-ctl status`, your compositor, and the relevant version details. Remove private information from logs before posting.
