# TEST FILE — safe to delete; does not affect originals
"""Example plugin: weather comes from an injected provider; no network requests."""


class Plugin:
    def on_load(self, context):
        self.stats = context["stats"]
        self.config = context.get("config", {})

    def on_click(self, item=None):
        return {"action": "refresh_weather"}

    def render(self, context=None):
        city = self.config.get("location", "Brisbane")
        return {
            "label": str(self.stats.weather(city) or "Weather provider not configured"),
            "icon": "weather",
        }

    def on_tick(self, now):
        return None

    def config_schema(self):
        return {"location": {"default": "Brisbane"}}


PLUGIN = Plugin()
