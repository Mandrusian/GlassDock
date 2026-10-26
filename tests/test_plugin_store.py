"""Plugin store client: index.json, autoindex fallback, checksums, offline behaviour, safe install."""
import hashlib
import json
import os
import tempfile
import threading
import unittest
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler

from glassdock import plugin_store as PS

GOOD = "from glassdock.plugin_api import PluginBase\n\n\nclass Hello(PluginBase):\n    NAME = 'Hello'\n"


class _Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self.tmp.name, "site")
        os.makedirs(self.root)
        self.srv = HTTPServer(("127.0.0.1", 0), partial(_Quiet, directory=self.root))
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = "http://127.0.0.1:%d" % self.srv.server_address[1]

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.tmp.cleanup()

    def put(self, name, text):
        with open(os.path.join(self.root, name), "w", encoding="utf-8") as fh:
            fh.write(text)

    def test_default_url_is_the_mandrusia_store(self):
        self.assertEqual(PS.DEFAULT_URL, "https://plugin.mandrusia.tech")
        self.assertEqual(PS.normalize_url(""), "https://plugin.mandrusia.tech/")

    def test_rejects_non_http_schemes(self):
        for bad in ("file:///etc", "ftp://x/y", "javascript:alert(1)", "no-scheme"):
            with self.assertRaises(PS.StoreError):
                PS.normalize_url(bad)

    def test_index_json_listing(self):
        self.put("hello.py", GOOD)
        sha = hashlib.sha256(GOOD.encode()).hexdigest()
        self.put("index.json", json.dumps({"plugins": [
            {"id": "hello", "name": "Hello", "version": "1.2", "sha256": sha, "permissions": ["network", "bogus"]},
            {"id": "evil", "file": "../etc/passwd.py"},                       # traversal -> skipped
            {"id": "other", "file": "http://elsewhere.example/x.py"},         # absolute URL -> skipped
            "garbage"]}))
        rows = PS.list_plugins(self.url)
        self.assertEqual([r["id"] for r in rows], ["hello"])
        self.assertEqual(rows[0]["permissions"], ["network"])

    def test_autoindex_fallback_with_sidecar_metadata(self):
        self.put("beta.py", GOOD)
        self.put("beta.json", json.dumps({"name": "Beta Plugin", "version": "0.3"}))
        self.put("alpha.py", GOOD)
        rows = PS.list_plugins(self.url)                       # no index.json -> parse directory listing
        self.assertEqual([r["id"] for r in rows], ["alpha", "beta"])
        self.assertEqual(rows[1]["name"], "Beta Plugin")

    def test_offline_store_raises_storeoffline(self):
        import socket
        with socket.socket() as sock:                          # a port nobody listens on
            sock.bind(("127.0.0.1", 0))
            dead = "http://127.0.0.1:%d" % sock.getsockname()[1]
        with self.assertRaises(PS.StoreOffline):
            PS.list_plugins(dead)

    def test_download_verifies_checksum_and_installs_private_file(self):
        self.put("hello.py", GOOD)
        entry = {"id": "hello", "url": self.url + "/hello.py", "sha256": hashlib.sha256(GOOD.encode()).hexdigest()}
        dest = PS.download(entry, os.path.join(self.tmp.name, "plugins"))
        self.assertEqual(open(dest, encoding="utf-8").read(), GOOD)
        self.assertEqual(os.stat(dest).st_mode & 0o777, 0o600)
        self.assertEqual(os.listdir(os.path.dirname(dest)), ["hello.py"])      # no temp litter

    def test_checksum_mismatch_and_syntax_errors_install_nothing(self):
        self.put("hello.py", GOOD)
        self.put("broken.py", "def (:\n")
        target = os.path.join(self.tmp.name, "plugins")
        with self.assertRaises(PS.StoreError):
            PS.download({"id": "hello", "url": self.url + "/hello.py", "sha256": "0" * 64}, target)
        with self.assertRaises(PS.StoreError):
            PS.download({"id": "broken", "url": self.url + "/broken.py", "sha256": ""}, target)
        self.assertFalse(os.path.exists(target) and os.listdir(target))


if __name__ == "__main__":
    unittest.main()
