"""Example trusted GlassDock plugin. Review before enabling; plugin code is not sandboxed.
"""

import math

from glassdock.plugin_api import PluginBase


class CpuRing(PluginBase):
    NAME = "CPU Ring"
    TICK = 1.0
    PERMISSIONS = ["run_commands"]
    CONFIG = {
        "warn_at": {"type": "int", "default": 80, "min": 10, "max": 100, "label": "Turn red above (%)"},
        "show_text": {"type": "bool", "default": True, "label": "Show percentage"},
        "click_cmd": {"type": "str", "default": "btop", "label": "Command on click (runs in terminal)"},
    }

    def on_load(self):
        self.cpu = 0.0

    def on_tick(self):
        self.cpu = self.ctx.stats.cpu()
        self.ctx.redraw()

    def render(self, cr, w, h):
        col = self.ctx.colors["warn"] if self.cpu >= self.ctx.cfg("warn_at") else self.ctx.colors["accent"]
        cx, cy, r = w / 2, h / 2, w * 0.34
        cr.set_line_width(w * 0.10)
        cr.set_source_rgba(1, 1, 1, 0.15)
        cr.arc(cx, cy, r, 0, 2 * math.pi); cr.stroke()
        cr.set_source_rgba(*col)
        cr.set_line_cap(1)
        cr.arc(cx, cy, r, -math.pi / 2, -math.pi / 2 + 2 * math.pi * self.cpu / 100.0); cr.stroke()
        if self.ctx.cfg("show_text"):
            cr.set_source_rgba(1, 1, 1, 0.95)
            cr.select_font_face("Sans", 0, 1); cr.set_font_size(w * 0.24)
            t = "%d" % self.cpu
            ext = cr.text_extents(t)
            cr.move_to(cx - ext.width / 2 - ext.x_bearing, cy + ext.height / 2); cr.show_text(t)

    def on_click(self, button):
        if button == 2:
            ram, temp = self.ctx.stats.ram(), self.ctx.stats.temp()
            return ["CPU  %.0f%%" % self.cpu, "RAM  %.0f%% (%d / %d MB)" % (ram["used_pct"], ram["used_mb"], ram["total_mb"]),
                    "Temp %s" % ("%.0f°C" % temp if temp else "n/a")]
        self.ctx.run(self.ctx.cfg("click_cmd"), terminal=True)

    def tooltip(self):
        return "CPU %.0f%%" % self.cpu
