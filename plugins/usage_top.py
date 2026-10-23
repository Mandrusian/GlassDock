"""Example trusted GlassDock plugin. Review before enabling; plugin code is not sandboxed.
"""

import time

from glassdock.plugin_api import PluginBase


class UsageTop(PluginBase):
    NAME = "Most Used App"
    TICK = 3.0
    CONFIG = {"list_size": {"type": "int", "default": 5, "min": 1, "max": 10, "label": "Apps in popup"}}

    def on_tick(self):
        self.top = self.ctx.stats.usage_top(self.ctx.cfg("list_size"))
        self.ctx.redraw()

    def render(self, cr, w, h):
        top = getattr(self, "top", [])
        cr.set_source_rgba(*self.ctx.colors["fg"]); cr.select_font_face("Sans", 0, 1)
        cr.set_font_size(w * 0.34)
        n = str(top[0][1]["count"]) if top else "0"
        e = cr.text_extents(n); cr.move_to(w / 2 - e.width / 2 - e.x_bearing, h * 0.50); cr.show_text(n)
        cr.set_font_size(w * 0.13); cr.set_source_rgba(1, 1, 1, 0.7)
        nm = (top[0][0] if top else "launches")[:11]
        e = cr.text_extents(nm); cr.move_to(w / 2 - e.width / 2 - e.x_bearing, h * 0.75); cr.show_text(nm)

    def on_click(self, button):
        rows = []
        for app, u in getattr(self, "top", []):
            ago = int((time.time() - u["last_opened"]) / 60) if u["last_opened"] else 0
            rows.append("%-22s %3d launches  (last %d min ago)" % (app[:22], u["count"], ago))
        return rows or ["No launches recorded yet — launch something from the dock."]
