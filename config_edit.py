"""
AI-Hotkeys — edit config.ini without touching comments and order.

    set_values(path, {"aspetto": {"tema": "chiaro"}, "tasti": {"spiega": "End"}})

Only changes the given "key = value" lines; if a key or a
section is missing, it adds it. Keeps the encoding (UTF-8, with or without BOM)
and the file's line endings (Windows CRLF or LF). The file is replaced
atomically: a crash while saving never leaves a half-written config.ini.
"""

import os
import re
from pathlib import Path

BOM = b"\xef\xbb\xbf"

# Only real line breaks split lines (str.splitlines() also splits on U+2028, \x0c, ...)
_LINE_SPLIT = re.compile(r"\r\n|\r|\n")
_BAD_NAME = re.compile(r"[\r\n\x00=:\[\]]")
_BAD_VALUE = re.compile(r"[\r\n\x00]")


def _lines(text):
    lines = _LINE_SPLIT.split(text)
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def _check(section, key, value):
    for kind, name in (("section", section), ("key", key)):
        if not str(name).strip() or _BAD_NAME.search(str(name)):
            raise ValueError(f"invalid {kind} name: {name!r}")
    if _BAD_VALUE.search(str(value)):
        raise ValueError(f"invalid value for {section}.{key}: line breaks are not allowed")


def set_values(path, updates):
    for section, values in updates.items():
        for key, value in values.items():
            _check(section, key, value)

    path = Path(path)
    raw = path.read_bytes() if path.exists() else b""
    has_bom = raw.startswith(BOM)
    text = raw.decode("utf-8-sig")
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = _lines(text)

    for section, values in updates.items():
        sec_re = re.compile(r"^\s*\[" + re.escape(section) + r"\]\s*$", re.IGNORECASE)
        start = next((i for i, l in enumerate(lines) if sec_re.match(l)), None)

        if start is None:
            if lines and lines[-1].strip():
                lines.append("")
            lines.append(f"[{section}]")
            lines.extend(f"{k} = {v}" for k, v in values.items())
            continue

        end = next((i for i in range(start + 1, len(lines)) if re.match(r"^\s*\[.+\]\s*$", lines[i])), len(lines))

        for key, value in values.items():
            key_re = re.compile(r"^\s*" + re.escape(key) + r"\s*[=:]", re.IGNORECASE)
            found = next((i for i in range(start + 1, end) if key_re.match(lines[i])), None)
            if found is not None:
                lines[found] = f"{key} = {value}"
                continue
            # new key: after the last non-empty line of the section
            insert = end
            while insert > start + 1 and not lines[insert - 1].strip():
                insert -= 1
            lines.insert(insert, f"{key} = {value}")
            end += 1

    out = newline.join(lines) + newline
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_bytes((BOM if has_bom else b"") + out.encode("utf-8"))
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def read_values(path):
    """{section: {key: value}} (without comments)."""
    out, section = {}, None
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return out
    for line in _lines(text):
        s = line.strip()
        if not s or s.startswith((";", "#")):
            continue
        m = re.match(r"^\[(.+)\]$", s)
        if m:
            section = m.group(1).strip().lower()
            out.setdefault(section, {})
            continue
        kv = re.match(r"^([^=:]+?)\s*[=:]\s*(.*)$", s)
        if kv and section:
            out[section][kv.group(1).strip().lower()] = kv.group(2).strip()
    return out


# ---------------------------------------------------------
# Command-line tool:
#   python config_edit.py config.ini aspetto.tema=chiaro searxng.web_search=auto
# ---------------------------------------------------------

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: config_edit.py <config.ini> section.key=value ...")
        sys.exit(1)
    updates = {}
    for arg in sys.argv[2:]:
        name, _, value = arg.partition("=")
        section, _, key = name.partition(".")
        if not section or not key:
            print(f"Invalid argument: {arg}")
            sys.exit(1)
        updates.setdefault(section, {})[key] = value
    try:
        set_values(sys.argv[1], updates)
    except ValueError as e:
        print(e)
        sys.exit(1)
