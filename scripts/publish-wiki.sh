#!/usr/bin/env bash
set -Eeuo pipefail

# Publish docs/wiki/*.md into the native GitHub Wiki repository.
# Run from any directory inside a GlassDock checkout:
#   ./scripts/publish-wiki.sh

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_DIR="$ROOT/docs/wiki"
WIKI_URL="${GLASSDOCK_WIKI_URL:-https://github.com/Mandrusian/GlassDock.wiki.git}"
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/glassdock-wiki.XXXXXX")"
WIKI_DIR="$TMP_DIR/wiki"

cleanup() {
  rm -rf -- "$TMP_DIR"
}
trap cleanup EXIT

die() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

command -v git >/dev/null 2>&1 || die "git is required."
[[ -d "$SOURCE_DIR" ]] || die "Documentation source directory not found: $SOURCE_DIR"
compgen -G "$SOURCE_DIR/*.md" >/dev/null || die "No Markdown pages found in $SOURCE_DIR"

printf 'Cloning the GlassDock GitHub Wiki…\n'
if ! git clone "$WIKI_URL" "$WIKI_DIR"; then
  cat >&2 <<'MESSAGE'

Could not clone the Wiki repository.

If this Wiki has never had a page, initialize it first:
  1. Open https://github.com/Mandrusian/GlassDock/wiki/_new
  2. Create and save a page named "Home".
  3. Run this script again.

If the Wiki already has pages, check your GitHub authentication and write access.
MESSAGE
  exit 1
fi

# Convert repository-relative Markdown links into native wiki page links and
# keep links to files in the source repository absolute.
for source in "$SOURCE_DIR"/*.md; do
  name="$(basename "$source")"
  target="$WIKI_DIR/$name"
  sed -E \
    -e 's#\]\((Home|Installation|Configuration|Commands|Troubleshooting|GlassIcon|Development)\.md\)#](\1)#g' \
    -e 's#\]\(\.\./\.\./LICENSE\)#](https://github.com/Mandrusian/GlassDock/blob/master/LICENSE)#g' \
    -e 's#\]\(\.\./\.\./installer\.sh\)#](https://github.com/Mandrusian/GlassDock/blob/master/installer.sh)#g' \
    -e 's#\]\(\.\./\.\./extras/GlassIcon/README\.md\)#](https://github.com/Mandrusian/GlassDock/blob/master/extras/GlassIcon/README.md)#g' \
    "$source" > "$target"
done

cat > "$WIKI_DIR/_Sidebar.md" <<'SIDEBAR'
## GlassDock

- [Home](Home)
- [Installation](Installation)
- [Configuration](Configuration)
- [Commands and keybindings](Commands)
- [Troubleshooting](Troubleshooting)
- [GlassIcon Studio](GlassIcon)
- [Development](Development)

---

[Source repository](https://github.com/Mandrusian/GlassDock)
[Report an issue](https://github.com/Mandrusian/GlassDock/issues)
SIDEBAR

branch="$(git -C "$WIKI_DIR" branch --show-current)"
[[ -n "$branch" ]] || branch="master"

git -C "$WIKI_DIR" add -- Home.md Installation.md Configuration.md Commands.md Troubleshooting.md GlassIcon.md Development.md _Sidebar.md

if git -C "$WIKI_DIR" diff --cached --quiet; then
  printf 'Wiki is already up to date.\n'
  exit 0
fi

git -C "$WIKI_DIR" commit -m "Publish GlassDock documentation"
git -C "$WIKI_DIR" push origin "HEAD:$branch"

printf '\nPublished GlassDock documentation to:\n'
printf '  https://github.com/Mandrusian/GlassDock/wiki\n'
