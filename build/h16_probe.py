"""H16 smoke probe: run with the payload's own interpreter against a disposable install copy.

    <copy>\\python\\python.exe -B h16_probe.py --root <copy> --variant <name> --report <json> --poison <dir>

Checks, all recorded in the JSON report:
  env       sys.path / isolation flags; PYTHONPATH (pointed at --poison) and user site ignored (C28)
  bare      `import <root module>` from a neutral cwd, i.e. without the scripts' own sys.path insert
  entries   every entry point main.ahk runs, loaded the way main.ahk runs it (as a script in its
            own folder, cwd = install root, run_name != "__main__" so nothing executes)
  searx     the SearXNG import done by searxng/avvia_searxng.py, then which app modules it pulled in
  static    import names used by searx + searxng/lib that collide with install-root names
Never starts a server, never talks to Ollama. Exit code 1 if a required check fails.
"""

import argparse
import ast
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ENTRIES = [
    "actions/rewrite.py",
    "actions/summarize.py",
    "actions/explain.py",
    "actions/obsidian_todo.py",
    "actions/unload.py",
    "viewer.py",
    "settings.py",
    "config_edit.py",
    "searxng/avvia_searxng.py",
]

# Mirrors searxng/avvia_searxng.py main() up to the searx import (paths, pwd stub, loop, env).
SEARX_IMPORT = r"""
import asyncio, json, os, sys, types, warnings
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(here, "app"))
sys.path.insert(0, os.path.join(here, "lib"))
try:
    import pwd  # noqa: F401
except ImportError:
    stub = types.ModuleType("pwd")
    def getpwuid(uid):
        raise KeyError(uid)
    stub.getpwuid = getpwuid
    sys.modules["pwd"] = stub
with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
os.environ["SEARXNG_SETTINGS_PATH"] = os.path.join(here, "settings.yml")
os.environ["SEARXNG_DISABLE_ETC_SETTINGS"] = "1"
os.environ["SEARXNG_SECRET"] = "smoke"
from searx import webapp  # noqa: F401,E402
import curl_cffi  # noqa: F401,E402
mods = {}
for name, mod in list(sys.modules.items()):
    f = getattr(mod, "__file__", None)
    if f:
        mods[name] = os.path.abspath(f)
print(json.dumps({"ok": True, "sys_path": sys.path, "modules": mods}))
"""

ENTRY_WRAPPER = r"""
import json, os, runpy, sys
target = {target!r}
first = list(sys.path)
runpy.run_path(target, run_name="aih_smoke")
mods = {{}}
for name in {names!r}:
    mod = sys.modules.get(name)
    if mod is not None and getattr(mod, "__file__", None):
        mods[name] = os.path.abspath(mod.__file__)
extra = {{}}
if "websearch" in sys.modules:
    extra["curl_cffi_reuse"] = sys.modules["websearch"]._cffi() is not None
print(json.dumps({{"ok": True, "sys_path_at_start": first, "modules": mods, "extra": extra}}))
"""


def norm(p):
    return os.path.normcase(os.path.abspath(p))


def run(cmd, cwd, timeout=120):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    out = r.stdout.strip().splitlines()
    data = None
    if r.returncode == 0 and out:
        try:
            data = json.loads(out[-1])
        except ValueError:
            data = None
    return r.returncode, data, r.stderr.strip()[-1500:]


def root_names(root):
    names = set()
    for p in root.iterdir():
        if p.is_file() and p.suffix == ".py":
            names.add(p.stem)
        elif p.is_dir() and p.name.isidentifier():
            names.add(p.name)
    return names


def imported_top_names(tree_root):
    found = {}
    for path in tree_root.rglob("*.py"):
        try:
            tree = ast.parse(path.read_bytes(), filename=str(path))
        except (SyntaxError, ValueError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                tops = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                tops = [node.module.split(".")[0]]
            else:
                continue
            for t in tops:
                found.setdefault(t, str(path.relative_to(tree_root)))
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--variant", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--poison", required=True)
    args = ap.parse_args()

    root = Path(args.root).resolve()
    py = str(root / "python" / "python.exe")
    report = {"variant": args.variant, "failures": []}
    fail = report["failures"].append
    app_modules = sorted(p.stem for p in root.glob("*.py"))

    # env ------------------------------------------------------------------
    user_site = os.path.join(os.environ.get("APPDATA", ""), "Python")
    report["env"] = {
        "executable": sys.executable,
        "version": sys.version,
        "sys_path": sys.path,
        "flags": {k: getattr(sys.flags, k) for k in ("isolated", "ignore_environment", "no_user_site", "safe_path")},
        "site_imported": "site" in sys.modules,
        "pythonpath_env": os.environ.get("PYTHONPATH"),
    }
    paths = [norm(p) for p in sys.path]
    if norm(args.poison) in paths:
        fail("env: PYTHONPATH entry is on sys.path")
    if any(p.startswith(norm(user_site)) for p in paths):
        fail("env: user site-packages on sys.path")
    if any("site-packages" in p for p in paths):
        fail("env: a site-packages folder is on sys.path")

    # bare imports -----------------------------------------------------------
    neutral = tempfile.mkdtemp(prefix="aih-neutral-")
    report["bare"] = {}
    for m in app_modules:
        rc, _, err = run([py, "-B", "-c", f"import {m}"], cwd=neutral)
        report["bare"][m] = "ok" if rc == 0 else ("FAIL: " + (err.splitlines()[-1] if err else f"rc={rc}"))
    os.rmdir(neutral)

    # entries ----------------------------------------------------------------
    report["entries"] = {}
    for rel in ENTRIES:
        target = root / rel
        wrapper = target.parent / f"_aih_smoke_{target.stem}.py"
        wrapper.write_text(ENTRY_WRAPPER.format(target=str(target), names=app_modules), encoding="utf-8")
        try:
            rc, data, err = run([py, "-B", str(wrapper)], cwd=str(root))
        finally:
            wrapper.unlink()
        res = {"rc": rc}
        if data:
            res.update(data)
            wrong = {n: f for n, f in data["modules"].items() if norm(f) != norm(root / f"{n}.py")}
            if wrong:
                res["shadowed"] = wrong
                fail(f"entries: {rel} resolved app modules outside the install root: {wrong}")
            if data["extra"].get("curl_cffi_reuse") is False:
                fail(f"entries: {rel} could not reuse curl_cffi from searxng/lib")
        else:
            res["stderr"] = err
            fail(f"entries: {rel} failed to load: {err.splitlines()[-1] if err else rc}")
        report["entries"][rel] = res

    # searx import -----------------------------------------------------------
    wrapper = root / "searxng" / "_aih_smoke_searx.py"
    wrapper.write_text(SEARX_IMPORT, encoding="utf-8")
    try:
        rc, data, err = run([py, "-B", str(wrapper)], cwd=str(root), timeout=300)
    finally:
        wrapper.unlink()
    sx = {"rc": rc}
    if data:
        allowed = [norm(root / "python"), norm(root / "searxng" / "app"), norm(root / "searxng" / "lib"),
                   norm(root / "searxng")]
        app_hits, outside = {}, {}
        for name, f in data["modules"].items():
            nf = norm(f)
            if os.path.dirname(nf) in (norm(root), norm(root / "actions")):
                app_hits[name] = f
            elif not any(nf.startswith(a + os.sep) for a in allowed):
                outside[name] = f
        sx.update({"sys_path": data["sys_path"], "module_count": len(data["modules"]),
                   "app_modules_imported": app_hits, "modules_from_unexpected_places": outside})
        if app_hits:
            fail(f"searx: SearXNG import pulled in app modules (shadowing): {app_hits}")
        if outside:
            fail(f"searx: modules loaded from outside the payload: {sorted(outside)[:10]}")
    else:
        sx["stderr"] = err
        fail(f"searx: import failed: {err.splitlines()[-1] if err else rc}")
    report["searx"] = sx

    # static collision scan ----------------------------------------------------
    names = root_names(root)
    sx_imports = imported_top_names(root / "searxng" / "app")
    lib_imports = imported_top_names(root / "searxng" / "lib")
    lib_provides = {p.stem if p.is_file() else p.name for p in (root / "searxng" / "lib").iterdir()
                    if (p.is_file() and p.suffix in (".py", ".pyd")) or (p.is_dir() and "." not in p.name)}
    lib_provides = {n.split(".")[0] for n in lib_provides}
    report["static"] = {
        "root_names": sorted(names),
        "imported_by_searx_and_lib": {n: (sx_imports.get(n) or lib_imports.get(n))
                                      for n in sorted(names & (set(sx_imports) | set(lib_imports)))},
        "also_provided_by_searxng_lib": sorted(names & lib_provides),
        "also_stdlib_names": sorted(names & set(sys.stdlib_module_names)),
    }
    st = report["static"]
    for key in ("also_provided_by_searxng_lib", "also_stdlib_names"):
        if st[key]:
            fail(f"static: {key}: {st[key]}")
    for n, where in st["imported_by_searx_and_lib"].items():
        if n not in lib_provides and n != "searx":
            fail(f"static: '{n}' is imported by {where} and would resolve to the install root")

    Path(args.report).write_text(json.dumps(report, indent=2), encoding="utf-8")
    for f in report["failures"]:
        print("FAIL", f)
    return 1 if report["failures"] else 0


if __name__ == "__main__":
    sys.exit(main())
