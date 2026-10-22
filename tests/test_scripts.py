"""Tests for the shell scripts and the launcher environment helper.

These run entirely inside a temporary HOME; nothing on the real system is touched.
"""
import glob
import os
import shutil
import subprocess
import tempfile
import unittest

from moderndock.core.envutil import child_env

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = sorted(glob.glob(os.path.join(ROOT, "scripts", "*.sh")) + glob.glob(os.path.join(ROOT, "bin", "*")))
BASH = shutil.which("bash")


def run(args, home, **extra):
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": home, "XDG_CONFIG_HOME": os.path.join(home, ".config")}
    env["MODERNDOCK_ALLOW_ROOT"] = "1"  # tests may run as root inside containers
    env.update(extra)
    return subprocess.run(args, env=env, cwd=ROOT, capture_output=True, text=True, timeout=60)


@unittest.skipUnless(BASH, "bash required")
class ScriptSyntax(unittest.TestCase):
    def test_all_scripts_parse(self):
        for path in SCRIPTS:
            with self.subTest(script=os.path.basename(path)):
                r = subprocess.run([BASH, "-n", path], capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stderr)

    def test_scripts_are_executable(self):
        for path in SCRIPTS:
            with self.subTest(script=os.path.basename(path)):
                self.assertTrue(os.access(path, os.X_OK))


@unittest.skipUnless(BASH, "bash required")
class SwayIntegration(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.home, True)
        self.cfgdir = os.path.join(self.home, ".config", "sway")
        os.makedirs(self.cfgdir)
        self.cfg = os.path.join(self.cfgdir, "config")
        self.original = "set $mod Mod4\nbindsym $mod+Return exec foot\n"
        with open(self.cfg, "w") as f:
            f.write(self.original)
        self.script = os.path.join(ROOT, "scripts", "sway-integration.sh")

    def read(self):
        with open(self.cfg) as f:
            return f.read()

    def test_enable_adds_block_backup_and_snippet(self):
        r = run([self.script, "enable-autostart"], self.home)
        self.assertEqual(r.returncode, 0, r.stderr)
        text = self.read()
        self.assertTrue(text.startswith(self.original))
        self.assertEqual(text.count("include "), 1)
        self.assertEqual(len(glob.glob(self.cfg + ".moderndock-backup-*")), 1)
        snippet = os.path.join(self.home, ".config", "moderndock", "sway.conf")
        with open(snippet) as f:
            body = f.read()
        self.assertIn(os.path.join(ROOT, "bin", "moderndock"), body)

    def test_enable_is_idempotent(self):
        run([self.script, "enable-autostart"], self.home)
        first = self.read()
        r = run([self.script, "enable-autostart"], self.home)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.read(), first)

    def test_disable_restores_original_exactly(self):
        run([self.script, "enable-autostart"], self.home)
        r = run([self.script, "disable-autostart"], self.home)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.read(), self.original)
        self.assertFalse(os.path.exists(os.path.join(self.home, ".config", "moderndock", "sway.conf")))

    def test_handles_config_without_trailing_newline(self):
        with open(self.cfg, "w") as f:
            f.write("set $mod Mod4")
        run([self.script, "enable-autostart"], self.home)
        self.assertIn("set $mod Mod4\n# >>> moderndock", self.read())
        run([self.script, "disable-autostart"], self.home)
        self.assertEqual(self.read(), "set $mod Mod4\n")

    def test_missing_config_is_not_created_without_flag(self):
        os.remove(self.cfg)
        r = run([self.script, "enable-autostart"], self.home)
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(os.path.exists(self.cfg))

    def test_status_reports_state(self):
        self.assertIn("disabled", run([self.script, "status"], self.home).stdout)
        run([self.script, "enable-autostart"], self.home)
        self.assertIn("ENABLED", run([self.script, "status"], self.home).stdout)

    def _fake_sway(self, body):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        path = os.path.join(d, "sway")
        with open(path, "w") as f:
            f.write("#!/bin/sh\n" + body)
        os.chmod(path, 0o755)
        return d + os.pathsep + os.environ.get("PATH", "/usr/bin:/bin")

    def test_rollback_when_our_change_breaks_a_valid_config(self):
        # fake sway: rejects any config that contains our include
        path = self._fake_sway('for a; do :; done; if grep -q moderndock "$a"; then echo "bad config" >&2; exit 1; fi; exit 0\n')
        r = run([self.script, "enable-autostart"], self.home, PATH=path)
        self.assertEqual(r.returncode, 1)
        self.assertIn("bad config", r.stderr)
        self.assertEqual(self.read(), self.original)

    def test_no_rollback_when_original_was_already_invalid(self):
        path = self._fake_sway("exit 1\n")  # sway always rejects
        r = run([self.script, "enable-autostart"], self.home, PATH=path)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("# >>> moderndock", self.read())

    def test_check_blur_outside_sway_is_graceful(self):
        r = run([self.script, "check-blur"], self.home)
        self.assertEqual(r.returncode, 2)
        self.assertIn("Not inside a running Sway session", r.stdout)


@unittest.skipUnless(BASH, "bash required")
class InstallUninstall(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.home, True)
        self.bin = os.path.join(self.home, ".local", "bin")
        self.app = os.path.join(self.home, ".local", "share", "applications", "moderndock-settings.desktop")

    def test_install_then_uninstall(self):
        r = run([os.path.join(ROOT, "scripts", "install.sh"), "--no-check"], self.home)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        for cmd in ("moderndock", "moderndock-ctl", "moderndock-settings"):
            link = os.path.join(self.bin, cmd)
            self.assertTrue(os.path.islink(link))
            self.assertEqual(os.path.realpath(link), os.path.join(ROOT, "bin", cmd))
        with open(self.app) as f:
            self.assertIn("moderndock-settings", f.read())

        cfg = os.path.join(self.home, ".config", "moderndock")
        os.makedirs(cfg)
        with open(os.path.join(cfg, "config.json"), "w") as f:
            f.write("{}")
        r = run([os.path.join(ROOT, "scripts", "uninstall.sh")], self.home)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertEqual(os.listdir(self.bin), [])
        self.assertFalse(os.path.exists(self.app))
        self.assertTrue(os.path.exists(os.path.join(cfg, "config.json")), "settings must survive a normal uninstall")
        self.assertTrue(os.path.isdir(ROOT))

    def test_purge_backs_up_then_removes_config(self):
        cfg = os.path.join(self.home, ".config", "moderndock")
        os.makedirs(cfg)
        with open(os.path.join(cfg, "config.json"), "w") as f:
            f.write("{}")
        r = run([os.path.join(ROOT, "scripts", "uninstall.sh"), "--purge"], self.home)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertFalse(os.path.exists(cfg))
        self.assertEqual(len(glob.glob(os.path.join(self.home, "moderndock-config-backup-*.tar.gz"))), 1)

    def test_uninstall_leaves_foreign_files_alone(self):
        os.makedirs(self.bin)
        foreign = os.path.join(self.bin, "moderndock")
        with open(foreign, "w") as f:
            f.write("#!/bin/sh\n")
        run([os.path.join(ROOT, "scripts", "uninstall.sh")], self.home)
        self.assertTrue(os.path.exists(foreign))


class ChildEnv(unittest.TestCase):
    def test_removes_only_our_preload(self):
        env = child_env({"MODERNDOCK_PRELOAD": "/usr/lib64/libgtk-layer-shell.so.0",
                         "LD_PRELOAD": "/usr/lib64/libgtk-layer-shell.so.0:/opt/other.so", "A": "1"})
        self.assertEqual(env["LD_PRELOAD"], "/opt/other.so")
        self.assertNotIn("MODERNDOCK_PRELOAD", env)
        self.assertEqual(env["A"], "1")

    def test_drops_empty_preload(self):
        env = child_env({"MODERNDOCK_PRELOAD": "/x.so", "LD_PRELOAD": "/x.so"})
        self.assertNotIn("LD_PRELOAD", env)

    def test_untouched_without_marker(self):
        env = child_env({"LD_PRELOAD": "/opt/user.so"})
        self.assertEqual(env["LD_PRELOAD"], "/opt/user.so")


if __name__ == "__main__":
    unittest.main()
