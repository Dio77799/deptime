"""Score DT-QA-17: how often `explain_error` blames a release for a traceback with another cause.

    uv run python bench/false-blame/score.py bench/false-blame/cases.jsonl > bench/false-blame/results-<date>.md

The protocol is `bench/false-blame/README.md`.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path

from deptime.config import Settings, load_coverage
from deptime.index.location import open_index
from deptime.query import DepTime

BLAME = frozenset(
    {
        "symbol_removed",
        "symbol_not_yet_added",
        "param_removed",
        "param_not_yet_added",
        "param_now_required",
        "param_kind_changed",
        "module_removed",
    }
)
CAUSES = ("never_existed", "install", "shadowing", "usage", "environment")
RANK = {"high": 0, "medium": 1, "low": 2}


def wilson(x: int, n: int) -> tuple[float, float] | None:
    if not n:
        return None
    z = 1.96
    p = x / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centre - half), min(1.0, centre + half)


def rate(x: int, n: int) -> str:
    if not n:
        return "-"
    lo, hi = wilson(x, n)  # type: ignore[misc]
    return f"{x}/{n} = {100 * x / n:.1f}% (95% CI {100 * lo:.1f} to {100 * hi:.1f}%)"


def judge(case: dict, result) -> dict:
    blames = sorted((f for f in result.findings if f.issue in BLAME), key=lambda f: RANK[f.confidence])
    top = blames[0] if blames else None
    kinds = [f.issue for f in result.findings]
    return {
        "id": case["id"],
        "cause": case["cause"],
        "package": case["package"],
        "blamed": top is not None,
        "confidence": top.confidence if top else None,
        "finding": (
            f"{top.package} `{top.symbol}` {top.issue} (last with {top.last_version_with}, "
            f"first with {top.first_version_with})"
            if top
            else None
        ),
        "kinds": kinds,
        "not_covered": list(result.not_covered),
        "points_at_cause": case["cause"] == "never_existed" and "never_existed" in kinds,
    }


def report(rows: list[dict], built_at: str | None) -> str:
    n = len(rows)
    blamed = [r for r in rows if r["blamed"]]
    out = [
        "# DT-QA-17 results",
        "",
        f"Index built {built_at}. Protocol: [README.md](README.md). First and only scored run.",
        "",
        f"**Blamed a release:** {rate(len(blamed), n)}",
        "",
        "| Top blame's confidence | Cases |",
        "|---|---|",
        *(f"| {c} | {sum(r['confidence'] == c for r in blamed)} |" for c in RANK),
        "",
        "| Cause | Cases | Blamed |",
        "|---|---|---|",
    ]
    for cause in CAUSES:
        of = [r for r in rows if r["cause"] == cause]
        if of:
            out.append(f"| {cause} | {len(of)} | {sum(r['blamed'] for r in of)} |")
    kept = [r for r in rows if not r["blamed"]]
    said = Counter(k for r in kept for k in (r["kinds"] or ["no finding"]))
    ne = [r for r in rows if r["cause"] == "never_existed"]
    out += [
        "",
        "**What the answers that don't blame said** (finding kinds, a case can have several): "
        + (", ".join(f"{k} {v}" for k, v in said.most_common()) or "-"),
        "",
        f"`never_existed` answers on `never_existed` cases: {sum(r['points_at_cause'] for r in ne)} of {len(ne)}.",
        "",
        "## Blamed cases",
        "",
        "| Case | Cause | Confidence | Finding |",
        "|---|---|---|---|",
        *(f"| {r['id']} | {r['cause']} | {r['confidence']} | {r['finding']} |" for r in blamed),
        "",
        "## Every case",
        "",
        "| Case | Package | Cause | Answer |",
        "|---|---|---|---|",
    ]
    for r in rows:
        answer = r["finding"] or (", ".join(r["kinds"]) if r["kinds"] else "no finding")
        if r["not_covered"]:
            answer += f" (not covered: {', '.join(r['not_covered'])})"
        out.append(f"| {r['id']} | {r['package']} | {r['cause']} | {answer} |")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("cases", type=Path)
    parser.add_argument("--json", type=Path, help="also write each case's judgement here")
    args = parser.parse_args(argv)
    settings = Settings.from_env()
    store = open_index(settings.index_path)
    if store is None:
        print(f"no index at {settings.index_path}; run `deptime index pull` first", file=sys.stderr)
        return 2
    dt = DepTime(store, load_coverage(settings.coverage_file), settings.index_path)
    cases = [json.loads(line) for line in args.cases.read_text(encoding="utf-8").splitlines() if line.strip()]
    for c in cases:
        if c["cause"] not in CAUSES:
            raise SystemExit(f"{c['id']}: unknown cause {c['cause']!r}")
    rows = [judge(c, dt.explain_error(c["traceback"], c.get("installed") or None)) for c in cases]
    if args.json:
        args.json.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    sys.stdout.write(report(rows, store.built_at()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
