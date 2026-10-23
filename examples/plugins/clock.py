"""Example GlassDock plugin: a digital clock item.

Copy into ~/.config/glassdock/plugins/ and add clock to the plugin
allowlist in Settings → Widgets & Extensions before adding the item.
"""
from datetime import datetime


class ClockPlugin:
    def on_load(self, context):
        self.stats = context["stats"]
        self.config = context.get("config", {})

    def on_click(self, item=None):
        return {"action": "toast", "message": "GlassDock clock plugin"}

    def render(self, context=None):
        fmt = self.config.get("format", "%H:%M")
        return {"label": datetime.now().astimezone().strftime(fmt), "icon": "clock"}

    def on_tick(self, now):
        return None

    def config_schema(self):
        return {"format": {"default": "%H:%M"}}


PLUGIN = ClockPlugin()
