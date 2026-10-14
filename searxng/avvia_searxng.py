"""
AI-Hotkeys — avvia SearXNG in locale (motore di ricerca per End).

Lanciato in background da main.ahk all'avvio e, se serve, da explain.py.
Usa il Python portatile di AI-Hotkeys: niente Docker, niente WSL.

    searxng\\app\\searx\\   codice di SearXNG
    searxng\\lib\\          librerie necessarie
    searxng\\settings.yml   impostazioni
    work\\searxng.log       registro (si azzera a ogni avvio)
    work\\searxng.pid       processo in esecuzione (per chiuderlo)
"""

import configparser
import os
import secrets
import socket
import sys
import types
import warnings
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
WORK = BASE / "work"
LOG_FILE = WORK / "searxng.log"
PID_FILE = WORK / "searxng.pid"

DEFAULT_URL = "http://127.0.0.1:8888"


def searxng_url():
    parser = configparser.RawConfigParser()
    try:
        parser.read(BASE / "config.ini", encoding="utf-8-sig")
        url = parser.get("searxng", "searxng_url", fallback="").strip()
    except Exception:
        url = ""
    return url or DEFAULT_URL


def port_in_use(host, port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def main():
    WORK.mkdir(exist_ok=True)

    url = urlparse(searxng_url())
    host = "127.0.0.1"
    port = url.port or 8888

    # Già in esecuzione (es. dopo "Ricarica"): non serve un secondo processo.
    if port_in_use(host, port):
        return 0

    # pythonw non ha console: tutto quello che SearXNG scrive va nel registro.
    log = open(LOG_FILE, "w", encoding="utf-8", buffering=1)
    sys.stdout = log
    sys.stderr = log

    if not (HERE / "app" / "searx").is_dir():
        print("ERRORE: manca la cartella searxng\\app\\searx", flush=True)
        return 2

    sys.path.insert(0, str(HERE / "app"))
    sys.path.insert(0, str(HERE / "lib"))

    # --- Adattamenti per Windows -------------------------------------
    # SearXNG è pensato per Linux: importa il modulo "pwd" (solo Unix)
    # anche quando non usa Valkey. Un modulo vuoto basta.
    try:
        import pwd  # noqa: F401
    except ImportError:
        stub = types.ModuleType("pwd")

        def getpwuid(uid):
            raise KeyError(uid)

        stub.getpwuid = getpwuid
        sys.modules["pwd"] = stub

    # curl_cffi (le richieste ai motori) vuole il ciclo asyncio "selector";
    # su Windows quello predefinito è "proactor".
    if sys.platform == "win32":
        import asyncio
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    # -----------------------------------------------------------------

    os.environ["SEARXNG_SETTINGS_PATH"] = str(HERE / "settings.yml")
    os.environ["SEARXNG_DISABLE_ETC_SETTINGS"] = "1"
    os.environ["SEARXNG_BIND_ADDRESS"] = host
    os.environ["SEARXNG_PORT"] = str(port)
    # Chiave nuova a ogni avvio: serve solo a firmare i cookie delle preferenze.
    os.environ.setdefault("SEARXNG_SECRET", secrets.token_hex(32))

    PID_FILE.write_text(str(os.getpid()), encoding="ascii")
    print(f"SearXNG su http://{host}:{port}  (pid {os.getpid()})", flush=True)

    try:
        from searx import webapp  # importandolo, SearXNG si inizializza
        from werkzeug.serving import make_server

        server = make_server(host, port, webapp.app, threaded=True)
        print("Pronto.", flush=True)
        server.serve_forever()
    except Exception:
        import traceback
        traceback.print_exc()
        return 1
    finally:
        try:
            if PID_FILE.read_text(encoding="ascii").strip() == str(os.getpid()):
                PID_FILE.unlink()
        except Exception:
            pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
