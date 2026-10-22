import os
import tempfile
import threading
import unittest

from glassdock.core import sway as S
from tests.mock_sway import MockSway, sample_tree


class ParseTests(unittest.TestCase):
    def test_parse_tree(self):
        wins = S.parse_tree(sample_tree())
        ids = sorted(w.id for w in wins)
        self.assertEqual(ids, [11, 12, 13, 14, 21])        # scratch output skipped
        by = {w.id: w for w in wins}
        self.assertEqual(by[13].wm_class, "Steam")           # xwayland window
        self.assertTrue(by[14].floating)
        self.assertEqual(by[12].workspace, "1")
        self.assertEqual(by[12].output, "eDP-1")
        self.assertTrue(by[12].focused)
        self.assertTrue(by[21].fullscreen)

    def test_fullscreen_outputs(self):
        wins = S.parse_tree(sample_tree())
        ws_visible_1 = [{"output": "eDP-1", "name": "1", "visible": True},
                        {"output": "eDP-1", "name": "2", "visible": False}]
        self.assertEqual(S.fullscreen_outputs(wins, ws_visible_1), set())
        ws_visible_2 = [{"output": "eDP-1", "name": "1", "visible": False},
                        {"output": "eDP-1", "name": "2", "visible": True}]
        self.assertEqual(S.fullscreen_outputs(wins, ws_visible_2), {"eDP-1"})

    def test_parse_outputs(self):
        outs = S.parse_outputs([
            {"name": "eDP-1", "active": True, "rect": {"x": 0, "y": 0, "width": 1728, "height": 1117}, "scale": 2.0},
            {"name": "DP-1", "active": False, "rect": {"x": 0, "y": 0, "width": 1, "height": 1}},
        ])
        self.assertEqual([o["name"] for o in outs], ["eDP-1"])
        self.assertEqual(outs[0]["rect"], (0, 0, 1728, 1117))

    def test_garbage(self):
        self.assertEqual(S.parse_tree(None), [])
        self.assertEqual(S.parse_tree({}), [])


class IPCTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.td.name, "sway.sock")
        self.srv = MockSway(self.path, tree=sample_tree(),
                            outputs=[{"name": "eDP-1", "active": True,
                                      "rect": {"x": 0, "y": 0, "width": 1728, "height": 1117}}],
                            workspaces=[{"name": "1", "output": "eDP-1", "visible": True}])
        self.srv.start()

    def tearDown(self):
        self.srv.stop()
        self.td.cleanup()

    def test_queries_and_commands(self):
        ipc = S.SwayIPC(self.path)
        self.assertEqual(len(S.parse_tree(ipc.get_tree())), 5)
        self.assertEqual(ipc.get_outputs()[0]["name"], "eDP-1")
        self.assertEqual(ipc.get_workspaces()[0]["name"], "1")
        self.assertEqual(ipc.command_ok("[con_id=11] focus"), (True, ""))
        self.srv.fail_commands.add("bogus")
        ok, err = ipc.command_ok("bogus")
        self.assertFalse(ok)
        self.assertEqual(err, "nope")
        self.assertIn("[con_id=11] focus", self.srv.commands)
        ipc.close()

    def test_events_delivered_and_reconnect(self):
        got = []
        evt = threading.Event()

        def cb(name, payload):
            got.append(name)
            if name == "window":
                evt.set()

        listener = S.EventListener(cb, path=self.path)
        listener.start()
        for _ in range(50):
            if "connected" in got:
                break
            evt.wait(0.05)
        self.assertIn("connected", got)
        self.srv.emit(3, {"change": "new"})
        self.assertTrue(evt.wait(2))
        listener.stop()

    def test_missing_socket(self):
        with self.assertRaises(S.SwayError):
            S.SwayIPC(os.path.join(self.td.name, "nope")).get_tree()
        with self.assertRaises(S.SwayError):
            S.socket_path({})


if __name__ == "__main__":
    unittest.main()
