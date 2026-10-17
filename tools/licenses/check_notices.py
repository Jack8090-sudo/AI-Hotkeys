# AI-Hotkeys — fail the build if a redistributed file has no license notice.
#
#   python tools/licenses/check_notices.py build/out/manifest.txt
#   python tools/licenses/check_notices.py <manifest> --skip-shipped   (partial manifest: do not require
#                                                                        the notice files to be in it)
#
# The manifest (written by build/build.ps1, step S11) has one "path<TAB>sha256" line per payload file.
# Paths may use "\" or "/" and may start with "payload/" and "app/"; both prefixes are stripped, so
# paths are compared install-relative (app files land in the install folder itself).
#
# Every path must be covered by a component in tools/licenses/components.json or by a package in
# licenses/python-packages/packages.json (written by gen_notices.py). A binary (.exe/.dll/.pyd/.so) must
# also be listed: in its component's "binaries" patterns, or in its package's RECORD. The check also fails when:
#   - a *.dist-info in the manifest has no notice, or a different version than the notices describe;
#   - a package version pinned in "requires_dist" / "extra_notices" changed (bundled binaries must be
#     re-verified);
#   - a required notice file is missing or empty in the repo, or (unless --skip-shipped) not in the payload.
#
# Exit codes: 0 all covered, 1 problems found, 2 unreadable manifest or registry.
import argparse
import codecs
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _registry import (  # noqa: E402
    BINARY_SUFFIXES, ROOT, load_registry, norm_name, path_matches, split_dist_info,
)

SHA256_RE = re.compile(r"[0-9a-fA-F]{64}")
ALWAYS_SHIPPED = ("LICENSE", "THIRD_PARTY_NOTICES.md")
STRIP_PREFIXES = ("payload/", "app/")


class ManifestError(Exception):
    pass


def normalize_path(raw):
    path = raw.strip().replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    for prefix in STRIP_PREFIXES:
        if path.startswith(prefix):
            path = path[len(prefix):]
    parts = path.split("/")
    if not path or path.startswith("/") or ":" in parts[0] or ".." in parts or "" in parts:
        raise ValueError(f"not a relative payload path: {raw!r}")
    return path


def read_manifest(path):
    try:
        raw = Path(path).read_bytes()
        # Windows PowerShell 5.1 ">" / Out-File writes UTF-16 with a BOM; everything else should be UTF-8.
        utf16 = raw.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE))
        text = raw.decode("utf-16" if utf16 else "utf-8-sig")
    except OSError as e:
        raise ManifestError(f"cannot read manifest {path}: {e}") from e
    except UnicodeDecodeError as e:
        raise ManifestError(f"manifest {path} is neither UTF-8 nor UTF-16 with BOM: {e}") from e
    paths, errors = [], []
    for no, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) != 2 or not SHA256_RE.fullmatch(fields[1].strip()):
            errors.append(f"manifest line {no}: expected 'path<TAB>sha256', got {line[:120]!r}")
            continue
        try:
            paths.append(normalize_path(fields[0]))
        except ValueError as e:
            errors.append(f"manifest line {no}: {e}")
    if not paths and not errors:
        raise ManifestError(f"manifest {path} lists no files")
    return paths, errors


def load_inputs():
    """(registry, packages by name), validated enough that check() cannot hit a KeyError."""
    def require(obj, keys, where):
        missing = [k for k in keys if not isinstance(obj, dict) or k not in obj]
        if missing:
            raise ValueError(f"{where} lacks {', '.join(missing)}")

    try:
        registry = load_registry()
        require(registry, ("components", "python_packages"), "registry")
        for comp in registry["components"]:
            require(comp, ("id", "name", "paths", "notices"), f"component {comp!r:.60}")
        require(registry["python_packages"], ("lib_root", "index"), "python_packages")
        index = ROOT / registry["python_packages"]["index"]
    except (OSError, ValueError, TypeError) as e:
        raise ManifestError(f"invalid tools/licenses/components.json: {e}") from e
    try:
        data = json.loads(index.read_text(encoding="utf-8"))
        require(data, ("packages",), index.name)
        for p in data["packages"]:
            require(p, ("name", "version", "dist_info", "top_level", "binaries", "notices"), f"package {p!r:.60}")
        packages = {p["name"]: p for p in data["packages"]}
    except (OSError, ValueError, TypeError) as e:
        raise ManifestError(f"invalid {index.relative_to(ROOT).as_posix()}: {e} "
                            f"(run tools/licenses/gen_notices.py)") from e
    return registry, packages


def is_binary(path):
    return path.lower().endswith(BINARY_SUFFIXES)


def component_matches(comp, path):
    return (any(path_matches(p, path) for p in comp["paths"])
            and not any(path_matches(p, path) for p in comp.get("exclude", [])))


def package_top(rel):
    """Top-level RECORD entry owning a lib-relative path ("__pycache__/six.cpython-313.pyc" -> "six.py")."""
    parts = rel.split("/")
    if parts[0] == "__pycache__" and len(parts) == 2:
        return parts[1].split(".", 1)[0] + ".py"
    return parts[0]


def check(paths, registry, packages, skip_shipped):
    components = registry["components"]
    py = registry["python_packages"]
    lib_prefix = py["lib_root"].rstrip("/") + "/"
    extras = {k: v for k, v in py.get("extra_notices", {}).items() if isinstance(v, dict)}

    owners = defaultdict(list)  # top-level lib entry -> package names
    for pkg in packages.values():
        for top in pkg["top_level"]:
            owners[top].append(pkg["name"])

    errors = []
    uncovered = defaultdict(list)  # group -> paths
    required = {}  # notice file -> who needs it
    used_components, used_packages = set(), set()
    dists = {}  # normalized name -> version found in the manifest

    for path in paths:
        comp = next((c for c in components if component_matches(c, path)), None)
        if comp:
            if is_binary(path) and not any(path_matches(p, path) for p in comp.get("binaries", [])):
                errors.append(f"binary {path} is not in the 'binaries' list of {comp['name']} in "
                              f"components.json: identify its license before shipping it")
                continue
            used_components.add(comp["id"])
            for notice in comp["notices"]:
                required.setdefault(notice, comp["name"])
            continue
        if path.startswith(lib_prefix):
            rel = path[len(lib_prefix):]
            top = package_top(rel)
            info = split_dist_info(top)
            if info:
                dists[info[0]] = info[1]
            names = owners.get(top) or ([info[0]] if info and info[0] in packages else [])
            if names and is_binary(rel) and not any(
                    rel.lower() in {b.lower() for b in packages[n]["binaries"]} for n in names):
                errors.append(f"binary {path} is not in the RECORD of {', '.join(names)}: "
                              f"identify its license before shipping it")
                continue
            if names:
                for name in names:
                    used_packages.add(name)
                    pkg = packages[name]
                    for notice in pkg["notices"] + pkg.get("extra_notices", []):
                        required.setdefault(notice, f"{name} {pkg['version']}")
                continue
            group = lib_prefix + top
        else:
            group = "/".join(path.split("/")[:2])
        uncovered[group].append(path)

    for group, items in sorted(uncovered.items()):
        binaries = [p for p in items if is_binary(p)]
        kind = f"{len(binaries)} binaries, " if binaries else ""
        sample = ", ".join((binaries or items)[:3])
        errors.append(f"no notice covers {group} ({kind}{len(items)} files, e.g. {sample})")

    for name, version in sorted(dists.items()):
        pkg = packages.get(name)
        if pkg is None:
            errors.append(f"package {name} {version} has no notice: run tools/licenses/gen_notices.py "
                          f"on the payload's {py['lib_root']}")
        elif pkg["version"] != version:
            errors.append(f"package {name}: payload has {version}, notices describe {pkg['version']}: "
                          f"run tools/licenses/gen_notices.py")
        extra = extras.get(name)
        if extra and extra["version"] != version:
            errors.append(f"package {name} {version}: its bundled native libraries were verified for "
                          f"{extra['version']}; re-verify them and update extra_notices in components.json")
    for name in sorted(used_packages - set(dists)):
        errors.append(f"package {name}: files are in the payload but its {packages[name]['dist_info']} is not")

    for comp in components:
        if comp["id"] not in used_components:
            continue
        for dist, version in comp.get("requires_dist", {}).items():
            found = dists.get(norm_name(dist))
            if found != version:
                errors.append(f"{comp['name']}: notices were verified with {dist} {version}, payload has "
                              f"{found or 'no ' + dist}; re-verify and update components.json")

    shipped = set(paths)
    if not skip_shipped:
        for name in ALWAYS_SHIPPED:
            required.setdefault(name, "AI-Hotkeys")
    for notice, owner in sorted(required.items()):
        file = ROOT / notice
        if not file.is_file() or file.stat().st_size == 0:
            errors.append(f"notice file {notice} (for {owner}) is missing or empty in the repository")
        elif not skip_shipped and notice not in shipped:
            errors.append(f"notice file {notice} (for {owner}) is not in the payload")

    summary = (f"{len(paths)} files: {len(used_components)} components, {len(used_packages)} Python packages, "
               f"{len(required)} notice files")
    return errors, summary


def main(argv=None):
    ap = argparse.ArgumentParser(description="Fail if a redistributed file has no license notice.")
    ap.add_argument("manifest", help="path<TAB>sha256 manifest of the payload (build/out/manifest.txt)")
    ap.add_argument("--skip-shipped", action="store_true",
                    help="do not require the notice files themselves to be listed in the manifest")
    args = ap.parse_args(argv)
    try:
        registry, packages = load_inputs()
        paths, errors = read_manifest(args.manifest)
    except ManifestError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    problems, summary = check(paths, registry, packages, args.skip_shipped)
    errors += problems
    for e in errors:
        print(f"FAIL: {e}")
    print(("FAILED: " if errors else "OK: ") + summary + (f", {len(errors)} problems" if errors else ""))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
