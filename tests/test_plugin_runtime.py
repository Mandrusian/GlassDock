"""One plugin runtime: ordering rules, legacy-format adapter, and the extensions store's new fields."""
import json
import os
import shutil
import tempfile
import unittest

from glassdock import extras_store as X
from glassdock import plugin_api as P

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class OrderingTests(unittest.TestCase):
    def test_bundled_never_outranks_user_or_third_party_plugins(self):
        origins = {"zeta": "Installed", "alpha": "Bundled", "mid": "From store", "beta": "Custom folder", "cpu": "Bundled"}
        ordered = sorted(origins, key=lambda n: P.sort_key(n, origins[n]))
        self.assertEqual(ordered, ["beta", "mid", "zeta", "alpha", "cpu"])


class LegacyAdapterTests(unittest.TestCase):
    def test_old_style_example_plugins_run_on_the_current_runtime(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        for name in ("clock", "usage"):
            shutil.copy(os.path.join(ROOT, "examples", "plugins", name + ".py"), tmp)
        classes, errors = P.discover([tmp], allowlist=["clock", "usage"])
        self.assertEqual(errors, {})
        self.assertTrue(issubclass(classes["clock"], P.PluginBase))
        self.assertIn("format", classes["clock"].CONFIG)

    def test_only_allowlisted_modules_are_executed(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        marker = os.path.join(tmp, "ran")
        with open(os.path.join(tmp, "sneaky.py"), "w") as fh:
            fh.write("open(%r, 'w').write('x')\n" % marker)
        P.discover([tmp], allowlist=[])
        self.assertFalse(os.path.exists(marker))


class StoreFieldTests(unittest.TestCase):
    def test_origin_version_and_store_url_round_trip_and_are_validated(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        path = os.path.join(tmp, "extensions.json")
        X.save({"plugins": {"hello": {"enabled": True, "config": {}, "origin": "store", "version": "1.2"},
                            "x": {"enabled": False, "config": {}, "origin": "evil"}},
                "store_url": "https://plugin.mandrusia.tech"}, path)
        data = X.load(path)
        self.assertEqual(data["plugins"]["hello"]["origin"], "store")
        self.assertEqual(data["plugins"]["hello"]["version"], "1.2")
        self.assertNotIn("origin", data["plugins"]["x"])
        self.assertEqual(data["store_url"], "https://plugin.mandrusia.tech")
        X.save({"store_url": "javascript:alert(1)"}, path)
        self.assertEqual(X.load(path)["store_url"], "")
        json.load(open(path))                                 # still valid JSON on disk


if __name__ == "__main__":
    unittest.main()
