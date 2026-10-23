# Integrated GlassDock extension module.
"""Pure (GTK-free) maths for the Japanese-fan folder: layout on an arc + staggered spring."""
import math

OUTWARD = {"bottom": (0, -1), "top": (0, 1), "left": (1, 0), "right": (-1, 0)}


def fan_layout(n, icon, spread_deg=90, radius=0):
    """Build a bounded arc layout; ``u`` points away from the dock, ``v`` sideways."""
    if isinstance(n, bool) or not isinstance(n, int) or not 0 <= n <= 14:
        raise ValueError("fan item count must be an integer from 0 to 14")
    values = (icon, spread_deg, radius)
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
        raise ValueError("fan geometry must contain finite numbers")
    if icon <= 0 or not 20 <= spread_deg <= 180 or radius < 0:
        raise ValueError("invalid fan geometry")
    if n == 0:
        return []
    if n == 1:
        return [(max(radius, icon * 1.3), 0.0, 0.0)]
    gap = icon * 1.12
    spread = math.radians(spread_deg)
    r = radius or max(icon * 1.9, gap * (n - 1) / spread)
    return [
        (r * math.cos(spread * (i / (n - 1) - 0.5)),
         r * math.sin(spread * (i / (n - 1) - 0.5)),
         spread * (i / (n - 1) - 0.5))
        for i in range(n)
    ]

def fan_bounds(layout, icon, pad=8):
    """Return the area needed around the fan origin."""
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
           for value in (icon, pad)) or icon <= 0 or pad < 0:
        raise ValueError("icon and padding must be finite and valid")
    if not layout:
        return icon + 2 * pad, icon / 2 + pad
    lu = max(u for u, _, _ in layout) + icon / 2 + pad
    hv = max(abs(v) for _, v, _ in layout) + icon / 2 + pad
    return lu, hv


def to_xy(edge, u, v, length, half):
    """Map (u,v) to drawing-area pixels. Origin (u=0) sits at the dock-side end, centred across."""
    if edge == "bottom":
        return half + v, length - u
    if edge == "top":
        return half + v, u
    if edge == "left":
        return u, half + v
    return length - u, half + v          # right


class FanAnimator:
    """Per-child damped spring toward 1.0 with a start stagger (underdamped = slight overshoot)."""

    def __init__(self, n, stagger=0.035, k=300.0, c=19.0):
        if isinstance(n, bool) or not isinstance(n, int) or not 0 <= n <= 14:
            raise ValueError("animator item count must be an integer from 0 to 14")
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
               for value in (stagger, k, c)) or stagger < 0 or k <= 0 or c < 0:
            raise ValueError("invalid spring parameters")
        self.n, self.stagger, self.k, self.c = n, float(stagger), float(k), float(c)
        self.t, self.p, self.v = 0.0, [0.0] * n, [0.0] * n

    def step(self, dt):
        if isinstance(dt, bool) or not isinstance(dt, (int, float)) or not math.isfinite(dt):
            raise ValueError("dt must be a finite number")
        dt = max(0.0, min(float(dt), 1 / 30.0))
        self.t += dt
        done = True
        for i in range(self.n):
            if self.t < i * self.stagger:
                done = False
                continue
            self.v[i] += (self.k * (1.0 - self.p[i]) - self.c * self.v[i]) * dt
            self.p[i] += self.v[i] * dt
            if abs(1.0 - self.p[i]) > 0.002 or abs(self.v[i]) > 0.02:
                done = False
        return done
