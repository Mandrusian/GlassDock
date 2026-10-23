"""User themes: save the current look, import and export theme files.

Only appearance keys are imported from files. Every value is validated by the
same configuration coercion used by Settings, so theme files cannot change
commands, behavior, monitor configuration, or launchers.
"""
import json
import os
import re

from . import config as C
from .themes import CUSTOM, THEMES

PREFIX = "user:"
FORMAT = "glassdock-theme"
VERSION = 1
MAX_BYTES = 64 * 1024
MAX_THEMES = 200
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class ThemeError(ValueError):
    """Raised with a message safe to show to the user."""


def themes_dir(env=None):
    return os.path.join(C.config_dir(env), "themes")


def is_user(name):
    return isinstance(name, str) and name.startswith(PREFIX) and bool(SLUG_RE.fullmatch(name[len(PREFIX):]))


def slugify(text):
    slug = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")[:48].strip("-")
    return slug or "theme"


def clean_text(value, limit):
    text = _CONTROL.sub(" ", value if isinstance(value, str) else "")
    return " ".join(text.split())[:limit]


def current_values(cfg):
    return {key: C.get_path(cfg, key) for key in C.THEME_KEYS}


def validate_theme(data):
    if not isinstance(data, dict):
        raise ThemeError("This isn't a GlassDock theme file.")
    if data.get("format") not in (None, FORMAT):
        raise ThemeError("This isn't a GlassDock theme file.")
    version = data.get("version", VERSION)
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise ThemeError("This theme file has an invalid version.")
    if version > VERSION:
        raise ThemeError("This theme was made with a newer GlassDock. Update GlassDock to use it.")
    label = clean_text(data.get("name"), 60)
    if not label:
        raise ThemeError("The theme has no name.")
    raw = data.get("values")
    if not isinstance(raw, dict):
        raise ThemeError("The theme has no settings in it.")
    values, ignored = {}, []
    for key, value in raw.items():
        if key not in C.THEME_KEYS:
            ignored.append(str(key)[:60])
            continue
        try:
            values[key] = C.coerce(C.SETTINGS[key], value)
        except (ValueError, TypeError):
            ignored.append(str(key)[:60])
    if not values:
        raise ThemeError("The theme doesn't contain any usable appearance settings.")
    for key in C.THEME_KEYS:
        values.setdefault(key, C.default_value(key))
    return {"label": label, "description": clean_text(data.get("description"), 200),
            "values": values, "ignored": ignored}


def to_file_dict(label, description, values):
    return {"format": FORMAT, "version": VERSION, "name": clean_text(label, 60),
            "description": clean_text(description, 200),
            "values": {key: values[key] for key in sorted(values) if key in C.THEME_KEYS}}


def _write_json(path, obj):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = "%s.tmp-%d" % (path, os.getpid())
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)
    finally:
        try:
            if os.path.exists(tmp):
                os.unlink(tmp)
        except OSError:
            pass


def _read_json(path):
    try:
        size = os.path.getsize(path)
    except OSError as exc:
        raise ThemeError("Couldn't read that file (%s)." % (exc.strerror or "error")) from exc
    if size > MAX_BYTES:
        raise ThemeError("That file is too large to be a theme (limit %d KB)." % (MAX_BYTES // 1024))
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except UnicodeDecodeError as exc:
        raise ThemeError("That file isn't text, so it can't be a theme.") from exc
    except (ValueError, RecursionError) as exc:
        raise ThemeError("That file isn't valid JSON, so it can't be a theme.") from exc
    except OSError as exc:
        raise ThemeError("Couldn't read that file (%s)." % (exc.strerror or "error")) from exc


def list_user_themes(directory=None):
    directory = directory or themes_dir()
    themes, problems = {}, []
    try:
        files = sorted(name for name in os.listdir(directory) if name.endswith(".json"))
    except OSError:
        return themes, problems
    for filename in files[:MAX_THEMES]:
        slug = filename[:-5]
        if not SLUG_RE.fullmatch(slug):
            problems.append("%s: file name isn't a valid theme id" % filename)
            continue
        path = os.path.join(directory, filename)
        try:
            info = validate_theme(_read_json(path))
        except ThemeError as exc:
            problems.append("%s: %s" % (filename, exc))
            continue
        info.update(user=True, path=path)
        themes[PREFIX + slug] = info
    return themes, problems


def unique_slug(base, directory=None):
    directory = directory or themes_dir()
    slug, number = base, 2
    while os.path.exists(os.path.join(directory, slug + ".json")):
        suffix = "-%d" % number
        slug = base[:48 - len(suffix)] + suffix
        number += 1
    return slug


def _check_room(directory):
    try:
        count = sum(1 for name in os.listdir(directory) if name.endswith(".json"))
    except OSError:
        count = 0
    if count >= MAX_THEMES:
        raise ThemeError("You already have %d saved themes. Delete some first." % MAX_THEMES)


def save_theme(cfg, label, description="", directory=None):
    directory = directory or themes_dir()
    label = clean_text(label, 60)
    if not label:
        raise ThemeError("Give the theme a name.")
    _check_room(directory)
    slug = unique_slug(slugify(label), directory)
    _write_json(os.path.join(directory, slug + ".json"), to_file_dict(label, description, current_values(cfg)))
    return PREFIX + slug


def import_file(path, directory=None):
    directory = directory or themes_dir()
    info = validate_theme(_read_json(path))
    _check_room(directory)
    slug = unique_slug(slugify(info["label"]), directory)
    _write_json(os.path.join(directory, slug + ".json"),
                to_file_dict(info["label"], info["description"], info["values"]))
    return PREFIX + slug, info


def export_file(info, path):
    if not path:
        raise ThemeError("No file chosen.")
    try:
        _write_json(path, to_file_dict(info["label"], info.get("description", ""), info["values"]))
    except OSError as exc:
        raise ThemeError("Couldn't write the file (%s)." % (exc.strerror or "error")) from exc


def rename_theme(name, new_label, directory=None):
    directory = directory or themes_dir()
    if not is_user(name):
        raise ThemeError("Only your own themes can be renamed.")
    new_label = clean_text(new_label, 60)
    if not new_label:
        raise ThemeError("Give the theme a name.")
    path = os.path.join(directory, name[len(PREFIX):] + ".json")
    info = validate_theme(_read_json(path))
    _write_json(path, to_file_dict(new_label, info["description"], info["values"]))


def delete_theme(name, directory=None):
    directory = directory or themes_dir()
    if not is_user(name):
        raise ThemeError("Only your own themes can be deleted.")
    try:
        os.remove(os.path.join(directory, name[len(PREFIX):] + ".json"))
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise ThemeError("Couldn't delete the theme (%s)." % (exc.strerror or "error")) from exc
    return True


def apply_values(cfg, info, name):
    for key, value in info["values"].items():
        if key in C.THEME_KEYS:
            C.set_path(cfg, key, C.coerce(C.SETTINGS[key], value))
    cfg["theme"] = name
    return cfg


def matches(cfg, info):
    try:
        return all(C.get_path(cfg, key) == C.coerce(C.SETTINGS[key], value)
                   for key, value in info["values"].items() if key in C.THEME_KEYS)
    except (ValueError, TypeError, KeyError):
        return False


def all_themes(user):
    merged = {name: dict(theme, user=False) for name, theme in THEMES.items()}
    merged.update(user)
    return merged


def label_for(name, user):
    if name == CUSTOM:
        return "Custom"
    info = all_themes(user).get(name)
    if info:
        return info["label"]
    return "Custom" if is_user(name) else str(name)
