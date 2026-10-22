# Commands and keybindings

## Commands

| Command | Purpose |
| --- | --- |
| `glassdock` | Start the dock |
| `glassdock --autostart` | Start in autostart mode |
| `glassdock-settings` | Open Settings |
| `glassdock-ctl status` | Show runtime status |
| `glassdock-ctl reload` | Reload configuration |
| `glassdock-ctl toggle` | Show or hide the dock |
| `glassdock-ctl quit` | Exit the running dock |
| `glassdock-ctl launch N` | Activate dock item number N |

Run these commands inside your Wayland session.

## Dock interactions

| Action | Result |
| --- | --- |
| Click an item | Launch the app or focus its window |
| Click again | Cycle that app's windows |
| Middle-click or Shift-click | Open another window or instance |
| Drag an icon | Reorder pinned items |
| Right-click an item | Open its context menu |

Context menu options can include window selection, app actions, pin/unpin, Settings, and Quit.

## Sway keybindings

Add bindings to your Sway config:

```ini
bindsym $mod+Ctrl+d exec glassdock-ctl toggle
bindsym $mod+Ctrl+1 exec glassdock-ctl launch 1
```

GlassDock also writes commented example bindings to `~/.config/glassdock/sway.conf`.
