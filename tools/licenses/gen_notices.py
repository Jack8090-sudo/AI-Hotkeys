# AI-Hotkeys — build the Python-package notices from *.dist-info metadata.
#
# Reads every <lib>/*.dist-info (the vendored SearXNG dependencies) and:
#   - copies each package's license files to licenses/python-packages/<name>-<version>/,
#     including license files that live inside the package itself (listed in RECORD);
#   - writes licenses/python-packages/packages.json (used by check_notices.py), including each
#     package's binaries from RECORD, so an unlisted .dll/.pyd fails the manifest check;
#   - rewrites the generated package table in THIRD_PARTY_NOTICES.md.
#
#   python tools/licenses/gen_notices.py --lib C:\AI-Hotkeys\searxng\lib
#   python tools/licenses/gen_notices.py --lib <payload>\searxng\lib --check   (no writes; exit 1 if stale)
#
# Exit codes: 0 ok, 1 stale (--check) or a package with missing/unclear license data, 2 usage error.
import argparse
import csv
import email.parser
import io
import json
import re
import shutil
import sys
from pathlib import Path, PurePosixPath

sys.dont_write_bytecode = True  # --check must not even create __pycache__
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _registry import (  # noqa: E402
    BINARY_SUFFIXES, ROOT, load_registry, norm_name, normalize_text, path_matches, split_dist_info,
)

NOTICES_MD = ROOT / "THIRD_PARTY_NOTICES.md"
OUT_DIR = ROOT / "licenses" / "python-packages"
BEGIN = "<!-- BEGIN GENERATED: python-packages (tools/licenses/gen_notices.py) -->"
END = "<!-- END GENERATED: python-packages -->"

SPDX_TOKEN_RE = re.compile(r"\(|\)|AND|OR|WITH|[A-Za-z0-9.+-]+")
LICENSE_NAME_RE = re.compile(r"^(?:LICEN[CS]E|COPYING|NOTICE|AUTHORS)|LICEN[CS]E", re.IGNORECASE)
URL_KEYS = ("source", "source code", "repository", "homepage", "home")
# Ids accepted from the free-text "License" field; anything else needs a reviewed license_overrides entry.
KNOWN_SPDX = {
    "0BSD", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "CC0-1.0", "HPND", "ISC", "MIT", "MIT-0",
    "MPL-2.0", "PSF-2.0", "Python-2.0", "Unlicense", "Zlib",
}


def read_metadata(dist_info):
    text = (dist_info / "METADATA").read_text(encoding="utf-8", errors="replace")
    return email.parser.Parser().parsestr(text, headersonly=True)


def project_url(meta, name):
    urls = {}
    for entry in meta.get_all("Project-URL") or []:
        label, _, url = entry.partition(",")
        urls[label.strip().lower()] = url.strip()
    for key in URL_KEYS:
        if urls.get(key):
            return urls[key]
    home = (meta.get("Home-page") or "").strip()
    if home and home.upper() != "UNKNOWN":
        return home
    return f"https://pypi.org/project/{name}/"


def spdx_license(meta, name, overrides):
    expr = (meta.get("License-Expression") or "").strip()
    if expr:
        return expr
    if name in overrides:
        return overrides[name]
    lic = (meta.get("License") or "").strip()
    tokens = SPDX_TOKEN_RE.findall(lic)
    ids = [t for t in tokens if t not in ("(", ")", "AND", "OR", "WITH")]
    if lic and "".join(tokens) == lic.replace(" ", "") and ids and all(i in KNOWN_SPDX for i in ids):
        return lic
    return None


def record_paths(dist_info):
    record = dist_info / "RECORD"
    if not record.is_file():
        return None
    rows = csv.reader(io.StringIO(record.read_text(encoding="utf-8", errors="replace")))
    return [row[0].replace("\\", "/") for row in rows if row and row[0]]


def safe_rel(rel):
    """A License-File value usable under the notice folder, or None if it could escape it."""
    p = PurePosixPath(rel.replace("\\", "/"))
    if not rel or p.is_absolute() or ":" in rel or ".." in p.parts:
        return None
    return p.as_posix()


def dist_license_files(dist_info, meta, problems, label):
    """[(source file, path relative to the package's notice folder)] from the dist-info."""
    found = []
    declared = meta.get_all("License-File") or []
    for raw in declared:
        rel = safe_rel(raw)
        if rel is None:
            problems.append(f"{label}: unsafe License-File value {raw!r}")
            continue
        for cand in (dist_info / "licenses" / rel, dist_info / rel):
            if cand.is_file():
                found.append((cand, rel))
                break
        else:
            problems.append(f"{label}: declared License-File {rel!r} not found in {dist_info.name}")
    if not declared:
        for cand in sorted(dist_info.iterdir()):
            if cand.is_file() and LICENSE_NAME_RE.search(cand.name):
                found.append((cand, cand.name))
    return found


def embedded_license_files(lib, dist_info, paths):
    """License files shipped inside the package (e.g. a vendored sub-library), from RECORD."""
    found = []
    for rel in paths:
        if rel.startswith("..") or rel.split("/")[0] == dist_info.name or safe_rel(rel) is None:
            continue
        src = lib / rel
        if LICENSE_NAME_RE.search(rel.rsplit("/", 1)[-1]) and src.is_file():
            found.append((src, "embedded/" + rel))
    return found


def collect(lib, registry):
    """Return (packages, files, problems); files maps repo-relative path -> bytes."""
    py = registry["python_packages"]
    lib_root = py["lib_root"].rstrip("/")
    overrides = py.get("license_overrides", {})
    extras = {k: v for k, v in py.get("extra_notices", {}).items() if isinstance(v, dict)}
    component_binaries = [p for c in registry["components"] for p in c.get("binaries", [])]
    packages, files, problems = [], {}, []
    for dist_info in sorted(lib.glob("*.dist-info"), key=lambda p: p.name.lower()):
        guess = split_dist_info(dist_info.name) or (dist_info.name, "?")
        try:
            meta = read_metadata(dist_info)
        except OSError as e:
            problems.append(f"{dist_info.name}: cannot read METADATA ({e})")
            continue
        if not meta["Name"] or not meta["Version"]:
            problems.append(f"{dist_info.name}: METADATA has no Name/Version; using the folder name")
        name = norm_name(meta["Name"] or guess[0])
        version = meta["Version"] or guess[1]
        label = f"{name} {version}"
        folder = f"{name}-{version}"
        paths = record_paths(dist_info)
        if paths is None:
            problems.append(f"{label}: {dist_info.name} has no RECORD, so its files cannot be attributed")
            paths = []
        sources = dist_license_files(dist_info, meta, problems, label) + embedded_license_files(lib, dist_info, paths)
        notices = []
        for src, rel in sources:
            dest = f"licenses/python-packages/{folder}/{rel}"
            files[dest] = src.read_bytes()
            notices.append(dest)
        license_id = spdx_license(meta, name, overrides)
        if not notices:
            problems.append(f"{label}: no license file found in {dist_info.name}")
        if not license_id:
            problems.append(f"{label}: no reliable SPDX license id (License: {meta.get('License')!r}); add one "
                            f"to license_overrides in tools/licenses/components.json after reading its license text")
        binaries = sorted(p for p in paths if not p.startswith("..") and p.lower().endswith(BINARY_SUFFIXES))
        foreign = [p for p in binaries if not p.lower().endswith(".pyd")
                   and not any(path_matches(pat, f"{lib_root}/{p}") for pat in component_binaries)]
        if foreign and name not in extras:
            problems.append(f"{label}: ships native libraries ({', '.join(foreign[:3])}) with no extra_notices "
                            f"entry or component in components.json; identify what they contain")
        entry = {
            "name": name,
            "version": version,
            "license": license_id or "UNKNOWN",
            "url": project_url(meta, name),
            "dist_info": dist_info.name,
            "top_level": sorted({p.split("/")[0] for p in paths if not p.startswith("..")} | {dist_info.name}),
            "binaries": binaries,
            "notices": notices,
        }
        extra = extras.get(name)
        if extra:
            entry["bundles"] = extra["bundles"]
            entry["bundles_verified_for"] = extra["version"]
            entry["extra_notices"] = extra["notices"]
            if extra["version"] != version:
                problems.append(f"{label}: bundled native libraries were verified for "
                                f"{extra['version']}; re-verify them and update extra_notices")
        packages.append(entry)
    index = {
        "_comment": "Generated by tools/licenses/gen_notices.py from searxng/lib/*.dist-info. Do not edit.",
        "packages": packages,
    }
    files["licenses/python-packages/packages.json"] = (json.dumps(index, indent=2) + "\n").encode("utf-8")
    return packages, files, problems


def render_table(packages):
    lines = [
        BEGIN,
        "",
        "| Package | Version | License (SPDX) | Notices in `licenses/python-packages/` |",
        "|---|---|---|---|",
    ]
    for p in packages:
        cell = f"`{p['name']}-{p['version']}/`"
        if p.get("bundles"):
            cell += f"; statically bundles {p['bundles']}"
        lines.append(f"| [{p['name']}]({p['url']}) | {p['version']} | {p['license']} | {cell} |")
    lines += ["", END]
    return "\n".join(lines)


def updated_notices_md(packages):
    text = NOTICES_MD.read_text(encoding="utf-8")
    start, end = text.find(BEGIN), text.find(END)
    if start < 0 or end < start:
        raise SystemExit(f"error: generated-table markers not found in {NOTICES_MD.name}")
    return text[:start] + render_table(packages) + text[end + len(END):]


def existing_files():
    if not OUT_DIR.is_dir():
        return {}
    return {p.relative_to(ROOT).as_posix(): p.read_bytes() for p in OUT_DIR.rglob("*") if p.is_file()}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build the Python-package notices from *.dist-info metadata.")
    ap.add_argument("--lib", type=Path, default=ROOT / "searxng" / "lib",
                    help="folder holding the *.dist-info directories (default: searxng/lib in this tree)")
    ap.add_argument("--check", action="store_true", help="compare with the files on disk; write nothing")
    args = ap.parse_args(argv)
    if not args.lib.is_dir() or not any(args.lib.glob("*.dist-info")):
        print(f"error: no *.dist-info under {args.lib} (pass --lib C:\\AI-Hotkeys\\searxng\\lib)", file=sys.stderr)
        return 2

    packages, files, problems = collect(args.lib, load_registry())
    md = updated_notices_md(packages)

    if args.check:
        have = {k: normalize_text(v) for k, v in existing_files().items()}
        want = {k: normalize_text(v) for k, v in files.items()}
        stale = sorted(k for k in want.keys() | have.keys() if have.get(k) != want.get(k))
        if normalize_text(NOTICES_MD.read_bytes()) != normalize_text(md.encode("utf-8")):
            stale.append(NOTICES_MD.name + " (package table)")
        for item in stale:
            print(f"stale: {item}")
        for item in problems:
            print(f"problem: {item}")
        if stale:
            print("Run tools/licenses/gen_notices.py (without --check) and commit the result.")
        return 1 if stale or problems else 0

    if OUT_DIR.is_dir():
        shutil.rmtree(OUT_DIR)
    for rel, data in files.items():
        dest = ROOT / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    NOTICES_MD.write_text(md, encoding="utf-8", newline="\n")
    print(f"{len(packages)} packages, {len(files) - 1} license files -> {OUT_DIR.relative_to(ROOT).as_posix()}/")
    for item in problems:
        print(f"problem: {item}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
