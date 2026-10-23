"""Source-level checks for the AI plugin prompt in the Plugins panel."""
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AIPluginPromptTests(unittest.TestCase):
    def test_plugins_panel_exposes_copyable_ai_prompt(self):
        source = (ROOT / "glassdock" / "extension_settings.py").read_text(encoding="utf-8")
        self.assertIn("PLUGIN_AI_PROMPT", source)
        self.assertIn('Gtk.Button(label="Copy AI plugin prompt…")', source)
        self.assertIn('dialog.add_button("Copy prompt", Gtk.ResponseType.APPLY)', source)
        self.assertIn("clipboard.set_text", source)

    def test_prompt_describes_real_plugin_api_and_permissions(self):
        source = (ROOT / "glassdock" / "extension_settings.py").read_text(encoding="utf-8")
        for expected in ("glassdock.plugin_api", "PluginBase", "PERMISSIONS", "render(cr, w, h)",
                         "self.ctx.stats", "self.ctx.colors", "network", "run_commands",
                         "approved plugins run as my user"):
            self.assertIn(expected, source)


if __name__ == "__main__":
    unittest.main()
