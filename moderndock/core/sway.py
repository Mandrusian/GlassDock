"""Minimal Sway/SwayFX IPC client (i3-ipc protocol) and tree parsing."""
import json
import os
import socket
import struct
import threading
import time
from dataclasses import dataclass, field

MAGIC = b"i3-ipc"
_HEADER = struct.Struct("=6sII")

RUN_COMMAND = 0
GET_WORKSPACES = 1
SUBSCRIBE = 2
GET_OUTPUTS = 3
GET_TREE = 4
GET_VERSION = 7

EVENT_BIT = 0x80000000
EVENT_NAMES = {0: "workspace", 1: "output", 2: "mode", 3: "window", 4: "barconfig_update",
               5: "binding", 6: "shutdown", 7: "tick", 21: "input"}


class SwayError(Exception):
    pass


def socket_path(env=None):
    env = os.environ if env is None else env
    p = env.get("SWAYSOCK") or env.get("I3SOCK")
    if not p:
        raise SwayError("SWAYSOCK is not set (not running under Sway?)")
    return p


def _recv_exact(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise SwayError("connection closed")
        buf += chunk
    return buf


class SwayIPC:
    def __init__(self, path=None, timeout=3.0):
        self.path = path or socket_path()
        self.timeout = timeout
        self.sock = None
        self._lock = threading.Lock()

    def connect(self):
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(self.timeout)
        try:
            s.connect(self.path)
        except OSError as exc:
            s.close()
            raise SwayError("cannot connect to %s: %s" % (self.path, exc))
        self.sock = s

    def close(self):
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None

    def _send(self, mtype, payload=b""):
        if isinstance(payload, str):
            payload = payload.encode()
        self.sock.sendall(_HEADER.pack(MAGIC, len(payload), mtype) + payload)

    def _read(self):
        hdr = _recv_exact(self.sock, _HEADER.size)
        magic, length, mtype = _HEADER.unpack(hdr)
        if magic != MAGIC:
            raise SwayError("bad IPC magic")
        body = _recv_exact(self.sock, length) if length else b""
        return mtype, body

    def request(self, mtype, payload=b""):
        with self._lock:
            if self.sock is None:
                self.connect()
            try:
                self._send(mtype, payload)
                while True:
                    rtype, body = self._read()
                    if rtype & EVENT_BIT:
                        continue  # stray event on a query connection
                    break
            except (OSError, SwayError):
                self.close()
                raise
        try:
            return json.loads(body.decode() or "null")
        except ValueError as exc:
            raise SwayError("invalid JSON reply: %s" % exc)

    def command(self, cmd):
        """Run a sway command; returns list of {success, error?}."""
        return self.request(RUN_COMMAND, cmd)

    def command_ok(self, cmd):
        """Return (ok, error_message)."""
        try:
            res = self.command(cmd)
        except (SwayError, OSError) as exc:
            return False, str(exc)
        if isinstance(res, list):
            for r in res:
                if not r.get("success", False):
                    return False, r.get("error", "command failed")
        return True, ""

    def get_tree(self):
        return self.request(GET_TREE)

    def get_outputs(self):
        return self.request(GET_OUTPUTS)

    def get_workspaces(self):
        return self.request(GET_WORKSPACES)

    def get_version(self):
        return self.request(GET_VERSION)

    # -- events
    def subscribe(self, events):
        with self._lock:
            if self.sock is None:
                self.connect()
            self._send(SUBSCRIBE, json.dumps(events))
            _t, body = self._read()
        res = json.loads(body.decode() or "{}")
        if not res.get("success"):
            raise SwayError("subscribe failed")
        self.sock.settimeout(None)

    def read_event(self):
        mtype, body = self._read()
        if not mtype & EVENT_BIT:
            return None, None
        name = EVENT_NAMES.get(mtype & ~EVENT_BIT, str(mtype & ~EVENT_BIT))
        try:
            return name, json.loads(body.decode() or "null")
        except ValueError:
            return name, None


class EventListener(threading.Thread):
    """Background thread delivering sway events to callback(name, payload).

    Reconnects with backoff. The callback runs in this thread, so GTK code
    must hop to the main loop (GLib.idle_add)."""

    def __init__(self, callback, events=("window", "workspace", "output", "shutdown"),
                 path=None, on_state=None):
        super().__init__(daemon=True, name="sway-events")
        self.callback = callback
        self.events = list(events)
        self.path = path
        self.on_state = on_state
        self._stop = threading.Event()
        self._ipc = None

    def stop(self):
        self._stop.set()
        if self._ipc is not None:
            self._ipc.close()

    def run(self):
        backoff = 0.5
        while not self._stop.is_set():
            ipc = SwayIPC(self.path)
            self._ipc = ipc
            try:
                ipc.connect()
                ipc.subscribe(self.events)
                if self.on_state:
                    self.on_state(True)
                backoff = 0.5
                self.callback("connected", None)
                while not self._stop.is_set():
                    name, payload = ipc.read_event()
                    if name is not None:
                        self.callback(name, payload)
            except (SwayError, OSError):
                pass
            finally:
                ipc.close()
            if self.on_state:
                self.on_state(False)
            if self._stop.wait(backoff):
                break
            backoff = min(backoff * 2, 5.0)


# ------------------------------------------------------------------ parsing

@dataclass
class Window:
    id: int
    app_id: str = ""
    wm_class: str = ""
    title: str = ""
    pid: int = 0
    focused: bool = False
    urgent: bool = False
    visible: bool = False
    floating: bool = False
    fullscreen: bool = False
    output: str = ""
    workspace: str = ""
    rect: tuple = (0, 0, 0, 0)


def _walk(node, output, workspace, out):
    ntype = node.get("type")
    if ntype == "output":
        output = node.get("name", "")
    elif ntype == "workspace":
        workspace = node.get("name", "")
    children = list(node.get("nodes", [])) + list(node.get("floating_nodes", []))
    if not children and ntype in ("con", "floating_con") and node.get("id") is not None:
        app_id = node.get("app_id") or ""
        props = node.get("window_properties") or {}
        wm_class = props.get("class") or ""
        if app_id or wm_class or node.get("pid"):
            r = node.get("rect") or {}
            out.append(Window(
                id=node["id"],
                app_id=app_id,
                wm_class=wm_class,
                title=node.get("name") or "",
                pid=node.get("pid") or 0,
                focused=bool(node.get("focused")),
                urgent=bool(node.get("urgent")),
                visible=bool(node.get("visible")),
                floating=ntype == "floating_con",
                fullscreen=bool(node.get("fullscreen_mode")),
                output=output,
                workspace=workspace,
                rect=(r.get("x", 0), r.get("y", 0), r.get("width", 0), r.get("height", 0)),
            ))
        return
    for child in children:
        _walk(child, output, workspace, out)


def parse_tree(tree):
    """Flatten a GET_TREE reply into Window objects (scratchpad output
    '__i3' is skipped)."""
    out = []
    if not isinstance(tree, dict):
        return out
    for out_node in tree.get("nodes", []):
        if out_node.get("name") == "__i3":
            continue
        _walk(out_node, out_node.get("name", ""), "", out)
    return out


def parse_outputs(outputs):
    """Return [{'name','rect':(x,y,w,h),'scale','active'}] for active outputs."""
    res = []
    for o in outputs or []:
        if not o.get("active", True):
            continue
        r = o.get("rect") or {}
        res.append({
            "name": o.get("name", ""),
            "rect": (r.get("x", 0), r.get("y", 0), r.get("width", 0), r.get("height", 0)),
            "scale": o.get("scale", 1.0),
            "focused": bool(o.get("focused")),
        })
    return res


def fullscreen_outputs(windows, workspaces):
    """Names of outputs whose *visible* workspace holds a fullscreen window."""
    visible = {(w.get("output"), w.get("name")) for w in (workspaces or []) if w.get("visible")}
    res = set()
    for win in windows:
        if win.fullscreen and (win.output, win.workspace) in visible:
            res.add(win.output)
    return res
