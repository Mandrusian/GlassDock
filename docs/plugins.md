# GlassDock plugins

Every plugin is the same kind of thing: one `.py` file with one `PluginBase` subclass. Bundled examples, plugins
you write, files you import and plugins from the store all use the same loader, the same settings card and the
same on/off switch. Nothing is loaded until you enable it, and plugins are trusted Python running as your user
(not a sandbox), so read a plugin before you turn it on.

Settings → Extensions → **Manage plugins…** has *Browse plugin store…*, *Import plugin…*, *Copy AI plugin prompt…*
and *Loading settings…*. Plugin folders: `~/.config/glassdock/plugins/` (installed/imported), the project's
`plugins/` (bundled examples) and an optional custom folder.

## Minimal plugin

```python
from glassdock.plugin_api import PluginBase

class RamRing(PluginBase):
    NAME = "RAM Ring"
    TICK = 2.0                         # seconds between on_tick calls (>= 0.2)
    PERMISSIONS = []                   # any of: "network", "run_commands"
    CONFIG = {"warn_at": {"type": "int", "default": 90, "min": 10, "max": 100, "label": "Warn above (%)"}}

    def on_tick(self):
        self.pct = self.ctx.stats.ram()["used_pct"]
        self.ctx.redraw()

    def render(self, cr, w, h):        # plain cairo, origin top-left, w x h
        ...

    def on_click(self, button):        # 1 = click, 2 = middle/shift-click; return None or a list of strings (popup)
        return None
```

`self.ctx` gives `cfg(key)`, `colors` (`accent`, `fg`, `bg`, `warn`, `ok`), `redraw()`, `notify(text)`,
`run(cmd, terminal=False)` (needs `run_commands`) and `stats`: `now() cpu() ram() temp() battery() uptime() net()
usage(app_id) usage_top(n)` plus `weather(city)` (needs `network`). Three exceptions in a row disable a plugin and
the error is shown on its card. Old-style `PLUGIN = Obj()` modules still load through a compatibility adapter.

## The plugin store

Default URL: `https://plugin.mandrusia.tech` (editable in the store window). It is a **plain static directory**:

```
index.json          optional, preferred
hello.py            one flat file per plugin (letters, digits, _ . - only)
hello.json          optional metadata when there is no index.json
```

`index.json`:

```json
{"plugins": [{"id": "hello", "name": "Hello", "version": "1.0", "author": "you",
              "description": "One line.", "file": "hello.py", "sha256": "<64 hex chars>",
              "permissions": ["network"], "homepage": "https://example.org"}]}
```

Without `index.json` GlassDock reads the server's plain directory listing and treats each `*.py` link as a plugin
(`name.json` beside it may supply the same fields). `sha256` is optional but recommended: a mismatch rejects the
download. Entries may not point at other hosts or sub-paths. Downloads are capped at 1 MiB, compiled but never
executed, written atomically with mode 0600, and registered **disabled**. If the store is unreachable the window
says so and everything else keeps working. Generate checksums with `sha256sum hello.py`.

## Write one with an AI

Settings → Extensions → Manage plugins… → *Copy AI plugin prompt…* copies a ready-made prompt. Fill the bracketed
blanks, paste it into any AI, save the returned file via *Import plugin…*, read it, then enable it.
