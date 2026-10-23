"""Guards against settings that exist in the schema but are not wired up.

These are static source checks, so they run without GTK or a display."""
import os
import re
import unittest

from glassdock.core import config as C

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


class CoverageTests(unittest.TestCase):
    def test_every_setting_is_consumed_by_the_dock(self):
        src = read("glassdock/dock.py")
        missing = [s.key for s in C.SCHEMA if ('"%s"' % s.key) not in src]
        self.assertEqual(missing, [], "settings never read by dock.py")

    def test_dock_only_reads_real_settings(self):
        src = read("glassdock/dock.py")
        used = set(re.findall(r'\bg\("([a-z_]+\.[a-z_0-9]+)"\)', src))
        used |= set(re.findall(r'getter\([^)]*\)\("([a-z_]+\.[a-z_0-9]+)"\)', src))
        self.assertTrue(used)
        self.assertEqual(sorted(used - set(C.SETTINGS)), [])

    def test_every_setting_type_has_a_settings_control(self):
        src = read("glassdock/settings.py")
        body = src.split("def make_control", 1)[1].split("def depends_met", 1)[0]
        for t in {s.type for s in C.SCHEMA}:
            self.assertTrue(re.search(r't == "%s"|t in \([^)]*"%s"' % (t, t), body),
                            "no control for type %s" % t)

    def test_settings_pages_cover_all_categories(self):
        cats = {c for c, _ in C.CATEGORIES}
        for s in C.SCHEMA:
            self.assertIn(s.category, cats, s.key)
        for c in cats:
            self.assertTrue(any(s.category == c for s in C.SCHEMA), "empty category " + c)

    def test_extensions_have_a_dedicated_sidebar_panel(self):
        categories = dict(C.CATEGORIES)
        self.assertNotIn("extensions", categories)
        extension_settings = [s for s in C.SCHEMA if s.key.startswith("extensions.")]
        self.assertTrue(extension_settings)
        self.assertTrue(all(s.category == "behavior" for s in extension_settings))
        src = read("glassdock/settings.py")
        self.assertIn('if cat in ("position", "behavior"):', src)
        self.assertIn('self.add_section("Extensions")', src)
        self.assertIn('self.add_page("extensions", "Extensions", self.extensions_panel)', src)
        self.assertIn('s.category == cat and not s.key.startswith("extensions.")', src)
        self.assertNotIn('cat == "behavior" and s.key.startswith("extensions.")', src)
        extension_src = read("glassdock/extension_settings.py")
        self.assertIn("class ExtensionSettingsDialog", extension_src)
        self.assertIn("PREFERENCE_GROUPS = (", extension_src)
        self.assertIn('"Clock & Calendar"', extension_src)
        self.assertIn('"Music Controls"', extension_src)
        self.assertNotIn("class ExtensionPreferencesPage", extension_src)

    def test_settings_app_builds_pages_from_schema(self):
        src = read("glassdock/settings.py")
        self.assertIn("for s in C.SCHEMA:", src)
        self.assertIn("SettingRow(s, self.store)", src)

    def test_monitor_override_keys_exist(self):
        for k in C.MONITOR_OVERRIDE_KEYS:
            self.assertIn(k, C.SETTINGS)

    def test_dependencies_point_at_existing_values(self):
        for s in C.SCHEMA:
            if s.depends:
                other = C.SETTINGS[s.depends[0]]
                req = s.depends[1]
                vals = req if isinstance(req, tuple) else (req,)
                if other.type == "choice":
                    allowed = [c[0] for c in other.choices]
                    for v in vals:
                        self.assertIn(v, allowed, s.key)
                elif other.type == "bool":
                    for v in vals:
                        self.assertIsInstance(v, bool, s.key)

    def test_all_python_sources_compile(self):
        for base, _dirs, files in os.walk(os.path.join(ROOT, "glassdock")):
            for fn in files:
                if fn.endswith(".py"):
                    path = os.path.join(base, fn)
                    with open(path, encoding="utf-8") as fh:
                        compile(fh.read(), path, "exec")


if __name__ == "__main__":
    unittest.main()
