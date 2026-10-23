# TEST FILE — safe to delete; does not affect originals
"""Example plugin: local digital clock."""

import datetime


class Plugin:
    def on_load(self, context):
        self.stats = context["stats"]
        self.config = context.get("config", {})

    def on_click(self, item=None):
        return {"action": "show_clock"}

    def render(self, context=None):
        return {
            "label": datetime.datetime.now().astimezone().strftime("%H:%M"),
            "icon": "clock",
        }

    def on_tick(self, now):
        return self.render()

    def config_schema(self):
        return {"format": {"default": "%H:%M"}}


PLUGIN = Plugin()
