"""Both sides of each holdout traceback's boundary, and the day the breaking release came out (DT-QA-16).

  uv run python bench/model-alone/boundaries.py            write bench/model-alone/boundaries.json from PyPI
  uv run python bench/model-alone/boundaries.py --check    compare it with the probe's checks in the holdout sets

A case gives one side of its boundary, as a prefix: `last_version_with: "0.27"` (the 0.27 series is the last with the
name) or, for a name the installed release doesn't have yet, `first_version_with`. The model-alone baseline also
accepts the other side (README.md), so this reads each package's release list from PyPI and writes down, per case:

  removed      last_with   the newest final release the prefix matches
               breaking    the oldest final release after it: the first without the name
  not yet      breaking    the oldest final release the prefix matches: the first with the name
  added        last_without  the newest final release before it

and `released`, the day the breaking release was uploaded, which splits the cases at a model's training cutoff.
Final releases only (no pre-releases or development releases), yanked ones included: a yanked release was still
published. Nothing here comes from DepTime's answers or from a model's.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

from packaging.version import InvalidVersion, Version

HERE = Path(__file__).parent
HOLDOUT = HERE.parent / "holdout"
OUT = HERE / "boundaries.json"


def load_cases() -> list[dict]:
    """The six sets' tracebacks, in set order: the 191 cases of the README's first-run row."""
    cases = []
    for path in sorted(HOLDOUT.glob("*/tracebacks.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                cases.append({**json.loads(line), "set": path.parent.name})
    return cases


def final_releases(package: str) -> dict[Version, str]:
    """Each final release of `package` on PyPI that has files, with the day its first file was uploaded."""
    with urllib.request.urlopen(f"https://pypi.org/pypi/{package}/json", timeout=60) as response:
        doc = json.load(response)
    out = {}
    for text, files in doc["releases"].items():
        try:
            version = Version(text)
        except InvalidVersion:
            continue
        if files and not version.is_prerelease and not version.is_devrelease:
            out[version] = min(f["upload_time_iso_8601"] for f in files)[:10]
    return out


def matches(version: Version, prefix: str) -> bool:
    """The benchmark's prefix rule, by components: "1.5" matches 1.5.3 and not 1.50.0."""
    want = Version(prefix).release
    have = version.release + (0,) * len(want)
    return have[: len(want)] == want


def boundary(expected: dict, releases: dict[Version, str]) -> dict:
    ordered = sorted(releases)
    if "last_version_with" in expected:
        prefix = expected["last_version_with"]
        inside = [v for v in ordered if matches(v, prefix)]
        after = [v for v in ordered if v > (inside[-1] if inside else Version(prefix))]
        row = {
            "side": "last_version_with",
            "prefix": prefix,
            "last_with": str(inside[-1]) if inside else None,
            "breaking": str(after[0]) if after else None,
        }
    else:
        prefix = expected["first_version_with"]
        inside = [v for v in ordered if matches(v, prefix)]
        before = [v for v in ordered if v < (inside[0] if inside else Version(prefix))]
        row = {
            "side": "first_version_with",
            "prefix": prefix,
            "breaking": str(inside[0]) if inside else None,
            "last_without": str(before[-1]) if before else None,
        }
    row["released"] = releases.get(Version(row["breaking"])) if row["breaking"] else None
    return row


def build() -> dict:
    cases = load_cases()
    by_package: dict[str, dict[Version, str]] = {}
    out = {}
    for case in cases:
        package = case["expected"]["package"]
        if package not in by_package:
            by_package[package] = final_releases(package)
            print(f"{package}: {len(by_package[package])} final releases", file=sys.stderr)
        out[case["id"]] = {"package": package, **boundary(case["expected"], by_package[package])}
    return out


def check(rows: dict) -> int:
    """Where the probe checked a case (`check.works_in` / `fails_in`), its releases must sit on the right sides."""
    problems = 0
    for case in load_cases():
        row, probe = rows[case["id"]], case.get("check")
        if row["breaking"] is None or row["released"] is None:
            print(f"{case['id']}: no breaking release found for {row['prefix']!r}")
            problems += 1
        if not probe:
            continue
        breaking = Version(row["breaking"])
        removed = row["side"] == "last_version_with"
        # Removed: it works up to the last release with it and fails from the breaking one. Not yet added: the
        # other way round.
        old, new = (
            (probe["works_in"], probe["fails_in"]) if removed else (probe["fails_in"], probe["works_in"])
        )
        wrong = [v for v in old if Version(v) >= breaking] + [v for v in new if Version(v) < breaking]
        if wrong:
            print(f"{case['id']}: breaking release {breaking} disagrees with the probe at {', '.join(wrong)}")
            problems += 1
    print(f"{len(rows)} cases, {problems} problems")
    return 1 if problems else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check", action="store_true", help="check boundaries.json against the probe's checks"
    )
    args = parser.parse_args()
    if args.check:
        return check(json.loads(OUT.read_text(encoding="utf-8")))
    OUT.write_text(json.dumps(build(), indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
