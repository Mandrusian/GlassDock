# Integrated GlassDock extension module.
"""Stats API shared by widgets and plugins. All reads are cheap and cached; failures return None/0."""
import glob
import math
import json
import os
import subprocess
import tempfile
import threading
import time
from urllib.parse import quote

from .extras_store import CONFIG_DIR


def _read(path):
    try:
        with open(path, "r") as fh:
            return fh.read().strip()
    except OSError:
        return None


class Stats:
    def __init__(self, usage_path=None):
        self._cpu_prev, self._cpu_val, self._cpu_t = None, 0.0, 0.0
        self._net_prev, self._net_val = None, (0.0, 0.0)
        self._weather, self._weather_t, self._weather_busy, self._weather_loc = None, 0.0, False, None
        self._weather_generation = 0
        self._lock = threading.RLock()
        self.usage_path = usage_path or os.path.join(CONFIG_DIR, "usage.json")
        self._usage = self._load_usage()

    # ---- system
    def now(self):
        return time.time()

    def cpu(self):
        """CPU busy percent 0..100 (delta since last call, cached 0.5 s)."""
        t = time.monotonic()
        if t - self._cpu_t < 0.5:
            return self._cpu_val
        raw = _read("/proc/stat")
        if raw:
            try:
                vals = [int(v) for v in raw.splitlines()[0].split()[1:]]
                if len(vals) < 5:
                    return self._cpu_val
                idle, total = vals[3] + vals[4], sum(vals)
                if self._cpu_prev and total > self._cpu_prev[1]:
                    delta = total - self._cpu_prev[1]
                    self._cpu_val = max(0.0, min(100.0, 100.0 * (1.0 - (idle - self._cpu_prev[0]) / float(delta))))
                self._cpu_prev, self._cpu_t = (idle, total), t
            except (ValueError, IndexError, ZeroDivisionError):
                return self._cpu_val
        return self._cpu_val

    def ram(self):
        """{'used_pct','used_mb','total_mb'}"""
        info = {}
        for line in (_read("/proc/meminfo") or "").splitlines():
            k, _, v = line.partition(":")
            try:
                info[k] = int(v.split()[0])
            except (ValueError, IndexError):
                pass
        total, avail = info.get("MemTotal", 0), info.get("MemAvailable", 0)
        used = max(0, total - avail)
        return {"used_pct": 100.0 * used / total if total else 0.0, "used_mb": used // 1024, "total_mb": total // 1024}

    def temp(self):
        """Hottest sensor in Celsius, or None."""
        best = None
        for p in glob.glob("/sys/class/thermal/thermal_zone*/temp") + glob.glob("/sys/class/hwmon/hwmon*/temp*_input"):
            v = _read(p)
            try:
                c = int(v) / 1000.0
                if 0 < c < 150 and (best is None or c > best):
                    best = c
            except (TypeError, ValueError):
                pass
        return best

    def battery(self):
        """{'pct','charging'} or None (works with macsmc-battery on Asahi too)."""
        for d in glob.glob("/sys/class/power_supply/*"):
            if _read(d + "/type") == "Battery":
                try:
                    pct = int(_read(d + "/capacity"))
                    return {"pct": max(0, min(100, pct)), "charging": (_read(d + "/status") or "") in ("Charging", "Full")}
                except (TypeError, ValueError):
                    return None
        return None

    def uptime(self):
        raw = _read("/proc/uptime")
        try:
            value = float(raw.split()[0]) if raw else 0.0
            return value if math.isfinite(value) and value >= 0 else 0.0
        except (ValueError, IndexError, OverflowError):
            return 0.0

    def net(self):
        """(down_bytes_per_s, up_bytes_per_s) summed over non-loopback interfaces."""
        rx = tx = 0
        for line in (_read("/proc/net/dev") or "").splitlines()[2:]:
            name, _, rest = line.partition(":")
            if name.strip() == "lo":
                continue
            f = rest.split()
            if len(f) >= 9:
                try:
                    rx, tx = rx + int(f[0]), tx + int(f[8])
                except (ValueError, OverflowError):
                    continue
        t = time.monotonic()
        if self._net_prev and t - self._net_prev[2] >= 0.5:
            dt = t - self._net_prev[2]
            self._net_val = (max(0.0, (rx - self._net_prev[0]) / dt), max(0.0, (tx - self._net_prev[1]) / dt))
            self._net_prev = (rx, tx, t)
        elif not self._net_prev:
            self._net_prev = (rx, tx, t)
        return self._net_val

    # ---- weather (network; refreshed in a thread every 15 min)
    def weather(self, location=""):
        """Return cached weather and refresh asynchronously at most every 15 minutes."""
        location = location.strip()[:100] if isinstance(location, str) else ""
        with self._lock:
            if location != self._weather_loc:
                self._weather, self._weather_t, self._weather_loc = None, 0.0, location
                self._weather_generation += 1
                self._weather_busy = False
            if not self._weather_busy and time.monotonic() - self._weather_t > 900:
                self._weather_busy = True
                generation = self._weather_generation
                threading.Thread(target=self._fetch_weather, args=(location, generation),
                                 daemon=True, name="glassdock-weather").start()
            return dict(self._weather) if isinstance(self._weather, dict) else None

    def _fetch_weather(self, loc, generation):
        result = None
        try:
            safe_location = quote(loc or "Brisbane", safe="")
            proc = subprocess.run(["curl", "-fsS", "--max-time", "8",
                                   "wttr.in/%s?format=%%t|%%C" % safe_location],
                                  capture_output=True, text=True, timeout=10, check=False)
            out = proc.stdout.strip() if proc.returncode == 0 else ""
            if "|" in out:
                temp, condition = out.split("|", 1)
                result = {"temp": temp.strip()[:24], "cond": condition.strip()[:80]}
        except (OSError, subprocess.SubprocessError):
            pass
        with self._lock:
            if generation == self._weather_generation and loc == self._weather_loc:
                self._weather = result
                self._weather_t = time.monotonic()
                self._weather_busy = False

    # ---- usage (counts launches made through the dock)
    def _load_usage(self):
        try:
            with open(self.usage_path, encoding="utf-8") as fh:
                d = json.load(fh)
            if not isinstance(d, dict):
                return {}
            clean = {}
            for key, item in list(d.items())[:10000]:
                if (isinstance(key, str) and isinstance(item, dict)
                        and isinstance(item.get("count"), int) and not isinstance(item.get("count"), bool)
                        and item["count"] >= 0 and isinstance(item.get("last_opened", 0), (int, float))
                        and math.isfinite(item.get("last_opened", 0))):
                    clean[key[:255]] = {"count": item["count"], "last_opened": float(item.get("last_opened", 0))}
            return clean
        except (OSError, ValueError, UnicodeError):
            return {}

    def record_launch(self, app_id):
        if not isinstance(app_id, str) or not app_id.strip():
            return
        with self._lock:
            entry = self._usage.setdefault(app_id[:255], {"count": 0, "last_opened": 0})
            entry["count"] += 1
            entry["last_opened"] = time.time()
            snapshot = dict((key, dict(value)) for key, value in self._usage.items())
        parent = os.path.dirname(os.path.abspath(self.usage_path))
        tmp = None
        try:
            os.makedirs(parent, mode=0o700, exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix=".usage.", suffix=".tmp", dir=parent)
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
                json.dump(snapshot, fh, ensure_ascii=False, allow_nan=False)
                fh.write("\n")
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.usage_path)
        except OSError:
            if tmp:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass

    def usage(self, app_id):
        with self._lock:
            return dict(self._usage.get(app_id, {"count": 0, "last_opened": 0}))

    def usage_top(self, n=5):
        """[(app_id, {'count','last_opened'}), ...] most-launched first."""
        if isinstance(n, bool) or not isinstance(n, int):
            n = 5
        n = max(1, min(n, 100))
        with self._lock:
            rows = [(key, dict(value)) for key, value in self._usage.items()]
        return sorted(rows, key=lambda kv: -kv[1].get("count", 0))[:n]
