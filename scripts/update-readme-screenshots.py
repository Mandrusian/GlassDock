from html import escape
from pathlib import Path
from urllib.parse import quote
import re

root = Path(__file__).resolve().parents[1]
folder = root / "assets" / "mainscreenshots"
readme = next(
    (p for p in root.iterdir()
     if p.is_file() and p.name.lower() == "readme.md"),
    None
)

if readme is None:
    raise SystemExit("README.md not found")

extensions = {
    ".png", ".jpg", ".jpeg", ".jpe", ".jfif", ".gif", ".apng",
    ".webp", ".avif", ".svg", ".bmp", ".dib", ".tif", ".tiff",
    ".ico", ".heic", ".heif", ".jp2", ".j2k", ".jpf", ".jpx",
    ".jpm", ".mj2"
}

images = sorted(
    (p for p in folder.iterdir()
     if p.is_file() and p.suffix.lower() in extensions),
    key=lambda p: p.name.casefold()
)

if not images:
    raise SystemExit(f"No supported images found in {folder.relative_to(root)}")

cells = []
for image in images:
    relative = image.relative_to(root).as_posix()
    src = escape(quote(relative, safe="/-._"), quote=True)
    alt = escape(image.stem.replace("_", " ").replace("-", " "), quote=True)
    cells.append(f'<td><img src="{src}" alt="{alt}" width="420"></td>')

rows = []
for i in range(0, len(cells), 2):
    pair = cells[i:i + 2]
    if len(pair) == 1:
        pair.append("<td></td>")
    rows.append("<tr>" + "".join(pair) + "</tr>")

gallery = (
    "<!-- AUTO-MAINSCREENSHOTS:BEGIN -->\n"
    "## Screenshots\n\n"
    "<details>\n"
    f"<summary>View all {len(images)} screenshots</summary>\n\n"
    "<table>\n" + "\n".join(rows) + "\n</table>\n\n"
    "</details>\n"
    "<!-- AUTO-MAINSCREENSHOTS:END -->"
)

content = readme.read_text()

content = re.sub(
    r"(?s)<!-- AUTO-MAINSCREENSHOTS:BEGIN -->.*?"
    r"<!-- AUTO-MAINSCREENSHOTS:END -->",
    "",
    content
)

content = re.sub(
    r"(?ims)^[ \t]{0,3}#{1,6}[ \t]+screenshots\b[^\n]*\n"
    r".*?(?=^[ \t]{0,3}#{1,6}[ \t]+|\Z)",
    "",
    content,
    count=1
)

requirements = re.search(
    r"(?im)^[ \t]{0,3}#{1,6}[ \t]+[^\n]*\brequirements?\b[^\n]*$",
    content
)

if requirements:
    position = requirements.start()
else:
    installation = re.search(
        r"(?im)^[ \t]{0,3}#{1,6}[ \t]+[^\n]*\binstallation\b[^\n]*$",
        content
    )
    position = installation.start() if installation else len(content.rstrip())

content = (
    content[:position].rstrip()
    + "\n\n" + gallery + "\n\n"
    + content[position:].lstrip()
)

readme.write_text(content)
print(f"Added {len(images)} images from assets/mainscreenshots/")
