"""
AI-Hotkeys — shared Ollama connection used by all actions.
"""

import configparser
import json
import os
import re
import traceback
import urllib.error
import urllib.request
from pathlib import Path

from prompt_loader import PROMPTS_WARNING
from prompt_loader import prompts


BASE_DIR = Path(__file__).resolve().parent
WORK_DIR = BASE_DIR / "work"
CONFIG_FILE = BASE_DIR / "config.ini"

# Error shown by main.ahk when an action fails (line 1 = message for the user)
ERROR_FILE = WORK_DIR / "error.txt"
# Problems found in config.ini (one per line), shown by main.ahk after a reload
CONFIG_WARNING_FILE = WORK_DIR / "config_warning.txt"

# Oldest Ollama known to accept "think": false (sent with every request)
MIN_OLLAMA_VERSION = (0, 9, 0)


# =========================================================
# CONFIGURATION (config.ini)
# =========================================================

DEFAULTS = {
    "model": "qwen3.5:9b",
    "ollama_url": "http://localhost:11434",
    "keep_alive": "30m",
    "todo_file": r"%USERPROFILE%\Documents\To-Do List.md",
}

CONFIG_WARNINGS = []


def _unquote(value):
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1].strip()
    return value


def load_config():
    """Settings from config.ini merged over DEFAULTS.

    A config.ini that cannot be read falls back to the defaults, and the reason
    goes into CONFIG_WARNINGS (written to work/config_warning.txt).
    """
    cfg = dict(DEFAULTS)
    CONFIG_WARNINGS.clear()
    parser = configparser.RawConfigParser()
    try:
        parser.read(CONFIG_FILE, encoding="utf-8-sig")
    except UnicodeDecodeError:
        CONFIG_WARNINGS.append("config.ini is not saved as UTF-8: using the default settings. "
                               "Open it in Notepad and save it with UTF-8 encoding.")
        return cfg
    except configparser.Error as e:
        first = str(e).strip().splitlines()[0][:160]
        CONFIG_WARNINGS.append(f"config.ini has an error, using the default settings: {first}")
        return cfg

    for section in parser.sections():
        for key, value in parser.items(section):
            value = _unquote(value.strip())
            if value:
                cfg[key] = value
    return cfg


def _write_atomic(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _write_config_warnings():
    lines = CONFIG_WARNINGS + ([PROMPTS_WARNING] if PROMPTS_WARNING else [])
    try:
        if lines:
            _write_atomic(CONFIG_WARNING_FILE, "\n".join(lines) + "\n")
        elif CONFIG_WARNING_FILE.exists():
            CONFIG_WARNING_FILE.unlink()
    except OSError:
        pass


CONFIG = load_config()
MODEL = CONFIG["model"]
OLLAMA_URL = CONFIG["ollama_url"].rstrip("/")
CHAT_URL = OLLAMA_URL + "/api/chat"

# How long Ollama keeps the model in memory after the last request.
# Without this the default is 5 minutes: the first press after a pause
# pays for reloading the model from disk (10-20 seconds).
# Ollama accepts -1 / 0 as numbers; as text it wants a duration ("30m").
KEEP_ALIVE = CONFIG["keep_alive"]
if re.fullmatch(r"-?\d+", KEEP_ALIVE):
    KEEP_ALIVE = int(KEEP_ALIVE)

_write_config_warnings()


def todo_file():
    return Path(os.path.expandvars(CONFIG["todo_file"]))


# =========================================================
# ERRORS (work/error.txt, read by main.ahk)
# =========================================================

class TruncatedAnswer(RuntimeError):
    """Ollama stopped because the answer reached num_predict."""


class StreamIncomplete(RuntimeError):
    """A streamed answer ended without Ollama's final "done" chunk."""


def describe_error(exc):
    """(message for the user, technical detail) for an exception."""
    detail = f"{type(exc).__name__}: {exc}"
    if isinstance(exc, urllib.error.HTTPError):
        err = ""
        try:
            body = exc.read().decode("utf-8", "replace")
            try:
                err = str(json.loads(body).get("error", ""))
            except Exception:
                err = body.strip()
        except Exception:
            pass
        detail = f"HTTP {exc.code}: {err or exc.reason}"
        if exc.code == 404:
            return f"Model '{MODEL}' not found: run  ollama pull {MODEL}", detail
        return f"Ollama returned an error (HTTP {exc.code}): {err[:120]}".rstrip(": "), detail
    reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
    if isinstance(reason, TimeoutError):
        return "Ollama did not answer in time. Try again, or select less text.", detail
    if isinstance(exc, (urllib.error.URLError, ConnectionError)):
        return "Ollama is not running: start Ollama, then try again.", detail
    if isinstance(exc, (TruncatedAnswer, StreamIncomplete)):
        return str(exc), detail
    if isinstance(exc, RuntimeError) and "not found" in str(exc).lower():
        return f"Model '{MODEL}' not found: run  ollama pull {MODEL}", detail
    return f"Something went wrong: {str(exc)[:150]}", detail


def write_error(message, detail=""):
    """Write work/error.txt: line 1 is shown to the user by main.ahk."""
    text = message.replace("\n", " ").strip()[:200] + "\n" + (detail.strip() + "\n" if detail else "")
    try:
        _write_atomic(ERROR_FILE, text)
    except OSError:
        pass


def clear_error():
    try:
        ERROR_FILE.unlink()
    except OSError:
        pass


# =========================================================
# REQUESTS
# =========================================================

# Ollama runs on this PC: never send its requests through a system proxy.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


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


def chat_ex(messages, mode, timeout=600):
    """Full response (no streaming): (text, done_reason)."""
    with _OPENER.open(_request(messages, mode, False), timeout=timeout) as r:
        data = json.load(r)
    if data.get("error"):
        raise RuntimeError(data["error"])
    return data.get("message", {}).get("content", ""), data.get("done_reason")


def chat(messages, mode, timeout=600):
    """Full response text (no streaming)."""
    return chat_ex(messages, mode, timeout)[0]


def open_stream(messages, mode, timeout=600):
    """Open a streaming response: use with stream_pieces()."""
    return _OPENER.open(_request(messages, mode, True), timeout=timeout)


def unload(timeout=30):
    """Free VRAM right away: ask Ollama to unload the model.

    This is done by sending a request with keep_alive = 0 and no prompt:
    Ollama drops the model from memory without generating anything.
    """
    req = urllib.request.Request(
        OLLAMA_URL + "/api/generate",
        data=json.dumps({"model": MODEL, "keep_alive": 0}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with _OPENER.open(req, timeout=timeout) as r:
        r.read()


def stream_pieces(response):
    """Text pieces of a streamed answer; StreamIncomplete if it stops before "done"."""
    done = False
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
            done = True
            if chunk.get("done_reason") == "length":
                raise TruncatedAnswer("The answer was cut off (too long for the model).")
            break
    if not done:
        raise StreamIncomplete("The answer was interrupted before the end.")


def _version_tuple(text):
    return tuple(int(n) for n in re.findall(r"\d+", str(text))[:3])


def health(timeout=3):
    """(ok, message): is Ollama running, recent enough, and is the model there?"""
    try:
        with _OPENER.open(OLLAMA_URL + "/api/version", timeout=timeout) as r:
            version = json.load(r).get("version", "")
        with _OPENER.open(OLLAMA_URL + "/api/tags", timeout=timeout) as r:
            names = [m.get("name", "") for m in json.load(r).get("models", [])]
    except Exception as e:
        return False, describe_error(e)[0]
    if version and _version_tuple(version) < MIN_OLLAMA_VERSION:
        need = ".".join(map(str, MIN_OLLAMA_VERSION))
        return False, f"Ollama {version} is too old: update it to {need} or newer."
    wanted = MODEL if ":" in MODEL else MODEL + ":latest"
    if wanted not in names:
        return False, f"Model '{MODEL}' not found: run  ollama pull {MODEL}"
    return True, f"Ollama {version}, model {MODEL} ready."


# =========================================================
# RESPONSE CLEANUP
# =========================================================

INTRO_RE = re.compile(
    r"^(ecco|di seguito|qui sotto|certo|ok|ho corretto)\b[^\n]{0,80}:\s*\n+",
    re.IGNORECASE,
)

# A section that only says "nothing here" ("## Termini tecnici\nNessuno.")
_EMPTY_BODY_RE = re.compile(
    r"[-*]?\s*(?:nessun[oa]?|niente|non ci sono[^\n]{0,60}|n/a|-)\.?",
    re.IGNORECASE,
)


def _drop_empty_sections(text):
    """Remove headings whose whole body is "Nessuno." / "n/a" / "-" (line by line, linear time)."""
    lines = text.split("\n")
    out, i = [], 0
    while i < len(lines):
        if re.match(r"#{1,4}", lines[i]):
            j = i + 1
            while j < len(lines) and not re.match(r"#{1,4} ", lines[j]):
                j += 1
            body = "\n".join(lines[i + 1:j]).strip()
            if body and _EMPTY_BODY_RE.fullmatch(body):
                i = j
                continue
        out.append(lines[i])
        i += 1
    return "\n".join(out)


def clean_answer(text, mode=None, original=None):
    """Remove wrappers the model adds around the answer.

    original = the selected text: an intro line or a code fence that is
    also in the original is real content and is kept.
    """
    text = text.replace("\r\n", "\n").strip()
    original = (original or "").replace("\r\n", "\n").strip()

    # Possible reasoning
    text = re.sub(r"(?s)^<think>.*?</think>\s*", "", text)

    # Everything wrapped in one ```...``` block (not two blocks, not a fenced original)
    fence = re.match(r"(?s)^```[a-zA-Z]*\n(.*)\n```$", text)
    if fence and "```" not in fence.group(1) and not original.startswith("```"):
        text = fence.group(1).strip()

    # Prompt tags repeated by the model
    text = re.sub(r"^</?(testo|versione_attuale|testo_originale)>\s*", "", text)
    text = re.sub(r"\s*</?(testo|versione_attuale|testo_originale)>$", "", text)

    if mode == "rewrite":
        # "Ecco il testo corretto:" at the start (unless the user wrote it)
        intro = INTRO_RE.match(text)
        if intro and intro.group(0).strip() not in original:
            text = text[intro.end():]
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
        text = _drop_empty_sections(text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()

    return text.strip()


# =========================================================
# PgUp / PgDn / End ACTIONS
# =========================================================

def max_input_chars(mode):
    """Longest selection that still leaves room in the context for the prompt and the answer.

    Rough estimate: about 3 characters per token, about 2000 tokens for the
    instructions (the web sources budget is kept apart by websearch.py).
    """
    num_predict = prompts.OPTIONS.get(mode, prompts.OPTIONS["explain"]).get("num_predict", 4096)
    return max(2000, (prompts.NUM_CTX - num_predict - 2000) * 3)


def run_action(mode, argv):
    """Usage: <script> <input.txt> <output.txt>

    Exit codes: 0 = done, 1 = error, 3 = text too long / answer cut off.
    On failure work/error.txt explains why (line 1 is shown to the user).
    """
    try:
        return _run_action(mode, argv)
    except Exception as e:
        message, detail = describe_error(e)
        write_error(message, detail + "\n" + traceback.format_exc())
        return 1


def _run_action(mode, argv):
    import sys
    import time

    t0 = time.time()
    clear_error()
    input_file = Path(argv[1])
    output_file = Path(argv[2])

    testo = input_file.read_text(encoding="utf-8-sig")

    if not testo.strip():
        print("Empty text.", file=sys.stderr)
        write_error("Nothing selected: select some text first.", "empty input")
        return 1

    limit = max_input_chars(mode)
    if len(testo) > limit:
        write_error(f"The selected text is too long ({len(testo):,} characters, about {limit:,} at most): "
                    "select a shorter part.", f"len={len(testo)} limit={limit}")
        return 3

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
        risposta, done_reason = chat_ex(messages, mode)
    except Exception as e:
        print(f"Ollama error: {e}", file=sys.stderr)
        write_error(*describe_error(e))
        return 1

    if done_reason == "length":
        write_error("The answer was cut off (too long for the model): select a shorter part.",
                    "done_reason=length")
        return 3

    risposta = clean_answer(risposta, mode, original=testo)
    if not risposta:
        write_error("Qwen returned an empty answer: try again.", "empty answer")
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
