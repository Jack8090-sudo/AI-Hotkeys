"""Check that the license and notice files the release must carry are present (CI licenses job, step S2).

    python scripts/ci/check_license_presence.py

Checks (all relative to the repo root):
  - LICENSE (project MIT license), ahk/license.txt (AutoHotkey GPLv2), searxng/LICENSE-searxng.txt (AGPL-3.0)
  - static/fonts/OFL-*.txt: at least one, and one for every font family shipped as .woff2
  - static/marked.min.js keeps its MIT header comment (the only copy of marked's notice in the file)
  - THIRD_PARTY_NOTICES.md (step S12)
Each file must exist and be non-empty. Exit codes: 0 ok, 1 something missing.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

REQUIRED = [
    ("LICENSE", "MIT License"),
    ("ahk/license.txt", "GNU GENERAL PUBLIC LICENSE"),
    ("searxng/LICENSE-searxng.txt", "GNU AFFERO GENERAL PUBLIC LICENSE"),
    ("THIRD_PARTY_NOTICES.md", None),
]
# Font file stem prefix -> OFL file that must cover it.
FONT_FAMILIES = {"barlow": "OFL-Barlow.txt", "ibm-plex": "OFL-IBM-Plex.txt"}
MARKED_HEADER_RE = re.compile(r"\A/\*\*.*?marked v[\d.]+.*?Copyright \(c\).*?\(MIT Licensed\).*?\*/", re.S)


def problems():
    out = []
    for rel, needle in REQUIRED:
        p = ROOT / rel
        if not p.is_file() or p.stat().st_size == 0:
            out.append(f"missing or empty: {rel}")
        elif needle and needle.lower() not in p.read_text(encoding="utf-8", errors="replace").lower():
            out.append(f"{rel} does not look like the expected license (no {needle!r})")

    fonts = ROOT / "static" / "fonts"
    ofl = sorted(fonts.glob("OFL-*.txt"))
    if not ofl:
        out.append("no static/fonts/OFL-*.txt")
    for f in ofl:
        if f.stat().st_size == 0:
            out.append(f"empty: static/fonts/{f.name}")
    for woff in sorted(fonts.glob("*.woff2")):
        family = next((k for k in FONT_FAMILIES if woff.name.startswith(k)), None)
        if family is None:
            out.append(f"font with no known license mapping: static/fonts/{woff.name}")
        elif not (fonts / FONT_FAMILIES[family]).is_file():
            out.append(f"static/fonts/{woff.name} needs static/fonts/{FONT_FAMILIES[family]}")

    marked = ROOT / "static" / "marked.min.js"
    if not marked.is_file():
        out.append("missing: static/marked.min.js")
    elif not MARKED_HEADER_RE.match(marked.read_text(encoding="utf-8", errors="replace")[:1000]):
        out.append("static/marked.min.js lost its MIT header comment")
    return out


def main():
    found = problems()
    for p in found:
        print(f"::error::{p}")
    print("ok: license files present" if not found else f"FAILED: {len(found)} problem(s)")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
