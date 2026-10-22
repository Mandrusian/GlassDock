"""Icon discovery and candidate-name tests (GTK-free)."""
import os
import shutil
import tempfile
import unittest

from glassdock.core import icons as I
from glassdock.core.desktop import DesktopEntry


class IconTests(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.home, True)
        self.env = {"HOME": self.home, "XDG_DATA_HOME": os.path.join(self.home, "data"),
                    "XDG_DATA_DIRS": os.path.join(self.home, "sys")}
        I._state.update(index=None, built=0.0)

    def touch(self, *parts):
        path = os.path.join(self.home, *parts)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "wb").close()
        return path

    def test_finds_flatpak_style_icon_and_prefers_scalable(self):
        small = self.touch("data", "icons", "hicolor", "48x48", "apps", "Foo.png")
        svg = self.touch("data", "icons", "hicolor", "scalable", "apps", "foo.svg")
        self.assertNotEqual(small, svg)
        self.assertEqual(I.find_icon_file("FOO", self.env), svg)

    def test_pixmaps_and_extension_in_name(self):
        pm = self.touch("sys", "pixmaps", "legacy.xpm")
        self.assertEqual(I.find_icon_file("legacy.xpm", self.env), pm)

    def test_apps_dir_beats_pixmaps(self):
        self.touch("sys", "pixmaps", "bar.png")
        apps = self.touch("sys", "icons", "hicolor", "64x64", "apps", "bar.png")
        self.assertEqual(I.find_icon_file("bar", self.env), apps)

    def test_symbolic_and_missing(self):
        self.touch("sys", "icons", "hicolor", "symbolic", "apps", "x-symbolic.svg")
        self.assertIsNone(I.find_icon_file("x-symbolic", self.env))
        self.assertIsNone(I.find_icon_file("nope", self.env))

    def test_absolute_missing_path_falls_back_to_basename(self):
        real = self.touch("data", "icons", "hicolor", "scalable", "apps", "baz.svg")
        self.assertEqual(I.find_icon_file("/gone/baz.png", self.env), real)

    def test_candidates_cover_entry_and_window_fallbacks(self):
        entry = DesktopEntry(id="org.mozilla.Firefox.desktop", path="", name="Mozilla Firefox",
                             icon="", exec="env A=1 /usr/bin/firefox %u",
                             startup_wm_class="Navigator")

        class Win:
            app_id = "Firefox-esr"
            wm_class = ""

        names = I.candidate_names("", entry, [Win()], entry.name)
        for want in ("org.mozilla.Firefox", "org.mozilla.firefox", "firefox", "navigator",
                     "firefox-esr", "mozilla-firefox"):
            self.assertIn(want, names)

    def test_candidates_strip_extension_but_keep_absolute(self):
        self.assertEqual(I.candidate_names("foo.PNG")[0], "foo")
        self.assertEqual(I.candidate_names("/a/b.png"), ["/a/b.png"])


if __name__ == "__main__":
    unittest.main()
