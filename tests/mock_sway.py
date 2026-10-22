"""A tiny fake Sway IPC server for tests."""
import json
import os
import socket
import struct
import threading

MAGIC = b"i3-ipc"
HDR = struct.Struct("=6sII")


class MockSway(threading.Thread):
    def __init__(self, path, tree=None, outputs=None, workspaces=None):
        super().__init__(daemon=True)
        self.path = path
        self.tree = tree or {"nodes": []}
        self.outputs = outputs or []
        self.workspaces = workspaces or []
        self.commands = []
        self.fail_commands = set()
        self._subs = []
        self._lock = threading.Lock()
        self._srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        if os.path.exists(path):
            os.unlink(path)
        self._srv.bind(path)
        self._srv.listen(8)
        self._running = True

    def stop(self):
        self._running = False
        try:
            self._srv.close()
        except OSError:
            pass

    @staticmethod
    def _pack(mtype, obj):
        body = json.dumps(obj).encode()
        return HDR.pack(MAGIC, len(body), mtype) + body

    def emit(self, event_type, payload):
        data = self._pack(0x80000000 | event_type, payload)
        with self._lock:
            for c in list(self._subs):
                try:
                    c.sendall(data)
                except OSError:
                    self._subs.remove(c)

    def run(self):
        while self._running:
            try:
                conn, _ = self._srv.accept()
            except OSError:
                break
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _recv(self, conn, n):
        buf = b""
        while len(buf) < n:
            chunk = conn.recv(n - len(buf))
            if not chunk:
                raise OSError("closed")
            buf += chunk
        return buf

    def _serve(self, conn):
        try:
            while True:
                magic, length, mtype = HDR.unpack(self._recv(conn, HDR.size))
                payload = self._recv(conn, length).decode() if length else ""
                if mtype == 0:
                    self.commands.append(payload)
                    ok = payload not in self.fail_commands
                    reply = [{"success": True}] if ok else [{"success": False, "error": "nope"}]
                elif mtype == 1:
                    reply = self.workspaces
                elif mtype == 2:
                    with self._lock:
                        self._subs.append(conn)
                    reply = {"success": True}
                elif mtype == 3:
                    reply = self.outputs
                elif mtype == 4:
                    reply = self.tree
                elif mtype == 7:
                    reply = {"human_readable": "mock"}
                else:
                    reply = {}
                conn.sendall(self._pack(mtype, reply))
        except OSError:
            pass


def sample_tree():
    def win(i, app_id=None, cls=None, focused=False, fs=0, visible=True, rect=(0, 0, 800, 600), floating=False):
        n = {"id": i, "type": "floating_con" if floating else "con", "name": "win%d" % i,
             "pid": 1000 + i, "focused": focused, "visible": visible,
             "fullscreen_mode": fs, "nodes": [], "floating_nodes": [],
             "rect": dict(zip(("x", "y", "width", "height"), rect))}
        if app_id:
            n["app_id"] = app_id
        if cls:
            n["window_properties"] = {"class": cls}
        return n

    ws1 = {"type": "workspace", "name": "1", "nodes": [
        {"type": "con", "id": 90, "nodes": [win(11, app_id="firefox"), win(12, app_id="firefox", focused=True),
                                            win(13, cls="Steam")], "floating_nodes": []}],
        "floating_nodes": [win(14, app_id="org.gnome.Nautilus", floating=True)]}
    ws2 = {"type": "workspace", "name": "2", "nodes": [win(21, app_id="mpv", fs=1)], "floating_nodes": []}
    return {"nodes": [
        {"type": "output", "name": "__i3", "nodes": [{"type": "workspace", "name": "__i3_scratch",
                                                      "nodes": [win(99, app_id="hidden")], "floating_nodes": []}]},
        {"type": "output", "name": "eDP-1", "nodes": [ws1, ws2], "floating_nodes": []},
    ]}
