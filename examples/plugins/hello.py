"""Smallest useful GlassDock plugin: shows the current minute and greets on click.

Copy into ~/.config/glassdock/plugins/ (or use Settings -> Extensions -> Manage plugins -> Import plugin),
then enable it there and press "Add to dock".
"""
import time

from glassdock.plugin_api import PluginBase


class Hello(PluginBase):
    NAME = "Hello"
    TICK = 1.0
    CONFIG = {"greeting": {"type": "str", "default": "Hello from GlassDock", "label": "Greeting"}}

    def on_tick(self):
        self.ctx.redraw()

    def render(self, cr, w, h):
        cr.set_source_rgba(*self.ctx.colors["fg"])
        cr.select_font_face("Sans", 0, 1)
        cr.set_font_size(w * 0.34)
        text = time.strftime("%M")
        ext = cr.text_extents(text)
        cr.move_to(w / 2 - ext.width / 2 - ext.x_bearing, h / 2 + ext.height / 2)
        cr.show_text(text)

    def on_click(self, button):
        return [self.ctx.cfg("greeting")]

    def tooltip(self):
        return self.ctx.cfg("greeting")
