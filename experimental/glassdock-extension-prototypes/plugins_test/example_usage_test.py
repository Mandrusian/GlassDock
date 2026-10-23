# TEST FILE — safe to delete; does not affect originals
"""Example plugin: app usage metric."""


class Plugin:
    def on_load(self, context):
        self.stats = context["stats"]
        self.config = context.get("config", {})

    def on_click(self, item=None):
        return {"action": "show_usage"}

    def render(self, context=None):
        key = self.config.get("item_key", "browser")
        return {"label": f"Opened {self.stats.usage_count(key)} times", "icon": "chart"}

    def on_tick(self, now):
        return None

    def config_schema(self):
        return {"item_key": {"default": "browser"}}


PLUGIN = Plugin()
