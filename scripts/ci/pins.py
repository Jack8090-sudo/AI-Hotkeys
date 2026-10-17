"""Print one field of an upstream pin from build/pins.json (CI, step S2).

    python scripts/ci/pins.py autohotkey url
    python scripts/ci/pins.py autohotkey sha256

Validates the shape it hands out: url must be https, sha256 must be 64 hex chars.
Exit codes: 0 ok, 1 missing component/field or invalid value, 2 usage error.
"""
import json
import re
import sys
from pathlib import Path

PINS = Path(__file__).resolve().parents[2] / "build" / "pins.json"


def get(component, field, pins_path=PINS):
    pins = json.loads(Path(pins_path).read_text(encoding="utf-8"))
    entry = pins.get(component)
    if not isinstance(entry, dict):
        raise KeyError(f"no component {component!r} in {pins_path}")
    value = entry.get(field)
    if not isinstance(value, str) or not value:
        raise KeyError(f"no field {component}.{field} in {pins_path}")
    if field == "sha256" and not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError(f"{component}.sha256 is not 64 lowercase hex chars")
    if field == "url" and not value.startswith("https://"):
        raise ValueError(f"{component}.url is not https")
    if field == "file" and (not re.fullmatch(r"[A-Za-z0-9._-]+", value) or ".." in value):
        raise ValueError(f"{component}.file is not a plain file name")
    return value


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        print(get(*argv))
    except (KeyError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
