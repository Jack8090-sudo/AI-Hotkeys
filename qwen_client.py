"""
AI-Hotkeys — shared Ollama connection used by all actions.

The module name (and the [qwen] config section) are historical: kept for compatibility (I11).
"""

import configparser
import http.client
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

# Error shown by main.ahk when an action fails (line 1 = message for the user).
# Selection jobs started with --run-dir write it inside their run directory
# instead (S9); work/error.txt stays for the health check, unload and the old
# argument form.
ERROR_FILE = WORK_DIR / "error.txt"
# Per-run directories: work/runs/<run id>/ (S9, contract K1 location)
RUNS_DIR = WORK_DIR / "runs"
RUN_ID_RE = re.compile(r"\d{14}-[0-9a-f]{16}")
# A run directory older than this is left over from a crash: swept away
STALE_RUN_SECONDS = 3600
# Problems found in config.ini (one per line), shown by main.ahk after a reload
CONFIG_WARNING_FILE = WORK_DIR / "config_warning.txt"

# Oldest Ollama known to accept "think": false (sent with every request)
MIN_OLLAMA_VERSION = (0, 9, 0)


# =========================================================
# CONFIGURATION (config.ini)
# =========================================================

DEFAULTS = {
    "model": "gemma4:e4b-it-qat",
    "ollama_url": "http://localhost:11434",
    "keep_alive": "30m",
    "todo_file": r"%USERPROFILE%\Documents\To-Do List.md",
}

CONFIG_WARNINGS = []

# Keys holding a file path: surrounding quotes ("C:\...") are removed
PATH_KEYS = {"todo_file"}


def _unquote(value):
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1].strip()
    return value


def _config_error_text(e):
    """Short description of a configparser error, with the line number and without the path."""
    if isinstance(e, configparser.MissingSectionHeaderError):
        return f"line {e.lineno}: a setting appears before any [section] header"
    if isinstance(e, configparser.DuplicateOptionError):
        return f"line {e.lineno}: '{e.option}' appears twice in [{e.section}]"
    if isinstance(e, configparser.DuplicateSectionError):
        return f"line {e.lineno}: section [{e.section}] appears twice"
    if isinstance(e, configparser.ParsingError) and e.errors:
        lineno, line = e.errors[0]
        return f"line {lineno}: {line.strip()[:80]!s} (expected  key = value)"
    return str(e).strip().splitlines()[0][:160]


CLOUD_MODEL_MESSAGE = ("Cloud models are not allowed: AI-Hotkeys keeps your text on this PC. "
                       "Choose a local model in Settings.")


def is_cloud_model(name):
    """True for an Ollama cloud model ("gpt-oss:120b-cloud", "glm-4.6:cloud"): it runs on
    Ollama's servers, so the selected text would leave this PC."""
    name = str(name or "").strip().lower()
    return name.endswith(":cloud") or name.endswith("-cloud")


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
        CONFIG_WARNINGS.append(f"config.ini has an error, using the default settings: {_config_error_text(e)}")
        return cfg

    for section in parser.sections():
        for key, value in parser.items(section):
            value = value.strip()
            if key in PATH_KEYS:
                value = _unquote(value)
            if value:
                cfg[key] = value
    if is_cloud_model(cfg["model"]):
        CONFIG_WARNINGS.append(f"config.ini names a cloud model ({cfg['model']}): {CLOUD_MODEL_MESSAGE} "
                               f"Using {DEFAULTS['model']} for now.")
        cfg["model"] = DEFAULTS["model"]
    return cfg


def _write_atomic(path, text, create_dir=True):
    """Write via a unique temp file + replace; if the replace is refused (file held open), write directly.

    create_dir=False: the folder must already exist (a run directory that main.ahk
    deleted is never recreated, so a late writer leaves nothing behind).
    """
    if create_dir:
        path.parent.mkdir(parents=True, exist_ok=True)
    elif not path.parent.is_dir():
        raise FileNotFoundError(f"run directory is gone: {path.parent}")
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        path.write_text(text, encoding="utf-8")
    finally:
        if tmp.exists():
            tmp.unlink()


def report_config_warnings():
    """Write work/config_warning.txt when config.ini or prompts_user.py has a problem (contract K6).

    Called by the entry points (actions), never at import: main.ahk deletes the
    file after showing it, so an import elsewhere cannot hide a warning.
    """
    lines = CONFIG_WARNINGS + ([PROMPTS_WARNING] if PROMPTS_WARNING else [])
    if lines:
        try:
            _write_atomic(CONFIG_WARNING_FILE, "\n".join(lines) + "\n")
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


def todo_file():
    return Path(os.path.expandvars(CONFIG["todo_file"]))


# =========================================================
# ERRORS (work/error.txt, read by main.ahk)
# =========================================================

class TruncatedAnswer(RuntimeError):
    """Ollama stopped because the answer reached num_predict."""


class StreamIncomplete(RuntimeError):
    """A streamed answer ended without Ollama's final "done" chunk."""


class CloudModelRefused(RuntimeError):
    """The model is an Ollama cloud model: the text would leave this PC."""


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
        if exc.code == 404 and ("model" in err.lower() or "not found" in err.lower()):
            return f"Model '{MODEL}' not found: run  ollama pull {MODEL}", detail
        if exc.code == 404:
            return f"Ollama answered 404: check  ollama_url  in the settings ({OLLAMA_URL}).", detail
        return f"Ollama returned an error (HTTP {exc.code}): {err[:120]}".rstrip(": "), detail
    reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
    if isinstance(reason, TimeoutError):
        return "Ollama did not answer in time. Try again, or select less text.", detail
    if isinstance(reason, (ConnectionResetError, ConnectionAbortedError)):
        return "Ollama stopped while answering: try again.", detail
    if isinstance(exc, (urllib.error.URLError, ConnectionError)):
        return "Ollama is not running: start Ollama, then try again.", detail
    if isinstance(exc, (TruncatedAnswer, StreamIncomplete, CloudModelRefused)):
        return str(exc), detail
    if isinstance(exc, RuntimeError) and "not found" in str(exc).lower():
        return f"Model '{MODEL}' not found: run  ollama pull {MODEL}", detail
    return f"Something went wrong: {str(exc)[:150]}", detail


# The run directory of the job in progress (--run-dir), None for the old form
_RUN_DIR = None


def _error_file():
    return _RUN_DIR / "error.txt" if _RUN_DIR else ERROR_FILE


def write_error(message, detail=""):
    """Write error.txt (K1): line 1 is shown to the user by main.ahk.

    In a run started with --run-dir it goes to <run dir>/error.txt, else work/error.txt.
    """
    line1 = re.sub(r"[\r\n\t]+", " ", message).strip()[:200]     # keeps the "run  ollama pull" spacing
    text = line1 + "\n" + (detail.strip() + "\n" if detail else "")
    try:
        _write_atomic(_error_file(), text, create_dir=_RUN_DIR is None)
    except OSError:
        pass


def clear_error():
    try:
        _error_file().unlink()
    except OSError:
        pass


# =========================================================
# RUN DIRECTORIES (work/runs/<id>/, S9)
# =========================================================

def is_run_dir(path):
    """True for a folder directly inside work/runs whose name is a run id."""
    path = Path(path)
    return bool(RUN_ID_RE.fullmatch(path.name)) and path.parent.resolve() == RUNS_DIR.resolve()


def sweep_stale_runs(max_age=STALE_RUN_SECONDS, keep=None, now=None):
    """Delete run directories last modified more than max_age seconds ago.

    Only folders named like a run id are touched; keep (a path) is never deleted.
    Returns the names deleted. Best effort: a locked file leaves its folder for next time.
    """
    import shutil
    import time

    now = time.time() if now is None else now
    keep = Path(keep).resolve() if keep else None
    removed = []
    try:
        entries = list(RUNS_DIR.iterdir())
    except OSError:
        return removed
    for d in entries:
        try:
            if not (d.is_dir() and RUN_ID_RE.fullmatch(d.name)) or (keep and d.resolve() == keep):
                continue
            if now - d.stat().st_mtime < max_age:
                continue
        except OSError:
            continue
        shutil.rmtree(d, ignore_errors=True)
        if not d.exists():
            removed.append(d.name)
    return removed


def remove_run_dir(run_dir):
    """Delete a run directory and everything in it (best effort)."""
    import shutil

    shutil.rmtree(run_dir, ignore_errors=True)


def parse_action_args(argv):
    """(input file, output file, run dir or None) from an action's argv.

    New form (S9):  <script> --run-dir=<work\\runs\\id>
    Old form (K3):  <script> <input.txt> <output.txt>
    """
    for a in argv[1:]:
        if a.startswith("--run-dir="):
            run_dir = Path(a.split("=", 1)[1])
            return run_dir / "input.txt", run_dir / "output.txt", run_dir
    if len(argv) < 3:
        raise ValueError("usage: <script> --run-dir=<dir>   or   <script> <input.txt> <output.txt>")
    return Path(argv[1]), Path(argv[2]), None


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
    if is_cloud_model(MODEL):
        raise CloudModelRefused(CLOUD_MODEL_MESSAGE)
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


def _lines(response):
    """Lines of a streamed response; a connection cut mid-answer becomes StreamIncomplete."""
    try:
        yield from response
    except http.client.IncompleteRead as e:
        raise StreamIncomplete("The answer was interrupted before the end.") from e


def stream_pieces(response):
    """Text pieces of a streamed answer; StreamIncomplete if it stops before "done"."""
    done = False
    for raw in _lines(response):
        raw = raw.strip()
        if not raw:
            continue
        try:
            chunk = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise StreamIncomplete("The answer was interrupted before the end.") from e
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
    nums = [int(n) for n in re.findall(r"\d+", str(text))[:3]]
    return tuple(nums + [0] * (3 - len(nums)))


def health(timeout=3):
    """(ok, message): is Ollama running, recent enough, and is the model there?"""
    if is_cloud_model(MODEL):
        return False, CLOUD_MODEL_MESSAGE
    try:
        with _OPENER.open(OLLAMA_URL + "/api/version", timeout=timeout) as r:
            version = json.load(r).get("version", "")
        with _OPENER.open(OLLAMA_URL + "/api/tags", timeout=timeout) as r:
            models = json.load(r).get("models", [])
        names = [m.get("name", "") for m in models]
        remote = {m.get("name", "") for m in models if m.get("remote_host") or m.get("remote_model")}
    except Exception as e:
        return False, describe_error(e)[0]
    # "0.0.0" is reported by builds from source: no check possible
    if version and _version_tuple(version) != (0, 0, 0) and _version_tuple(version) < MIN_OLLAMA_VERSION:
        need = ".".join(map(str, MIN_OLLAMA_VERSION))
        return False, f"Ollama {version} is too old: update it to {need} or newer."
    wanted = MODEL if ":" in MODEL else MODEL + ":latest"
    if wanted not in names:
        return False, f"Model '{MODEL}' not found: run  ollama pull {MODEL}"
    if wanted in remote:
        return False, CLOUD_MODEL_MESSAGE
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
    """Remove headings whose whole body is "Nessuno." / "n/a" / "-".

    Linear time: one backward pass finds, for every line, where the next
    section starts; only bodies of at most two non-empty lines are examined.
    """
    lines = text.split("\n")
    n = len(lines)
    next_section = [n] * (n + 1)          # first index > i that starts a "#... " section
    for i in range(n - 1, -1, -1):
        next_section[i] = i + 1 if i + 1 < n and re.match(r"#{1,4} ", lines[i + 1]) else next_section[i + 1]
    nonempty = [0] * (n + 1)              # non-empty lines before index i
    for i, line in enumerate(lines):
        nonempty[i + 1] = nonempty[i] + (1 if line.strip() else 0)

    out, i = [], 0
    while i < n:
        if re.match(r"#{1,4}", lines[i]):
            j = min(next_section[i], n)
            # Any heading inside the range is itself non-empty, so few ranges get scanned
            if 1 <= nonempty[j] - nonempty[i + 1] <= 2:
                body = "\n".join(l for l in lines[i + 1:j] if l.strip())
                if _EMPTY_BODY_RE.fullmatch(body.strip()):
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

    # Everything wrapped in one ```...``` block. Not unwrapped when the original was
    # fenced, or when it is really two blocks ("```a\n...\n```\ntext\n```b\n...\n```").
    # Inner blocks are fine when balanced and the first inner fence opens one (```lua).
    fence = re.match(r"(?s)^```[a-zA-Z]*\n(.*)\n```$", text)
    if fence and not original.startswith("```"):
        inner_fences = re.findall(r"(?m)^```(\S*)", fence.group(1))
        if not inner_fences or (len(inner_fences) % 2 == 0 and inner_fences[0]):
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

# Characters the web sources can add to the End prompt (websearch.SOURCES_BUDGET)
SOURCES_RESERVE_CHARS = 10000


def max_input_chars(mode):
    """Longest selection that still fits: room in the context for the instructions and the
    answer, and for rewrite an answer (as long as the text) that fits in num_predict.

    Rough estimate: about 3 characters per token, about 2000 tokens of instructions.
    """
    num_predict = prompts.OPTIONS.get(mode, prompts.OPTIONS["explain"]).get("num_predict", 4096)
    limit = (prompts.NUM_CTX - num_predict - 2000) * 3
    if mode == "rewrite":
        limit = min(limit, int(num_predict * 3 * 0.8))
    if mode == "explain" and str(CONFIG.get("web_search", "auto")).strip().lower() not in ("0", "false", "no", "off"):
        limit -= SOURCES_RESERVE_CHARS
    return max(2000, limit)


# ---------------------------------------------------------
# First answer, shared by run_action (whole answer at once) and the results
# page in stream mode (viewer.py /api/first, STREAM1): only the network call
# differs, so the checks, the prompt, the web search and the cleanup cannot drift.
# ---------------------------------------------------------

class ActionStop(Exception):
    """The first answer cannot be given: message for the user (K1 line 1), detail, exit code."""

    def __init__(self, message, detail="", code=1):
        super().__init__(message)
        self.message = message
        self.detail = detail
        self.code = code


TRUNCATED_FIRST = "The answer was cut off (too long for the model): select a shorter part."


def check_input(mode, testo):
    """ActionStop for an empty selection or one longer than max_input_chars(mode)."""
    if not testo.strip():
        raise ActionStop("Nothing selected: select some text first.", "empty input", 1)
    limit = max_input_chars(mode)
    if len(testo) > limit:
        raise ActionStop(f"The selected text is too long ({len(testo):,} characters, about {limit:,} at most): "
                         "select a shorter part.", f"len={len(testo)} limit={limit}", 3)


def first_sources(mode, testo, sources_path=None, save=True):
    """End's web search before the first answer: (sources, meta).

    meta always has "mode"; for explain also "web", "query" and "fonti". With
    save, the sources are saved for the results page (sources_path: as
    websearch.save_sources); the page in stream mode keeps them in memory (save=False).
    A failed search is not an error: the answer is written without the web.
    """
    meta = {"mode": mode}
    if mode != "explain":
        return [], meta
    import sys

    import websearch
    try:
        fonti, query = websearch.gather_sources(testo)
    except Exception as e:
        print(f"Web search failed: {e}", file=sys.stderr)
        fonti, query = [], []
    if save:
        websearch.save_sources(fonti, query, path=sources_path)
    meta.update({"web": bool(fonti), "query": query if fonti else [], "fonti": len(fonti)})
    websearch.status("The AI is writing the explanation…" + (f" ({len(fonti)} sources)" if fonti else " (no web)"))
    return fonti, meta


def first_request_messages(mode, testo, fonti):
    """The chat messages of the first answer (prompts.first_messages with the sources block)."""
    fonti_txt = None
    if fonti:
        import websearch
        fonti_txt = websearch.sources_block(fonti)
    return prompts.first_messages(mode, testo, fonti_txt, lunghezza=CONFIG.get("lunghezza", "normale"))


def finish_first(mode, testo, risposta, fonti, done_reason=None):
    """The final first answer: cleaned, with the sources linked. ActionStop if cut off or empty."""
    if done_reason == "length":
        raise ActionStop(TRUNCATED_FIRST, "done_reason=length", 3)
    risposta = clean_answer(risposta, mode, original=testo)
    if not risposta:
        raise ActionStop("The AI returned an empty answer: try again.", "empty answer", 1)
    if fonti:
        import websearch
        risposta = websearch.add_sources(risposta, fonti)
    return risposta


def write_meta(meta, run_dir=None):
    """meta.json for the results page: in the run directory (never created), or work/ (old form)."""
    meta_file = run_dir / "meta.json" if run_dir else WORK_DIR / "meta.json"
    try:
        _write_atomic(meta_file, json.dumps(meta, ensure_ascii=False), create_dir=run_dir is None)
    except Exception:
        pass


def run_action(mode, argv):
    """Usage: <script> --run-dir=<work\\runs\\id>   (main.ahk, S9)
           <script> <input.txt> <output.txt>      (old form, still accepted)

    With --run-dir, input.txt is read from the run directory and output.txt,
    meta.json, sources.json, status.txt and error.txt are written there
    atomically; the directory is never created, so a job whose directory was
    deleted (cancelled, or main.ahk exited) leaves nothing behind.

    Exit codes: 0 = done, 1 = error, 3 = text too long / answer cut off.
    On failure error.txt explains why (line 1 is shown to the user).
    """
    global _RUN_DIR
    try:
        input_file, output_file, _RUN_DIR = parse_action_args(argv)
    except ValueError as e:
        write_error("Internal error: the action was started without its files.", str(e))
        return 1
    try:
        if _RUN_DIR is not None and not _RUN_DIR.is_dir():
            return 1            # cancelled before we started: nothing to report to
        return _run_action(mode, input_file, output_file)
    except Exception as e:
        message, detail = describe_error(e)
        write_error(message, detail + "\n" + traceback.format_exc())
        return 1
    finally:
        _RUN_DIR = None


def _run_action(mode, input_file, output_file):
    import sys
    import time

    t0 = time.time()
    run_dir = _RUN_DIR
    clear_error()
    report_config_warnings()
    if run_dir is not None:
        sweep_stale_runs(keep=run_dir)

    testo = input_file.read_text(encoding="utf-8-sig")

    try:
        check_input(mode, testo)
    except ActionStop as e:
        print(e.message, file=sys.stderr)
        write_error(e.message, e.detail)
        return e.code

    # End: first the web search with SearXNG (if enabled). The progress phases
    # go to this run's own status.txt (old form: work/status.txt)
    if mode == "explain":
        import websearch
        websearch.STATUS_FILE = (run_dir or websearch.WORK_DIR) / "status.txt"
    fonti, meta = first_sources(mode, testo, run_dir / "sources.json" if run_dir else None)

    try:
        messages = first_request_messages(mode, testo, fonti)
        risposta, done_reason = chat_ex(messages, mode)
    except Exception as e:
        print(f"Ollama error: {e}", file=sys.stderr)
        write_error(*describe_error(e))
        return 1

    try:
        risposta = finish_first(mode, testo, risposta, fonti, done_reason)
    except ActionStop as e:
        write_error(e.message, e.detail)
        return e.code

    # Details for the results page (time, web search done): written before
    # output.txt, so whoever sees output.txt also finds this run's meta.json
    meta["seconds"] = round(time.time() - t0, 1)
    write_meta(meta, run_dir)

    _write_atomic(output_file, risposta, create_dir=run_dir is None)
    return 0
