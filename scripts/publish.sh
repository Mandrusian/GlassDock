#!/usr/bin/env bash
# Publish this project to GitHub as "glassdock".
#
#   scripts/publish.sh                 create github.com/<you>/glassdock (public) and push
#   scripts/publish.sh --private       same, but a private repository
#   scripts/publish.sh --owner NAME    GitHub user/org (needed when `gh` is not installed)
#   scripts/publish.sh --message MSG   commit message (default: "GlassDock")
#
# Uses the GitHub CLI (`gh auth login` once) when available; otherwise it sets up the
# remote and pushes with plain git (create the empty repo on github.com first).
set -euo pipefail

ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
cd "$ROOT"
NAME="glassdock"
VIS="public"
OWNER=""
MSG="GlassDock"
OLD="modern""dock"

while [ $# -gt 0 ]; do
    case "$1" in
        --private) VIS="private" ;;
        --public) VIS="public" ;;
        --owner) OWNER="${2:?--owner needs a value}"; shift ;;
        --message) MSG="${2:?--message needs a value}"; shift ;;
        -h|--help) sed -n '2,11p' "${BASH_SOURCE[0]}"; exit 0 ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
    shift
done

command -v git >/dev/null 2>&1 || { echo "git is not installed." >&2; exit 1; }

if [ ! -d .git ]; then
    git init -q
    git checkout -q -b main 2>/dev/null || git symbolic-ref HEAD refs/heads/main
fi
if [ ! -f .gitignore ]; then
    printf '__pycache__/\n*.pyc\n.pytest_cache/\n*.corrupt-*\n*.tmp-*\n' > .gitignore
fi
if [ -z "$(git config user.name || true)" ]; then
    git config user.name "$(id -un)"
    git config user.email "$(id -un)@users.noreply.github.com"
    echo "No git identity configured; using a local one ($(git config user.email))."
fi

git add -A
if git diff --cached --quiet; then
    echo "Nothing new to commit."
else
    git commit -q -m "$MSG"
    echo "Committed."
fi
BRANCH="$(git rev-parse --abbrev-ref HEAD)"

HAVE_GH=0
if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then HAVE_GH=1; fi

if git remote get-url origin >/dev/null 2>&1; then
    URL="$(git remote get-url origin)"
    case "$URL" in
        *"$OLD"*)
            if [ "$HAVE_GH" = 1 ]; then
                echo "origin still points at the old repository ($URL): renaming it to $NAME"
                gh repo rename "$NAME" --yes
            else
                echo "origin ($URL) still points at the old repository." >&2
                echo "Rename it to '$NAME' on GitHub (Settings -> General), then run:" >&2
                echo "  git remote set-url origin git@github.com:<you>/$NAME.git && git push -u origin $BRANCH" >&2
                exit 1
            fi ;;
    esac
    git push -u origin "$BRANCH"
elif [ "$HAVE_GH" = 1 ]; then
    TARGET="$NAME"
    [ -n "$OWNER" ] && TARGET="$OWNER/$NAME"
    gh repo create "$TARGET" "--$VIS" --source . --remote origin --push \
        --description "GlassDock - a floating, glassy dock for Wayland (Sway/SwayFX, Hyprland, niri, ...)"
elif [ -n "$OWNER" ]; then
    git remote add origin "git@github.com:$OWNER/$NAME.git"
    echo "Pushing to git@github.com:$OWNER/$NAME.git (the empty repository must already exist)."
    git push -u origin "$BRANCH" || {
        echo "Push failed. Create an EMPTY repository named '$NAME' on github.com, then run:" >&2
        echo "  git push -u origin $BRANCH" >&2
        exit 1
    }
else
    echo "The GitHub CLI is not installed/logged in and no --owner was given." >&2
    echo "Either:  install gh and run 'gh auth login', then re-run this script," >&2
    echo "or:      scripts/publish.sh --owner <your-github-username>" >&2
    exit 1
fi
echo "Done: https://github.com/$(git remote get-url origin | sed -E 's#.*github.com[:/]##; s#\.git$##')"
