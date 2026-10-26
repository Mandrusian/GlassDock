"""Plugin store client.

The store is a plain static file directory (no server code), by default
https://plugin.mandrusia.tech. Two layouts are understood:

* ``index.json`` -- ``{"plugins": [{"id", "name", "version", "description", "author",
  "file", "sha256", "permissions", "homepage"}]}`` (preferred; "file" is relative).
* A bare directory listing (nginx/Apache autoindex): every ``*.py`` link is a plugin and an
  optional sidecar ``<id>.json`` next to it supplies the same metadata fields.

Downloads are size-capped, checked against ``sha256`` when the store provides one, compiled
(never executed) and installed *disabled*. Nothing here imports GTK, so it is fully testable.
"""
import hashlib
import json
import os
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

DEFAULT_URL = "https://plugin.mandrusia.tech"
MAX_INDEX_BYTES = 1024 * 1024
MAX_PLUGIN_BYTES = 1024 * 1024
TIMEOUT = 8
USER_AGENT = "GlassDock-plugin-store/1"
_ID_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}\Z")
_FILE_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,100}\.py\Z")
_SHA_RE = re.compile(r"[0-9a-fA-F]{64}\Z")


class StoreError(Exception):
    """Raised with a short, user-presentable message."""


class StoreOffline(StoreError):
    """The store could not be reached (not yet live, no network, DNS, timeout...)."""


def normalize_url(url):
    url = (url or "").strip() or DEFAULT_URL
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("https", "http") or not parts.netloc:
        raise StoreError("Store URL must start with https:// (or http:// for a local mirror).")
    return url.rstrip("/") + "/"


def _fetch(url, limit):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:       # noqa: S310 - scheme checked
            data = resp.read(limit + 1)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise StoreError("Not found: %s" % url)
        raise StoreOffline("The store answered with HTTP %d." % exc.code)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise StoreOffline("Could not reach the plugin store (%s)." % getattr(exc, "reason", exc))
    if len(data) > limit:
        raise StoreError("Download is larger than the %d KiB limit." % (limit // 1024))
    return data


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)


def _clean_entry(raw, base):
    """Validate one store entry; returns a dict or None (bad entries are skipped, not fatal)."""
    if not isinstance(raw, dict):
        return None
    file_ = raw.get("file")
    pid = raw.get("id") or (os.path.basename(file_)[:-3] if isinstance(file_, str) and file_.endswith(".py") else "")
    if not isinstance(pid, str) or not _ID_RE.fullmatch(pid):
        return None
    file_ = file_ if isinstance(file_, str) and file_ else pid + ".py"
    if not _FILE_RE.fullmatch(file_):                          # flat directory only: no paths, no URLs
        return None
    url = urllib.parse.urljoin(base, urllib.parse.quote(file_))
    if urllib.parse.urlsplit(url).netloc != urllib.parse.urlsplit(base).netloc:
        return None                                           # never follow an index to another host
    sha = raw.get("sha256")
    perms = raw.get("permissions", [])
    text = lambda k, n: (raw.get(k) if isinstance(raw.get(k), str) else "")[:n]          # noqa: E731
    return {
        "id": pid, "name": text("name", 80) or pid, "version": text("version", 32),
        "description": text("description", 400), "author": text("author", 80),
        "homepage": text("homepage", 300), "url": url,
        "sha256": sha.lower() if isinstance(sha, str) and _SHA_RE.fullmatch(sha) else "",
        "permissions": [p for p in perms if p in ("network", "run_commands")] if isinstance(perms, list) else [],
    }


def list_plugins(url=None):
    """-> list of entry dicts, sorted by name. Raises StoreOffline / StoreError."""
    base = normalize_url(url)
    try:
        data = json.loads(_fetch(base + "index.json", MAX_INDEX_BYTES).decode("utf-8"))
        rows = data.get("plugins") if isinstance(data, dict) else data
        if not isinstance(rows, list):
            raise StoreError("index.json has no plugin list.")
    except StoreOffline:
        raise
    except (StoreError, ValueError, UnicodeError):
        rows = _from_directory_listing(base)
    out, seen = [], set()
    for raw in rows[:500]:
        entry = _clean_entry(raw, base)
        if entry and entry["id"] not in seen:
            seen.add(entry["id"])
            out.append(entry)
    return sorted(out, key=lambda e: e["name"].casefold())


def _from_directory_listing(base):
    parser = _Links()
    parser.feed(_fetch(base, MAX_INDEX_BYTES).decode("utf-8", "replace"))
    rows = []
    for href in parser.links:
        name = urllib.parse.unquote(href.split("?")[0].split("#")[0])
        if name.endswith(".py") and "/" not in name:
            row = {"file": name}
            try:                                                  # optional sidecar metadata
                side = json.loads(_fetch(base + urllib.parse.quote(name[:-3] + ".json"), 64 * 1024).decode("utf-8"))
                if isinstance(side, dict):
                    row.update(side, file=name)
            except (StoreError, ValueError, UnicodeError):
                pass
            rows.append(row)
    return rows


def download(entry, directory):
    """Fetch, verify, compile and atomically write ``<id>.py`` into ``directory`` (never executes it).

    Returns the destination path. Raises StoreError on any problem; nothing is left half-written.
    """
    code_bytes = _fetch(entry["url"], MAX_PLUGIN_BYTES)
    if entry.get("sha256") and hashlib.sha256(code_bytes).hexdigest() != entry["sha256"]:
        raise StoreError("Checksum mismatch for %s -- the download was rejected." % entry["id"])
    try:
        code = code_bytes.decode("utf-8")
        compile(code, entry["id"] + ".py", "exec")
    except (UnicodeError, SyntaxError, ValueError) as exc:
        raise StoreError("%s is not a valid Python plugin: %s" % (entry["id"], exc))
    if not _ID_RE.fullmatch(entry["id"]):
        raise StoreError("Invalid plugin id.")
    os.makedirs(directory, mode=0o700, exist_ok=True)
    dest = os.path.join(directory, entry["id"] + ".py")
    fd, tmp = tempfile.mkstemp(prefix="." + entry["id"] + ".", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(code)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, dest)
    except Exception:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise
    return dest
