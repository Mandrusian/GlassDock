"""Tiny JSON-lines control socket used by the settings app and
`moderndock-ctl` (e.g. for Sway keybindings)."""
import json
import os
import socket
import threading


def socket_path(env=None):
    env = os.environ if env is None else env
    rt = env.get("XDG_RUNTIME_DIR")
    if rt and os.path.isdir(rt):
        return os.path.join(rt, "moderndock.sock")
    return "/tmp/moderndock-%d.sock" % os.getuid()


def send_command(msg, path=None, timeout=1.5):
    """Send one command dict; returns the reply dict or None if no dock answers."""
    path = path or socket_path()
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(path)
        s.sendall((json.dumps(msg) + "\n").encode())
        buf = b""
        while b"\n" not in buf:
            chunk = s.recv(4096)
            if not chunk:
                break
            buf += chunk
        return json.loads(buf.decode() or "null")
    except (OSError, ValueError):
        return None
    finally:
        s.close()


class AlreadyRunning(Exception):
    pass


class ControlServer(threading.Thread):
    """Serves commands on a unix socket. `handler(msg) -> dict` runs in a
    worker thread, so it must only do thread-safe work (e.g. GLib.idle_add)."""

    def __init__(self, handler, path=None):
        super().__init__(daemon=True, name="control-socket")
        self.handler = handler
        self.path = path or socket_path()
        self._sock = None
        self._running = False

    def bind(self):
        if os.path.exists(self.path):
            if send_command({"cmd": "ping"}, self.path, timeout=0.5) is not None:
                raise AlreadyRunning(self.path)
            try:
                os.unlink(self.path)
            except OSError:
                pass
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.bind(self.path)
        os.chmod(self.path, 0o600)
        s.listen(8)
        self._sock = s
        self._running = True

    def stop(self):
        self._running = False
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
        try:
            os.unlink(self.path)
        except OSError:
            pass

    def run(self):
        while self._running:
            try:
                conn, _ = self._sock.accept()
            except OSError:
                break
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn):
        try:
            conn.settimeout(2.0)
            buf = b""
            while b"\n" not in buf:
                chunk = conn.recv(4096)
                if not chunk:
                    return
                buf += chunk
            try:
                msg = json.loads(buf.split(b"\n", 1)[0].decode())
                reply = self.handler(msg) if isinstance(msg, dict) else {"ok": False, "error": "bad message"}
            except ValueError:
                reply = {"ok": False, "error": "invalid JSON"}
            except Exception as exc:  # handler bug must not kill the server
                reply = {"ok": False, "error": str(exc)}
            conn.sendall((json.dumps(reply) + "\n").encode())
        except OSError:
            pass
        finally:
            conn.close()
