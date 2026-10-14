"""
AI-Hotkeys — shared Ollama connection used by all actions.
"""

import configparser
import json
import os
import re
import urllib.request
from pathlib import Path

import prompts


BASE_DIR = Path(__file__).resolve().parent
WORK_DIR = BASE_DIR / "work"
CONFIG_FILE = BASE_DIR / "config.ini"


# =========================================================
# CONFIGURATION (config.ini)
# =========================================================

DEFAULTS = {
    "model": "qwen3.5:9b",
    "ollama_url": "http://localhost:11434",
    "keep_alive": "30m",
    "todo_file": r"%USERPROFILE%\Documents\To-Do List.md",
}


def load_config():
    cfg = dict(DEFAULTS)
    parser = configparser.RawConfigParser()
    try:
        parser.read(CONFIG_FILE, encoding="utf-8-sig")
    except Exception:
        return cfg

    for section in parser.sections():
        for key, value in parser.items(section):
            if value.strip():
                cfg[key] = value.strip()
    return cfg


CONFIG = load_config()
MODEL = CONFIG["model"]
CHAT_URL = CONFIG["ollama_url"].rstrip("/") + "/api/chat"

# How long Ollama keeps the model in memory after the last request.
# Without this the default is 5 minutes: the first press after a pause
# pays for reloading the model from disk (10-20 seconds).
# Ollama accepts -1 / 0 as numbers; as text it wants a duration ("30m").
KEEP_ALIVE = CONFIG["keep_alive"]
if re.fullmatch(r"-?\d+", KEEP_ALIVE):
    KEEP_ALIVE = int(KEEP_ALIVE)


def todo_file():
    return Path(os.path.expandvars(CONFIG["todo_file"]))


# =========================================================
# REQUESTS
# =========================================================

def _options(mode):
    opts = dict(prompts.OPTIONS.get(mode, prompts.OPTIONS["explain"]))
    opts["num_ctx"] = prompts.NUM_CTX
    return opts


def _request(messages, mode, stream):
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": stream,
        "think": False,
        "keep_alive": KEEP_ALIVE,
        "options": _options(mode),
    }
    return urllib.request.Request(
        CHAT_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )


def chat(messages, mode, timeout=600):
    """Full response (no streaming)."""
    with urllib.request.urlopen(_request(messages, mode, False), timeout=timeout) as r:
        data = json.load(r)
    if data.get("error"):
        raise RuntimeError(data["error"])
    return data.get("message", {}).get("content", "")


def open_stream(messages, mode, timeout=600):
    """Open a streaming response: use with stream_pieces()."""
    return urllib.request.urlopen(_request(messages, mode, True), timeout=timeout)


def unload(timeout=30):
    """Free VRAM right away: ask Ollama to unload the model.

    This is done by sending a request with keep_alive = 0 and no prompt:
    Ollama drops the model from memory without generating anything.
    """
    url = CONFIG["ollama_url"].rstrip("/") + "/api/generate"
    req = urllib.request.Request(
        url,
        data=json.dumps({"model": MODEL, "keep_alive": 0}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        r.read()


def stream_pieces(response):
    for raw in response:
        raw = raw.strip()
        if not raw:
            continue
        chunk = json.loads(raw.decode("utf-8"))
        if chunk.get("error"):
            raise RuntimeError(chunk["error"])
        piece = chunk.get("message", {}).get("content", "")
        if piece:
            yield piece
        if chunk.get("done"):
            break


# =========================================================
# RESPONSE CLEANUP
# =========================================================

INTRO_RE = re.compile(
    r"^(ecco|di seguito|qui sotto|certo|ok|ho corretto)[^\n]{0,80}:\s*\n+",
    re.IGNORECASE,
)


def clean_answer(text, mode=None):
    text = text.replace("\r\n", "\n").strip()

    # Possible reasoning
    text = re.sub(r"(?s)^<think>.*?</think>\s*", "", text)

    # Everything wrapped in ```...```
    fence = re.match(r"(?s)^```[a-zA-Z]*\n(.*)\n```$", text)
    if fence:
        text = fence.group(1).strip()

    # Prompt tags repeated by the model
    text = re.sub(r"^</?(testo|versione_attuale|testo_originale)>\s*", "", text)
    text = re.sub(r"\s*</?(testo|versione_attuale|testo_originale)>$", "", text)

    if mode == "rewrite":
        # "Ecco il testo corretto:" at the start
        text = INTRO_RE.sub("", text, count=1)
        # Quotes around the whole text
        if len(text) > 2 and text[0] in "\"«“" and text[-1] in "\"»”" and text.count("\n") < 1:
            text = text[1:-1].strip()

    if mode == "explain":
        # Translation section we do not want
        text = re.sub(
            r"(?ims)^#{1,4}[^\n]*(traduzion|translation)[^\n]*\n.*?(?=^#{1,4} |\Z)",
            "",
            text,
        ).strip()
        # Empty sections: "## Termini tecnici\nNessuno." instead of omitting them
        text = re.sub(
            r"(?im)^#{1,4}[^\n]*\n+\s*[-*]?\s*(?:nessun[oa]?|niente|non ci sono[^\n]{0,60}|n/a|-)\.?\s*(?=\n#{1,4} |\Z)",
            "",
            text,
        )
        text = re.sub(r"\n{3,}", "\n\n", text).strip()

    return text.strip()


# =========================================================
# PgUp / PgDn / End ACTIONS
# =========================================================

def run_action(mode, argv):
    """Usage: <script> <input.txt> <output.txt>"""
    import sys
    import time

    t0 = time.time()
    input_file = Path(argv[1])
    output_file = Path(argv[2])

    testo = input_file.read_text(encoding="utf-8-sig")

    if not testo.strip():
        print("Empty text.", file=sys.stderr)
        return 1

    # End: first the web search with SearXNG (if enabled)
    fonti, query = [], []
    meta = {"mode": mode}
    if mode == "explain":
        import websearch
        try:
            fonti, query = websearch.gather_sources(testo)
        except Exception as e:
            print(f"Web search failed: {e}", file=sys.stderr)
            fonti = []
        websearch.save_sources(fonti, query)
        meta.update({"web": bool(fonti), "query": query if fonti else [], "fonti": len(fonti)})
        websearch.status("Qwen is writing the explanation…" + (f" ({len(fonti)} sources)" if fonti else " (no web)"))

    try:
        fonti_txt = websearch.sources_block(fonti) if fonti else None
        messages = prompts.first_messages(mode, testo, fonti_txt, lunghezza=CONFIG.get("lunghezza", "normale"))
        risposta = chat(messages, mode)
    except Exception as e:
        print(f"Ollama error: {e}", file=sys.stderr)
        return 1

    risposta = clean_answer(risposta, mode)
    if not risposta:
        return 1

    if fonti:
        risposta = websearch.add_sources(risposta, fonti)

    output_file.write_text(risposta, encoding="utf-8")

    # Details for the results page (time, web search done)
    meta["seconds"] = round(time.time() - t0, 1)
    try:
        (WORK_DIR / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    return 0
