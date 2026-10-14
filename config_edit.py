"""
AI-Hotkeys — modifica di config.ini senza toccare commenti e ordine.

    set_values(path, {"aspetto": {"tema": "chiaro"}, "tasti": {"spiega": "End"}})

Cambia solo le righe "chiave = valore" indicate; se una chiave o una
sezione manca, la aggiunge. Mantiene la codifica (UTF-8, con o senza BOM)
e gli a capo del file (CRLF di Windows o LF).
"""

import re
from pathlib import Path

BOM = b"\xef\xbb\xbf"


def set_values(path, updates):
    path = Path(path)
    raw = path.read_bytes() if path.exists() else b""
    has_bom = raw.startswith(BOM)
    text = raw.decode("utf-8-sig")
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines()

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
            key_re = re.compile(r"^\s*" + re.escape(key) + r"\s*=", re.IGNORECASE)
            found = next((i for i in range(start + 1, end) if key_re.match(lines[i])), None)
            if found is not None:
                lines[found] = f"{key} = {value}"
                continue
            # chiave nuova: dopo l'ultima riga piena della sezione
            insert = end
            while insert > start + 1 and not lines[insert - 1].strip():
                insert -= 1
            lines.insert(insert, f"{key} = {value}")
            end += 1

    out = newline.join(lines) + newline
    path.write_bytes((BOM if has_bom else b"") + out.encode("utf-8"))


def read_values(path):
    """{sezione: {chiave: valore}} (senza commenti)."""
    out, section = {}, None
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return out
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith((";", "#")):
            continue
        m = re.match(r"^\[(.+)\]$", s)
        if m:
            section = m.group(1).strip().lower()
            out.setdefault(section, {})
            continue
        if "=" in s and section:
            k, v = s.split("=", 1)
            out[section][k.strip().lower()] = v.strip()
    return out


# ---------------------------------------------------------
# Applicazione da riga di comando (usata dall'installer):
#   python config_edit.py config.ini aspetto.tema=chiaro searxng.web_search=auto
# ---------------------------------------------------------

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Uso: config_edit.py <config.ini> sezione.chiave=valore ...")
        sys.exit(1)
    updates = {}
    for arg in sys.argv[2:]:
        name, _, value = arg.partition("=")
        section, _, key = name.partition(".")
        if not section or not key:
            print(f"Argomento non valido: {arg}")
            sys.exit(1)
        updates.setdefault(section, {})[key] = value
    set_values(sys.argv[1], updates)
