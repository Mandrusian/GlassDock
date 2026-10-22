"""Color parsing helpers. Colors are RGBA float tuples in 0..1."""
import re

_NAMED = {
    "white": (1.0, 1.0, 1.0, 1.0),
    "black": (0.0, 0.0, 0.0, 1.0),
    "transparent": (0.0, 0.0, 0.0, 0.0),
}

_HEX = re.compile(r"#([0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})")
_FUNC = re.compile(r"rgba?\(([^)]*)\)")


def parse_color(value):
    """Parse '#rgb', '#rgba', '#rrggbb', '#rrggbbaa', 'rgb()/rgba()' or a few names.

    Raises ValueError for anything else.
    """
    if isinstance(value, (tuple, list)) and len(value) in (3, 4):
        vals = [float(v) for v in value]
        if len(vals) == 3:
            vals.append(1.0)
        return tuple(min(1.0, max(0.0, v)) for v in vals)
    if not isinstance(value, str):
        raise ValueError("not a color: %r" % (value,))
    s = value.strip().lower()
    if s in _NAMED:
        return _NAMED[s]
    m = _HEX.fullmatch(s)
    if m:
        h = m.group(1)
        if len(h) in (3, 4):
            h = "".join(ch * 2 for ch in h)
        if len(h) == 6:
            h += "ff"
        r, g, b, a = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4, 6))
        return (r, g, b, a)
    m = _FUNC.fullmatch(s)
    if m:
        parts = [p.strip() for p in m.group(1).split(",")]
        if len(parts) not in (3, 4):
            raise ValueError("bad rgb() color: %r" % value)
        rgb = []
        for p in parts[:3]:
            if p.endswith("%"):
                rgb.append(float(p[:-1]) / 100.0)
            else:
                rgb.append(float(p) / 255.0)
        a = float(parts[3]) if len(parts) == 4 else 1.0
        return tuple(min(1.0, max(0.0, v)) for v in (*rgb, a))
    raise ValueError("unrecognised color: %r" % value)


def is_valid_color(value):
    try:
        parse_color(value)
        return True
    except (ValueError, TypeError):
        return False


def to_hex(rgba):
    """Return '#rrggbb' (alpha dropped)."""
    r, g, b = (int(round(min(1.0, max(0.0, c)) * 255)) for c in rgba[:3])
    return "#%02x%02x%02x" % (r, g, b)


def normalize_color(value):
    """Normalise any accepted color string to '#rrggbb'. Alpha is ignored:
    opacity is a separate setting."""
    return to_hex(parse_color(value))


def with_alpha(rgba, alpha):
    return (rgba[0], rgba[1], rgba[2], min(1.0, max(0.0, alpha)))
