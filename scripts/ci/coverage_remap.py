"""Map coverage data measured in AppTree temp copies back onto the repo files (CI, step S2).

tests/support.py copies the app into %TEMP%/aihk-test-<random>/ and imports it from there, so the
raw data names files like C:/.../Temp/aihk-test-x1y2/qwen_client.py. This rewrites the data file
(COVERAGE_FILE, default .coverage) so every such file becomes <repo>/qwen_client.py, merging the
arcs of all copies. Copies whose repo counterpart does not exist are dropped (with a note).

    python scripts/ci/coverage_remap.py [--data-file PATH]

Exit codes: 0 ok, 1 no data / nothing measured.
"""
import argparse
import os
import re
import sys
from pathlib import Path

from coverage import CoverageData

ROOT = Path(__file__).resolve().parents[2]
COPY_RE = re.compile(r"[\\/]aihk-test-[^\\/]+[\\/](.+)$")


def remap(path):
    m = COPY_RE.search(path)
    if not m:
        return path
    return str(ROOT / Path(m.group(1)))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data-file", default=os.environ.get("COVERAGE_FILE", ".coverage"))
    args = ap.parse_args(argv)

    src = CoverageData(basename=args.data_file)
    src.read()
    files = sorted(src.measured_files())
    if not files:
        print(f"error: no coverage data in {args.data_file}", file=sys.stderr)
        return 1
    if not src.has_arcs():
        print("error: data has no arcs; run coverage with branch = true", file=sys.stderr)
        return 1

    merged = {}
    dropped = set()
    for f in files:
        target = remap(f)
        if not Path(target).is_file():
            dropped.add(target)
            continue
        merged.setdefault(target, set()).update(src.arcs(f) or ())

    os.remove(args.data_file)
    dst = CoverageData(basename=args.data_file)
    dst.add_arcs({k: sorted(v) for k, v in merged.items()})
    dst.write()
    for d in sorted(dropped):
        print(f"note: no repo file for {d}; dropped")
    print(f"remapped {len(files)} measured files onto {len(merged)} repo files")
    return 0 if merged else 1


if __name__ == "__main__":
    sys.exit(main())
