"""
AI-Hotkeys — parti comuni alle pagine locali (risultati e impostazioni):
caratteri, stile condiviso e impostazioni di aspetto da config.ini.
"""

import json
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
FONTS_DIR = STATIC_DIR / "fonts"

FONT_RE = re.compile(r"^/fonts/([a-z0-9-]+\.woff2)$")

# Valori ammessi e predefiniti della sezione [aspetto]
LOOK = {
    "tema": ("scuro", ("scuro", "nero", "chiaro", "sistema")),
    "colore": ("ambra", ("ambra", "ghiaccio", "menta", "corallo", "viola", "neutro")),
    "larghezza": ("normale", ("stretta", "normale", "ampia")),
    "mostra_originale": ("si", ("si", "no")),
}
TEXT_SIZE = (16, 14, 20)   # predefinito, minimo, massimo (px)


def _yes_no(value):
    v = str(value or "").strip().lower()
    if v in ("si", "sì", "yes", "true", "1", "on"):
        return "si"
    if v in ("no", "false", "0", "off"):
        return "no"
    return None


def look_settings(config):
    """Impostazioni di aspetto validate, pronte per la pagina."""
    out = {}
    for key, (default, allowed) in LOOK.items():
        value = str(config.get(key, default)).strip().lower()
        if key == "mostra_originale":
            value = _yes_no(value) or default
        out[key] = value if value in allowed else default
    try:
        size = int(str(config.get("testo", TEXT_SIZE[0])).strip())
    except ValueError:
        size = TEXT_SIZE[0]
    out["testo"] = max(TEXT_SIZE[1], min(TEXT_SIZE[2], size))
    return out


def theme_css():
    return (STATIC_DIR / "theme.css").read_text(encoding="utf-8")


def script_json(data):
    """JSON da mettere dentro <script>: niente "</script>" che chiude il tag."""
    return (
        json.dumps(data, ensure_ascii=False)
        .replace("</", "<\\/")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
        .replace("<!--", "<\\!--")
    )


def html_escape(text):
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )


def try_serve_font(handler, path):
    """Serve i caratteri da static/fonts. True se la richiesta era per un carattere."""
    m = FONT_RE.match(path)
    if not m:
        return False
    f = FONTS_DIR / m.group(1)
    if not f.is_file():
        handler.send_error(404)
        return True
    body = f.read_bytes()
    handler.send_response(200)
    handler.send_header("Content-Type", "font/woff2")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "max-age=86400")
    handler.end_headers()
    handler.wfile.write(body)
    return True
