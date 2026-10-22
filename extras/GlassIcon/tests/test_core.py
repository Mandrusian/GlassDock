import os
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import glassicon_core as core


class GlassIconCoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="glassicon-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.data = self.home / ".local/share"
        self.config = self.home / ".config"
        self.state = self.home / ".local/state"
        for path in (self.home, self.data, self.config, self.state):
            path.mkdir(parents=True, exist_ok=True)
        patcher = mock.patch.dict(os.environ, {
            "HOME": str(self.home),
            "XDG_DATA_HOME": str(self.data),
            "XDG_CONFIG_HOME": str(self.config),
            "XDG_STATE_HOME": str(self.state),
            "XDG_DATA_DIRS": str(self.root / "system-data"),
            "XDG_CURRENT_DESKTOP": "sway",
            "DESKTOP_SESSION": "sway",
        }, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        (self.root / "system-data" / "icons").mkdir(parents=True)
        (self.data / "icons").mkdir(parents=True)
        self.create_theme("TestTheme")

    def create_theme(self, name, inherit="hicolor"):
        path = self.data / "icons" / name
        path.mkdir(parents=True, exist_ok=True)
        (path / "index.theme").write_text(
            "[Icon Theme]\n"
            f"Name={name}\n"
            "Comment=Test icon theme\n"
            f"Inherits={inherit}\n"
            "Directories=48x48/apps\n"
            "\n[48x48/apps]\nSize=48\nContext=Applications\nType=Fixed\n",
            encoding="utf-8",
        )
        return path

    def test_discovers_user_icon_themes(self):
        self.create_theme("SecondTheme")
        themes = {theme["name"]: theme for theme in core.discover_icon_themes()}
        self.assertIn("TestTheme", themes)
        self.assertIn("SecondTheme", themes)
        self.assertEqual(themes["TestTheme"]["label"], "TestTheme")

    def test_ini_update_preserves_comments_and_unrelated_keys(self):
        path = self.config / "gtk-3.0/settings.ini"
        path.parent.mkdir(parents=True)
        path.write_text("; keep this comment\n[Settings]\n# also keep\ngtk-theme-name=Adwaita\n\n[Other]\nValue=unchanged\n", encoding="utf-8")
        core.set_ini_setting(path, "Settings", "gtk-icon-theme-name", "TestTheme")
        result = path.read_text(encoding="utf-8")
        self.assertIn("; keep this comment", result)
        self.assertIn("# also keep", result)
        self.assertIn("gtk-theme-name=Adwaita", result)
        self.assertIn("gtk-icon-theme-name=TestTheme", result)
        self.assertIn("[Other]\nValue=unchanged", result)
        core.set_ini_setting(path, "Settings", "gtk-icon-theme-name", "SecondTheme")
        self.assertEqual(path.read_text(encoding="utf-8").count("gtk-icon-theme-name="), 1)
        self.assertIn("gtk-icon-theme-name=SecondTheme", path.read_text(encoding="utf-8"))

    def test_apply_theme_updates_both_gtk_settings_files(self):
        (self.config / "gtk-3.0").mkdir(parents=True)
        (self.config / "gtk-4.0").mkdir(parents=True)
        fake = lambda args, timeout=2.5: subprocess.CompletedProcess(args, 1, "", "unavailable")
        with mock.patch.object(core, "_run", side_effect=fake), mock.patch.object(core.shutil, "which", return_value=None):
            result = core.apply_icon_theme("TestTheme")
        gtk3 = (self.config / "gtk-3.0/settings.ini").read_text(encoding="utf-8")
        gtk4 = (self.config / "gtk-4.0/settings.ini").read_text(encoding="utf-8")
        self.assertIn("gtk-icon-theme-name=TestTheme", gtk3)
        self.assertIn("gtk-icon-theme-name=TestTheme", gtk4)
        self.assertEqual(result["theme"], "TestTheme")
        self.assertTrue(any("GTK 3" in message for message in result["written"]))

    def test_launcher_override_and_restore_existing_user_file(self):
        apps = self.data / "applications"
        apps.mkdir(parents=True)
        desktop = apps / "sample.desktop"
        original = "[Desktop Entry]\nType=Application\nName=Example App\nExec=example\nIcon=old-icon\n\n[Extra]\nKey=keep\n"
        desktop.write_text(original, encoding="utf-8")
        image = self.root / "new-icon.svg"
        image.write_text("<svg xmlns='http://www.w3.org/2000/svg' width='16' height='16'></svg>\n", encoding="utf-8")
        with mock.patch.object(core, "application_roots", return_value=[apps]):
            apps_found = core.discover_applications()
            sample = next((app for app in apps_found if app["id"] == "sample.desktop"), None)
            self.assertIsNotNone(sample)
            destination = core.set_application_icon("sample.desktop", image)
            modified = destination.read_text(encoding="utf-8")
            self.assertIn(f"Icon={image}", modified)
            self.assertIn("[Extra]\nKey=keep", modified)
            self.assertTrue(core.load_state()["application_overrides"]["sample.desktop"]["had_original_user_file"])
            self.assertTrue(core.reset_application_icon("sample.desktop"))
            self.assertEqual(desktop.read_text(encoding="utf-8"), original)
            self.assertFalse(core.load_state()["application_overrides"])

    def test_generated_launcher_override_is_removed_on_reset(self):
        system_apps = self.root / "system-data/applications"
        system_apps.mkdir(parents=True)
        (system_apps / "only-system.desktop").write_text(
            "[Desktop Entry]\nType=Application\nName=System app\nExec=system-app\nIcon=system-icon\n",
            encoding="utf-8",
        )
        image = self.root / "custom.png"
        image.write_bytes(b"png-placeholder")
        destination = core.set_application_icon("only-system.desktop", image)
        self.assertTrue(destination.is_file())
        self.assertTrue(core.reset_application_icon("only-system.desktop"))
        self.assertFalse(destination.exists())

    def test_system_icon_override_creates_inheriting_overlay_and_reset_removes_it(self):
        image = self.root / "folder.svg"
        image.write_text("<svg xmlns='http://www.w3.org/2000/svg'></svg>\n", encoding="utf-8")
        fake = lambda args, timeout=2.5: subprocess.CompletedProcess(args, 1, "", "unavailable")
        with mock.patch.object(core, "detect_icon_theme", return_value="TestTheme"), \
             mock.patch.object(core, "_run", side_effect=fake), \
             mock.patch.object(core.shutil, "which", return_value=None):
            result = core.set_system_icon("folder", image)
            overlay = self.data / "icons" / result["theme"]
            icon_path = overlay / "scalable/places/folder.svg"
            self.assertTrue(icon_path.is_file())
            self.assertIn("Inherits=TestTheme,hicolor", (overlay / "index.theme").read_text(encoding="utf-8"))
            self.assertTrue(core.reset_system_icon("folder"))
        self.assertFalse(overlay.exists())
        self.assertFalse(core.load_state()["system_overrides"])

    def test_switching_base_theme_keeps_custom_system_icon_overlay(self):
        self.create_theme("SecondTheme")
        image = self.root / "folder.svg"
        image.write_text("<svg xmlns='http://www.w3.org/2000/svg'></svg>\n", encoding="utf-8")
        fake = lambda args, timeout=2.5: subprocess.CompletedProcess(args, 1, "", "unavailable")
        with mock.patch.object(core, "_run", side_effect=fake), mock.patch.object(core.shutil, "which", return_value=None):
            created = core.set_system_icon("folder", image)
            overlay_name = created["theme"]
            switched = core.apply_icon_theme("SecondTheme")
        self.assertEqual(switched["theme"], overlay_name)
        self.assertEqual(core.load_state()["base_theme"], "SecondTheme")
        index = (self.data / "icons" / overlay_name / "index.theme").read_text(encoding="utf-8")
        self.assertIn("Inherits=SecondTheme,hicolor", index)
        self.assertTrue((self.data / "icons" / overlay_name / "scalable/places/folder.svg").is_file())

    def test_installs_icon_theme_archive_without_replacing_existing_theme(self):
        archive = self.root / "theme-pack.zip"
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("TestTheme-Extra/index.theme", "[Icon Theme]\nName=TestTheme\nInherits=hicolor\nDirectories=48x48/apps\n\n[48x48/apps]\nSize=48\nContext=Applications\nType=Fixed\n")
            bundle.writestr("TestTheme-Extra/48x48/apps/sample.png", b"test-icon")
        installed = core.install_icon_theme(archive)
        self.assertEqual(len(installed), 1)
        self.assertEqual(installed[0]["name"], "TestTheme-Extra")
        target = Path(installed[0]["path"])
        self.assertTrue((target / "index.theme").is_file())
        self.assertEqual((target / "48x48/apps/sample.png").read_bytes(), b"test-icon")
        self.assertIn("Name=TestTheme", (target / "index.theme").read_text(encoding="utf-8"))

    def test_rejects_archive_path_traversal(self):
        archive = self.root / "malicious.zip"
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("../../escaped.txt", "not allowed")
        with self.assertRaises(ValueError):
            core.install_icon_theme(archive)
        self.assertFalse((self.root.parent / "escaped.txt").exists())

    def test_atomic_write_supports_binary_content(self):
        path = self.root / "bytes.bin"
        core.atomic_write(path, b"\x00\x01icon")
        self.assertEqual(path.read_bytes(), b"\x00\x01icon")

    def test_desktop_icon_is_inserted_inside_section(self):
        source = "[Desktop Entry]\nType=Application\nName=Example\n\n[Extra]\nKeep=yes\n"
        result = core._replace_desktop_icon(source, "/tmp/custom icon.svg")
        self.assertIn("Name=Example\nIcon=/tmp/custom icon.svg\n\n[Extra]", result)
        self.assertIn("[Extra]\nKeep=yes", result)


if __name__ == "__main__":
    unittest.main()
