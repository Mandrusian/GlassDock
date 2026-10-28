"""Which section of the dock is the pointer over, and where do extras (widgets, folders) go? Pure helpers.

The dock has a LEFT section (pinned apps, launchers, folders, Trash, and extras the user left there) and a RIGHT
section: the divider, running apps that aren't pinned, and any widgets or plugins moved there.
"""


def is_extra(item):
    """Widgets/folders from the Extensions system (they are not in config.json)."""
    return str(getattr(item, "special", "") or "").startswith("x:")


def item_zone(item):
    """'right' for right-side widgets, the divider, and running apps; 'left' for everything else."""
    if getattr(item, "side", "") == "right":
        return "right"
    return "right" if item.cfg_index < 0 and not is_extra(item) else "left"


def is_slot_item(item):
    """Items that keep a position the user chose (as opposed to dividers and running apps)."""
    return item.cfg_index >= 0 or is_extra(item)


def zone_for(pm, spans, icon):
    """pm: pointer position along the dock. spans: [(is_right, start, end)] in dock order.

    The right section starts at its first item. With none, it starts a little past the last icon, so a
    widget can be dropped there to create the section.
    """
    first_right = next((s for r, s, e in spans if r), None)
    if first_right is not None:
        return "right" if pm >= first_right else "left"
    last_end = max((e for r, s, e in spans), default=0.0)
    return "right" if pm > last_end + icon * 0.6 else "left"


def place_extras(out, entries, make, divider):
    """Insert extras into the dock's item list.

    entries: [(at, id, side)] in saved order. Left extras go at index `at` (or before Trash when unset);
    right extras are appended after everything else, behind a divider.
    """
    out = list(out)
    right = []
    for at, wid, side in entries:
        if side == "right":
            right.append(wid)
            continue
        item = make(wid, "")
        if isinstance(at, int) and not isinstance(at, bool) and 0 <= at <= len(out):
            out.insert(at, item)
        else:
            trash_i = next((i for i, existing in enumerate(out) if getattr(existing, "special", None) == "trash"), len(out))
            out.insert(trash_i, item)
    if right:
        if out and getattr(out[-1], "kind", "") != "separator" and not any(getattr(i, "key", "") == "sep:right" for i in out):
            out.append(divider())
        out.extend(make(wid, "right") for wid in right)
    return out


def reorder_extras(extras, wid, side, left_at, right_order):
    """Return the saved extras list after moving `wid` into a section.

    left_at: {id: final index} for every left extra shown (so positions are reproduced exactly);
    right_order: ids of the right extras in their new order. Entries not shown keep their place.
    """
    extras = [dict(e) for e in extras]
    if not any(e["id"] == wid for e in extras):
        return extras
    for e in extras:
        if e["id"] == wid:
            if side == "right":
                e["side"], e["at"] = "right", None
            else:
                e.pop("side", None)
        if e.get("side") != "right" and e["id"] in left_at:
            e["at"] = left_at[e["id"]]
    left = [e for e in extras if e.get("side") != "right"]
    right = [e for e in extras if e.get("side") == "right"]
    left.sort(key=lambda e: (e.get("at") is None, e.get("at") or 0))
    right.sort(key=lambda e: right_order.index(e["id"]) if e["id"] in right_order else len(right_order))
    return left + right
