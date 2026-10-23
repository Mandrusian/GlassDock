# TEST FILE — safe to delete; does not affect originals
"""Headless widget models whose data can be adapted by a GTK/Cairo renderer."""

import calendar
import datetime as dt
import math
import subprocess
import time


def _datetime(value):
    if value is None:
        return dt.datetime.now().astimezone()
    if not isinstance(value, dt.datetime):
        raise TypeError("now must be a datetime")
    return value


def _positive_size(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("size must be a positive finite number")
    if not math.isfinite(value) or value <= 0:
        raise ValueError("size must be a positive finite number")
    return float(value)


class AnalogClock:
    def __init__(self, show_seconds=False, sweep=True):
        if not isinstance(show_seconds, bool) or not isinstance(sweep, bool):
            raise ValueError("show_seconds and sweep must be booleans")
        self.show_seconds = show_seconds
        self.sweep = sweep

    def render(self, now=None, size=64):
        now = _datetime(now)
        size = _positive_size(size)
        seconds = now.second + (now.microsecond / 1_000_000 if self.sweep else 0)
        minutes = now.minute + seconds / 60
        hours = now.hour % 12 + minutes / 60
        radius = size * 0.39
        hands = [
            ("hour", hours / 12 * 2 * math.pi, radius * 0.52, 4),
            ("minute", minutes / 60 * 2 * math.pi, radius * 0.78, 2.5),
        ]
        if self.show_seconds:
            hands.append(("second", seconds / 60 * 2 * math.pi, radius * 0.9, 1))
        return {
            "type": "analog_clock",
            "size": size,
            "center": (size / 2, size / 2),
            "radius": radius,
            "hands": [
                {
                    "name": name,
                    "angle_radians": angle - math.pi / 2,
                    "length": length,
                    "width": width,
                }
                for name, angle, length, width in hands
            ],
        }

    def on_click(self):
        return {"action": "none"}


class DigitalClock:
    def __init__(self, fmt="%H:%M", show_seconds=False):
        if not isinstance(fmt, str) or not fmt:
            raise ValueError("fmt must be a non-empty string")
        if not isinstance(show_seconds, bool):
            raise ValueError("show_seconds must be a boolean")
        self.fmt = fmt
        self.show_seconds = show_seconds

    def render(self, now=None):
        now = _datetime(now)
        fmt = self.fmt
        if self.show_seconds and "%S" not in fmt:
            fmt += ":%S"
        return {
            "type": "digital_clock",
            "text": now.strftime(fmt),
            "accessible_label": now.strftime("%A, %d %B %Y, %H:%M:%S"),
        }

    def on_click(self):
        return {"action": "none"}


class CalendarWidget:
    def __init__(self, first_weekday=0):
        if isinstance(first_weekday, bool) or not isinstance(first_weekday, int):
            raise ValueError("first_weekday must be an integer from 0 to 6")
        if not 0 <= first_weekday <= 6:
            raise ValueError("first_weekday must be an integer from 0 to 6")
        self.first_weekday = first_weekday
        self.expanded = False

    def on_click(self):
        self.expanded = not self.expanded
        return {"action": "toggle_calendar", "expanded": self.expanded}

    def render(self, year=None, month=None):
        today = dt.date.today()
        year = today.year if year is None else year
        month = today.month if month is None else month
        if isinstance(year, bool) or not isinstance(year, int) or not 1 <= year <= 9999:
            raise ValueError("year must be an integer from 1 to 9999")
        if isinstance(month, bool) or not isinstance(month, int) or not 1 <= month <= 12:
            raise ValueError("month must be an integer from 1 to 12")

        cal = calendar.Calendar(firstweekday=self.first_weekday)
        return {
            "type": "calendar",
            "year": year,
            "month": month,
            "expanded": self.expanded,
            "weekday_headers": [
                calendar.day_abbr[(self.first_weekday + i) % 7] for i in range(7)
            ],
            "weeks": cal.monthdayscalendar(year, month),
            "today": today.isoformat(),
            "accessible_label": f"{calendar.month_name[month]} {year}",
        }


class MusicWidget:
    """Explicitly refreshed playerctl adapter; rendering never starts processes."""

    ACTIONS = {"play-pause", "next", "previous"}

    def __init__(self, playerctl="playerctl", timeout=1.5, refresh_interval=2.0):
        if not isinstance(playerctl, str) or not playerctl.strip():
            raise ValueError("playerctl must be a non-empty executable name")
        for value, label in ((timeout, "timeout"), (refresh_interval, "refresh_interval")):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{label} must be a positive finite number")
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{label} must be a positive finite number")
        self.playerctl = playerctl
        self.timeout = float(timeout)
        self.refresh_interval = float(refresh_interval)
        self.hovered = False
        self.status = "Stopped"
        self.title = "Nothing playing"
        self._last_refresh_at = None

    def _run(self, *args):
        try:
            result = subprocess.run(
                [self.playerctl, *args],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False, ""
        if result.returncode != 0:
            return False, ""
        return True, result.stdout.strip()

    def refresh(self, now=None, force=False):
        """Refresh metadata outside a draw callback; returns the current view."""
        timestamp = time.monotonic() if now is None else now
        if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)):
            raise ValueError("now must be a finite monotonic timestamp")
        if not math.isfinite(timestamp):
            raise ValueError("now must be a finite monotonic timestamp")
        if (
            not force
            and self._last_refresh_at is not None
            and timestamp - self._last_refresh_at < self.refresh_interval
            and timestamp >= self._last_refresh_at
        ):
            return self.render()

        status_ok, status = self._run("status")
        title_ok, title = self._run("metadata", "--format", "{{artist}} — {{title}}")
        self.status = status if status_ok and status else "Stopped"
        self.title = title if title_ok and title else "Nothing playing"
        self._last_refresh_at = timestamp
        return self.render()

    def render(self):
        return {
            "type": "music",
            "status": self.status,
            "title": self.title,
            "controls_visible": self.hovered,
            "accessible_label": f"Music: {self.title}, {self.status}",
        }

    def on_hover(self, hovered):
        self.hovered = bool(hovered)
        return self.render()

    def on_click(self, action="play-pause"):
        if action not in self.ACTIONS:
            raise ValueError("unsupported action")
        dispatched, _ = self._run(action)
        if dispatched:
            self._last_refresh_at = None
        return {"action": action, "dispatched": dispatched}


def render_demo():
    now = dt.datetime(2026, 10, 23, 13, 5, 9, tzinfo=dt.timezone.utc)
    return {
        "analog": AnalogClock(True).render(now),
        "digital": DigitalClock("%H:%M", True).render(now),
        "calendar": CalendarWidget().render(2026, 10),
        "music": MusicWidget().render(),
    }


if __name__ == "__main__":
    import json

    print(json.dumps(render_demo(), indent=2))
