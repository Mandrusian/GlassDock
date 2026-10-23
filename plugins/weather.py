"""Example trusted GlassDock plugin. Review before enabling; plugin code is not sandboxed.
"""

from glassdock.plugin_api import PluginBase


class Weather(PluginBase):
    NAME = "Weather"
    TICK = 5.0
    PERMISSIONS = ["network"]
    CONFIG = {"location": {"type": "str", "default": "Brisbane", "label": "City (wttr.in)"}}

    def on_load(self):
        self.w = None

    def on_tick(self):
        self.w = self.ctx.stats.weather(self.ctx.cfg("location"))
        self.ctx.redraw()

    def render(self, cr, w, h):
        cr.set_source_rgba(*self.ctx.colors["fg"])
        cr.select_font_face("Sans", 0, 1)
        t = self.w["temp"] if self.w else "…"
        cr.set_font_size(w * (0.30 if len(t) < 6 else 0.24))
        e = cr.text_extents(t); cr.move_to(w / 2 - e.width / 2 - e.x_bearing, h * 0.52); cr.show_text(t)
        cr.set_font_size(w * 0.13); cr.set_source_rgba(1, 1, 1, 0.7)
        c = (self.w["cond"] if self.w else "loading")[:12]
        e = cr.text_extents(c); cr.move_to(w / 2 - e.width / 2 - e.x_bearing, h * 0.76); cr.show_text(c)

    def on_click(self, button):
        return ["%s: %s" % (self.ctx.cfg("location"), "%s, %s" % (self.w["temp"], self.w["cond"]) if self.w else "loading…")]

    def tooltip(self):
        return "Weather — " + self.ctx.cfg("location")
