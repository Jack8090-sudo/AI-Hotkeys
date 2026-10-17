"""Repository hygiene checks on the files git tracks (CI secret-scan job, step S2).

    python scripts/ci/check_hygiene.py            # both checks
    python scripts/ci/check_hygiene.py tracked    # forbidden tracked files only
    python scripts/ci/check_hygiene.py paths      # personal C:\\Users\\<name>\\ paths only

tracked: fails if git tracks config.ini (personal paths), anything under work/ (the user's selected
         text), any *.exe or *.rar (binaries are downloaded and hash-pinned, never committed).
paths:   fails if a tracked text file contains a personal Windows profile path such as
         C:\\Users\\jack\\..., or the same path with / or \\\\ separators. Placeholders are allowed:
         %USERPROFILE%, $env:USERPROFILE, <name>, <user>, {user}, USERNAME, Public, Default, ...

Exit codes: 0 clean, 1 findings, 2 git failed.
"""
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]

FORBIDDEN_NAMES = {"config.ini"}
FORBIDDEN_DIRS = {"work"}
FORBIDDEN_SUFFIXES = {".exe", ".rar"}

# C:\Users\<segment>\  with \, / or \\ separators (also file:///C:/Users/...). Case-insensitive.
USER_PATH_RE = re.compile(r"(?i)\b[a-z]:(?:\\\\|\\|/)users(?:\\\\|\\|/)([^\\/\s\"'`<>|:*?%$]+)")
# Segment values that are not a real person's profile.
ALLOWED_SEGMENTS = {
    "public", "default", "default user", "all users", "defaultaccount",
    "user", "username", "name", "you", "yourname", "your-name", "your_name", "me", "someone",
    "runneradmin", "runner", "...", "…", "x", "xxx", "example",
}
PLACEHOLDER_RE = re.compile(r"^(?:\{[^}]*\}|\[[^\]]*\]|<[^>]*>|\.\.\.|…)$")
# Files where a matching string is expected (this checker's own docs and patterns).
SELF = {"scripts/ci/check_hygiene.py"}


def git_ls_files():
    try:
        out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"], capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError) as e:
        print(f"error: git ls-files failed: {e}", file=sys.stderr)
        sys.exit(2)
    return [p for p in out.stdout.decode("utf-8", "surrogateescape").split("\0") if p]


def check_tracked(files):
    bad = []
    for f in files:
        p = PurePosixPath(f)
        if p.name.lower() in FORBIDDEN_NAMES:
            bad.append((f, "personal config file"))
        elif p.parts and p.parts[0].lower() in FORBIDDEN_DIRS:
            bad.append((f, "runtime work/ directory (user data)"))
        elif p.suffix.lower() in FORBIDDEN_SUFFIXES:
            bad.append((f, f"binary {p.suffix.lower()}"))
    for f, why in bad:
        print(f"::error file={f}::tracked file not allowed ({why}): {f}")
    return not bad


def allowed_segment(seg):
    s = seg.strip().lower()
    return s in ALLOWED_SEGMENTS or bool(PLACEHOLDER_RE.match(seg.strip()))


def scan_text(text):
    """Yield (line_no, match_text) for personal profile paths in text."""
    for n, line in enumerate(text.splitlines(), 1):
        for m in USER_PATH_RE.finditer(line):
            if not allowed_segment(m.group(1)):
                yield n, m.group(0)


def check_paths(files):
    found = 0
    for f in files:
        if f in SELF:
            continue
        path = ROOT / f
        try:
            data = path.read_bytes()
        except OSError:
            continue  # deleted in the work tree, a submodule, ...
        if b"\0" in data[:8192]:
            continue  # binary (fonts, icons)
        text = data.decode("utf-8", "replace")
        for n, hit in scan_text(text):
            found += 1
            print(f"::error file={f},line={n}::personal Windows profile path: {hit}")
    return not found


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    which = set(argv) or {"tracked", "paths"}
    if not which <= {"tracked", "paths"}:
        print(__doc__, file=sys.stderr)
        return 2
    files = git_ls_files()
    ok = True
    if "tracked" in which:
        ok &= check_tracked(files)
    if "paths" in which:
        ok &= check_paths(files)
    print(f"{'ok' if ok else 'FAILED'}: checked {len(files)} tracked files ({', '.join(sorted(which))})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
