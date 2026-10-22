"""Environment helpers (GTK-free so they can be unit-tested).

bin/glassdock preloads libgtk-layer-shell (it must be loaded before
libwayland-client when used from Python). It records the path in
GLASSDOCK_PRELOAD so we can remove it again from the environment of every
application the dock launches.
"""
import os
import re


def child_env(env=None):
    """Environment for launched applications: ours minus the layer-shell preload."""
    env = dict(os.environ if env is None else env)
    lib = env.pop("GLASSDOCK_PRELOAD", None)
    if lib and env.get("LD_PRELOAD"):
        parts = [p for p in re.split(r"[:\s]+", env["LD_PRELOAD"]) if p and p != lib]
        if parts:
            env["LD_PRELOAD"] = ":".join(parts)
        else:
            env.pop("LD_PRELOAD", None)
    return env
