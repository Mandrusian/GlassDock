#!/usr/bin/env python3
"""glassdock-ctl: talk to the running dock (handy for Sway keybindings)."""
import json
import sys

from .core import control

USAGE = """usage: glassdock-ctl <command> [arg]

  ping            exit 0 if the dock is running
  status          print dock status as JSON
  reload          re-read the config file
  toggle          show/hide the dock (overrides auto-hide until 'auto')
  show | hide     force the dock visible / hidden
  auto            return to automatic show/hide behavior
  launch N        activate the Nth item (1-based, separators not counted)
  badge N COUNT   set an item's badge count (0 clears it; N follows Settings > Launchers order)
  quit            stop the dock
"""


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] in ("-h", "--help", "help"):
        sys.stdout.write(USAGE)
        return 0
    msg = {"cmd": argv[0]}
    if argv[0] == "launch":
        if len(argv) != 2:
            print("launch needs one item index", file=sys.stderr)
            return 2
        msg["index"] = argv[1]
    elif argv[0] == "badge":
        if len(argv) != 3:
            print("badge needs an item index and a non-negative count", file=sys.stderr)
            return 2
        try:
            if int(argv[1]) < 1 or int(argv[2]) < 0:
                raise ValueError
        except ValueError:
            print("badge expects INDEX >= 1 and COUNT >= 0", file=sys.stderr)
            return 2
        msg["index"], msg["count"] = argv[1], argv[2]
    reply = control.send_command(msg)
    if reply is None:
        print("glassdock is not running", file=sys.stderr)
        return 1
    if argv[0] == "status":
        print(json.dumps(reply, indent=2))
    elif not reply.get("ok"):
        print(reply.get("error", "failed"), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
