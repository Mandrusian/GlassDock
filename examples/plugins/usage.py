"""Example GlassDock plugin: in-memory dock item activation count.

The count resets when GlassDock restarts. It is not a system-wide usage
tracker; it only measures launches/clicks recorded by this dock process.
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
        return {"label": f"{total} launches", "icon": "utilities-system-monitor"}

    def on_tick(self, now):
        return None

    def config_schema(self):
        return {}


PLUGIN = UsagePlugin()
