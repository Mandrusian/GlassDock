import os
import tempfile
import unittest

from moderndock.core import desktop as D

SAMPLE = """\
[Desktop Entry]
Type=Application
Name=Web Browser
Name[de]=Webbrowser
Name[de_DE]=Webbrowser DE
Icon=web-browser
Exec=env FOO=1 mybrowser --new-window %U
StartupWMClass=MyBrowser
Categories=Network;WebBrowser;
Actions=new-private;

[Desktop Action new-private]
Name=New Private Window
Exec=mybrowser --private-window
"""


class DesktopTests(unittest.TestCase):
    def test_parse_and_localize(self):
        e = D.parse_desktop_text(SAMPLE, "mybrowser.desktop", locales=["de_DE", "de"])
        self.assertEqual(e.name, "Webbrowser DE")
        e = D.parse_desktop_text(SAMPLE, "mybrowser.desktop", locales=["de"])
        self.assertEqual(e.name, "Webbrowser")
        e = D.parse_desktop_text(SAMPLE, "mybrowser.desktop", locales=[])
        self.assertEqual(e.name, "Web Browser")
        self.assertEqual(e.startup_wm_class, "MyBrowser")
        self.assertEqual(e.categories, ["Network", "WebBrowser"])
        self.assertEqual(len(e.actions), 1)
        self.assertEqual(e.actions[0].name, "New Private Window")

    def test_locale_candidates(self):
        self.assertEqual(D.locale_candidates("de_DE.UTF-8@euro"), ["de_DE@euro", "de_DE", "de@euro", "de"])
        self.assertEqual(D.locale_candidates("C"), [])
        self.assertEqual(D.locale_candidates("en_AU.UTF-8"), ["en_AU", "en"])

    def test_non_application_and_nameless_rejected(self):
        self.assertIsNone(D.parse_desktop_text("[Desktop Entry]\nType=Link\nName=x\n", "x.desktop"))
        self.assertIsNone(D.parse_desktop_text("[Desktop Entry]\nType=Application\nExec=x\n", "x.desktop"))
        self.assertIsNone(D.parse_desktop_text("garbage", "x.desktop"))

    def test_expand_exec(self):
        e = D.parse_desktop_text(SAMPLE, "a.desktop", locales=[])
        self.assertEqual(D.expand_exec("app %U", e), ["app"])
        self.assertEqual(D.expand_exec("app %U", e, ["a", "b"]), ["app", "a", "b"])
        self.assertEqual(D.expand_exec("app %f", e, ["a", "b"]), ["app", "a"])
        self.assertEqual(D.expand_exec("app --file=%f", e, ["a"]), ["app", "--file=a"])
        self.assertEqual(D.expand_exec("app %i", e), ["app", "--icon", "web-browser"])
        self.assertEqual(D.expand_exec('app "two words" 100%%', e), ["app", "two words", "100%"])
        self.assertEqual(D.expand_exec("app %c", e), ["app", "Web Browser"])
        self.assertEqual(D.expand_exec("app %d %n", e), ["app"])

    def test_exec_basename(self):
        self.assertEqual(D.exec_basename("env FOO=1 /usr/bin/MyBrowser %U"), "mybrowser")
        self.assertEqual(D.exec_basename("flatpak run --branch=stable org.mozilla.firefox @@u %U @@"),
                         "org.mozilla.firefox")
        self.assertEqual(D.exec_basename("/usr/bin/foot"), "foot")

    def test_discovery_precedence_and_ids(self):
        with tempfile.TemporaryDirectory() as td:
            user = os.path.join(td, "user", "applications")
            sysd = os.path.join(td, "sys", "applications")
            os.makedirs(os.path.join(sysd, "sub"))
            os.makedirs(user)
            def w(path, name, extra=""):
                with open(path, "w") as fh:
                    fh.write("[Desktop Entry]\nType=Application\nName=%s\nExec=x\n%s" % (name, extra))
            w(os.path.join(user, "a.desktop"), "UserA")
            w(os.path.join(sysd, "a.desktop"), "SysA")
            w(os.path.join(sysd, "sub", "b.desktop"), "SubB")
            w(os.path.join(sysd, "hid.desktop"), "Hidden", "Hidden=true\n")
            w(os.path.join(user, "hid.desktop"), "UserHid", "Hidden=true\n")
            ents = D.load_entries([user, sysd], locales=[], desktop_names=[])
            self.assertEqual(ents["a.desktop"].name, "UserA")
            self.assertIn("sub-b.desktop", ents)
            self.assertNotIn("hid.desktop", ents)

    def test_find_entry_and_launchable(self):
        e = D.parse_desktop_text(SAMPLE, "x.desktop", locales=[])
        self.assertIs(D.find_entry({"x.desktop": e}, "x"), e)
        self.assertTrue(D.is_launchable(e))
        e.no_display = True
        self.assertFalse(D.is_launchable(e))


if __name__ == "__main__":
    unittest.main()
