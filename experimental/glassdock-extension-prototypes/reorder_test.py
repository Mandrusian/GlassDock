# TEST FILE — safe to delete; does not affect originals
"""Stable-key reorder helper and a validated explicit-Euler spring integrator."""

import math
from collections.abc import Mapping


def reorder(items, source_key, target_key):
    if isinstance(items, (str, bytes)) or not hasattr(items, "__iter__"):
        raise ValueError("items must be an iterable of mappings")
    result = list(items)
    keys = []
    for item in result:
        if not isinstance(item, Mapping) or "key" not in item:
            raise ValueError("every item must be a mapping with a key")
        keys.append(item["key"])
    try:
        unique_keys = set(keys)
        hash(source_key)
        hash(target_key)
    except TypeError as exc:
        raise ValueError("item and target keys must be hashable") from exc
    if len(unique_keys) != len(keys):
        raise ValueError("item keys must be unique")
    positions = {key: index for index, key in enumerate(keys)}
    if source_key not in positions or target_key not in positions:
        raise KeyError("unknown key")
    source_index = positions[source_key]
    target_index = positions[target_key]
    moving = result.pop(source_index)
    if source_index < target_index:
        target_index -= 1
    result.insert(target_index, moving)
    return result


def _finite(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number")
    return float(value)


def spring_step(current, target, velocity, stiffness=220.0, damping=22.0, dt=1 / 60):
    current = _finite(current, "current")
    target = _finite(target, "target")
    velocity = _finite(velocity, "velocity")
    stiffness = _finite(stiffness, "stiffness")
    damping = _finite(damping, "damping")
    dt = _finite(dt, "dt")
    if stiffness <= 0 or damping < 0:
        raise ValueError("stiffness must be positive and damping must be non-negative")
    if not 0 < dt <= 0.1:
        raise ValueError("dt must be in (0, 0.1]")
    velocity += (stiffness * (target - current) - damping * velocity) * dt
    next_current = current + velocity * dt
    if not math.isfinite(next_current) or not math.isfinite(velocity):
        raise ValueError("spring step became numerically unstable")
    return next_current, velocity


if __name__ == "__main__":
    print(reorder([{"key": "a"}, {"key": "b"}, {"key": "c"}], "a", "c"))
