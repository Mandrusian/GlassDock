"""Example GlassDock plugin: in-memory dock item activation count.

Counts are kept only in memory and reset when GlassDock restarts.
"""


class UsagePlugin:
    def on_load(self, context):
        self.stats = context["stats"]
        self.config = context.get("config", {})

    def on_click(self, item=None):
        return {"action": "toast", "message": "Usage statistics are in-memory"}

    def render(self, context=None):
        usage = self.stats.snapshot()["usage"]
        total = sum(usage.values())
        return {"label": "%d launches" % total, "icon": "utilities-system-monitor"}

    def on_tick(self, now):
        return None

    def config_schema(self):
        return {}


PLUGIN = UsagePlugin()
