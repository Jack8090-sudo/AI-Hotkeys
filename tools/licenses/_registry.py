# AI-Hotkeys — shared helpers for the license tools (gen_notices.py, check_notices.py).
import json
import re
from fnmatch import fnmatchcase
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = Path(__file__).resolve().parent / "components.json"
BINARY_SUFFIXES = (".exe", ".dll", ".pyd", ".so")


def load_registry(path=REGISTRY):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def norm_name(name):
    """PEP 503 normalized distribution name ("Flask_Babel" -> "flask-babel")."""
    return re.sub(r"[-_.]+", "-", name).lower()


def split_dist_info(dirname):
    """"lxml-6.1.3.dist-info" -> ("lxml", "6.1.3"); None if it is not a dist-info name."""
    if not dirname.endswith(".dist-info"):
        return None
    stem = dirname[: -len(".dist-info")]
    if "-" not in stem:
        return None
    name, version = stem.rsplit("-", 1)
    return norm_name(name), version


def _match_parts(pat, parts):
    if not pat:
        return not parts
    if pat[0] == "**":
        return any(_match_parts(pat[1:], parts[i:]) for i in range(len(parts) + 1))
    return bool(parts) and fnmatchcase(parts[0], pat[0]) and _match_parts(pat[1:], parts[1:])


def path_matches(pattern, path):
    """Glob match on "/"-separated paths: "*" stays inside a segment, "**" spans segments."""
    return _match_parts(pattern.split("/"), path.split("/"))


def normalize_text(data):
    """Bytes with CRLF folded to LF, so git's eol conversion never counts as a change."""
    return data.replace(b"\r\n", b"\n")
