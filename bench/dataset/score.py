"""Score predictions on the DepTime API-change benchmark. Standard library only; Python 3.9 or newer.

  python score.py --uses my.uses.jsonl                       does each use still work after the upgrade?
  python score.py --tracebacks my.tracebacks.jsonl           which release change explains each traceback?
  python score.py --uses my.uses.jsonl --collection 2026-11f only one collection's items
  python score.py ... --json scores.json                     the numbers as JSON as well

The data files are read from --data (default: this file's directory). The prediction formats and the scoring rules are
in README.md. An item with no prediction counts as an abstention; an id the data doesn't have is an error.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

# The issues that say a release change caused the error. A finding of another kind (or none) doesn't blame a release.
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


def wilson(x: int, n: int) -> tuple[float, float]:
    z = 1.96
    p = x / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centre - half), min(1.0, centre + half)


def rate(x: int, n: int) -> str:
    if not n:
        return "-"
    lo, hi = wilson(x, n)
    return f"{x}/{n} = {100 * x / n:.1f}% (95% CI {100 * lo:.1f} to {100 * hi:.1f}%)"


def ratio(x: int, n: int) -> float | None:
    return round(x / n, 6) if n else None


def canonical(name: str) -> str:
    """A distribution name as PyPI compares them (PEP 503): `Google_GenerativeAI` is `google-generativeai`."""
    return re.sub(r"[-_.]+", "-", name).lower()


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def read_predictions(path: Path, known: set[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for n, p in enumerate(read_jsonl(path), 1):
        pid = p.get("id")
        if pid not in known:
            raise SystemExit(f"{path}:{n}: no item with id {pid!r}")
        if pid in out:
            raise SystemExit(f"{path}:{n}: a second prediction for {pid!r}")
        out[pid] = p
    return out


# ---------------------------------------------------------------------------------------------- uses
def use_counts(rows: list[dict]) -> dict[str, int]:
    """`breaks: true` flags a use; false says it works; null or no prediction abstains."""
    c = {"tp": 0, "fn": 0, "fp": 0, "tn": 0, "abstain_breaks": 0, "abstain_works": 0}
    for r in rows:
        said = r["said"]
        if r["label"] == "breaks":
            c["tp" if said is True else "fn"] += 1
            c["abstain_breaks"] += said is None
        else:
            c["fp" if said is True else "tn"] += 1
            c["abstain_works"] += said is None
    return c


def use_line(name: str, rows: list[dict]) -> str:
    c = use_counts(rows)
    nb = c["tp"] + c["fn"]
    return (
        f"| {name} | {len(rows)} ({nb}) | {rate(c['tp'], nb)} | {rate(c['fp'], c['fp'] + c['tn'])} |"
        f" {rate(c['tp'], c['tp'] + c['fp'])} | {c['abstain_breaks']} / {c['abstain_works']} |"
    )


USE_HEAD = [
    "| group | uses (breaks) | breaks found | working uses flagged | flags that are breaks | abstained (breaks / works) |",
    "|---|---|---|---|---|---|",
]


def score_uses(items: list[dict], preds: dict[str, dict]) -> tuple[list[str], dict]:
    rows = []
    for it in items:
        p = preds.get(it["id"])
        said = p.get("breaks") if p else None
        if said not in (True, False, None):
            raise SystemExit(f"prediction for {it['id']!r}: `breaks` must be true, false or null")
        rows.append({**it, "said": said})
    c = use_counts(rows)
    nb, nw = c["tp"] + c["fn"], c["fp"] + c["tn"]
    by_upgrade: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_upgrade[r["upgrade"]].append(r)
    clean = [rs for rs in by_upgrade.values() if all(r["label"] == "works" for r in rs)]
    alarms = sum(any(r["said"] is True for r in rs) for rs in clean)
    broken = [rs for rs in by_upgrade.values() if any(r["label"] == "breaks" for r in rs)]
    caught = sum(any(r["said"] is True and r["label"] == "breaks" for r in rs) for rs in broken)
    missing = sum(1 for it in items if it["id"] not in preds)
    out = [
        f"**Uses:** {len(rows)} ({nb} break, {nw} work) in {len(by_upgrade)} upgrades;"
        f" {missing} without a prediction (counted as abstentions).",
        "",
        f"- **Breaks found:** {rate(c['tp'], nb)}",
        f"- **Working uses flagged:** {rate(c['fp'], nw)}",
        f"- **Flags that are breaks:** {rate(c['tp'], c['tp'] + c['fp'])}",
        f"- **Abstained:** {c['abstain_breaks']} breaks, {c['abstain_works']} working uses",
        f"- **Upgrades where every use works, with at least one false alarm:** {rate(alarms, len(clean))}",
        f"- **Upgrades with a break, with at least one break flagged:** {rate(caught, len(broken))}",
    ]

    def groups(title: str, key) -> list[str]:
        g: dict[str, list[dict]] = defaultdict(list)
        for r in rows:
            g[key(r)].append(r)
        return ["", f"**By {title}:**", "", *USE_HEAD, *(use_line(k, v) for k, v in sorted(g.items()))]

    out += groups("collection", lambda r: r["collection"])
    out += groups("direction", lambda r: r["direction"])
    out += groups(
        "kind of use", lambda r: r["use"]["kind"] + (" (on an instance)" if r["use"].get("via") else "")
    )
    changes: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r["label"] == "breaks":
            changes[r["change"]].append(r)
    out += ["", "**Breaks found, by change type:**", "", "| change | breaks | found |", "|---|---|---|"]
    for k, v in sorted(changes.items()):
        cc = use_counts(v)
        out.append(f"| {k} | {len(v)} | {rate(cc['tp'], len(v))} |")
    summary = {
        "uses": len(rows),
        "breaks": nb,
        "missing_predictions": missing,
        **c,
        "breaks_found": ratio(c["tp"], nb),
        "working_flagged": ratio(c["fp"], nw),
        "flags_that_are_breaks": ratio(c["tp"], c["tp"] + c["fp"]),
        "clean_upgrades": len(clean),
        "clean_upgrades_with_a_false_alarm": alarms,
    }
    return out, summary


# ---------------------------------------------------------------------------------------------- tracebacks
def judge(case: dict, findings: list[dict]) -> dict:
    """Root cause: the first finding's package, name and kind of change. Boundary and replacement count only when the
    root cause is right."""
    exp = case["expected"]
    top = findings[0] if findings else None
    root = bool(
        top
        and canonical(str(top.get("package") or "")) == canonical(exp["package"])
        and any(
            str(s or "").endswith(exp["symbol_suffix"]) for s in (top.get("symbol"), top.get("defined_at"))
        )
        and top.get("issue") == exp["issue"]
    )
    boundary = replacement = None
    if "last_version_with" in exp:
        boundary = root and str(top.get("last_version_with") or "").startswith(exp["last_version_with"])
    elif "first_version_with" in exp:
        boundary = root and str(top.get("first_version_with") or "").startswith(exp["first_version_with"])
    if "replacement_contains" in exp:
        targets = [str(t) for t in (top.get("replacements") or [])[:3]] if top else []
        replacement = root and any(exp["replacement_contains"] in t for t in targets)
    return {
        "answered": top is not None,
        "root_cause": root,
        "passed": root and boundary is not False,
        "replacement": replacement,
    }


def score_tracebacks(items: list[dict], preds: dict[str, dict]) -> tuple[list[str], dict]:
    out: list[str] = []
    summary: dict = {}
    missing = sum(1 for it in items if it["id"] not in preds)
    out.append(f"**Tracebacks:** {len(items)}; {missing} without a prediction (counted as no finding).")
    by_split: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        by_split[it["split"]].append(it)
    for split in ("holdout", "dev"):
        cases = by_split.get(split)
        if not cases:
            continue
        marks = [judge(c, (preds.get(c["id"]) or {}).get("findings") or []) for c in cases]
        n = len(marks)
        passed = sum(m["passed"] for m in marks)
        root = sum(m["root_cause"] for m in marks)
        answered = [m for m in marks if m["answered"]]
        with_r = [m for m in marks if m["replacement"] is not None]
        out += [
            "",
            f"**`{split}`** ({n} tracebacks from real reports)",
            "",
            f"- **Root cause and boundary:** {rate(passed, n)}",
            f"- Root cause: {rate(root, n)}",
            f"- A right replacement among the first three: {rate(sum(bool(m['replacement']) for m in with_r), len(with_r))}",
            f"- Findings that name the right root cause: {rate(sum(m['root_cause'] for m in answered), len(answered))}",
        ]
        if split == "holdout":
            sets: dict[str, list[dict]] = defaultdict(list)
            for c, m in zip(cases, marks):  # noqa: B905 (`strict=` needs Python 3.10; this runs on 3.9)
                sets[c["collection"]].append(m)
            out += ["", "| collection | tracebacks | root cause and boundary |", "|---|---|---|"]
            out += [
                f"| {k} | {len(v)} | {rate(sum(m['passed'] for m in v), len(v))} |"
                for k, v in sorted(sets.items())
            ]
        summary[split] = {
            "cases": n,
            "root_cause_and_boundary": ratio(passed, n),
            "root_cause": ratio(root, n),
            "replacement": ratio(sum(bool(m["replacement"]) for m in with_r), len(with_r)),
            "passed": passed,
        }
    neg = by_split.get("not-api-change")
    if neg:
        blamed = [
            c
            for c in neg
            if any(f.get("issue") in BLAME for f in (preds.get(c["id"]) or {}).get("findings") or [])
        ]
        out += [
            "",
            f"**`not-api-change`** ({len(neg)} tracebacks with another cause; lower is better)",
            "",
            f"- **Blamed on a release change:** {rate(len(blamed), len(neg))}",
        ]
        summary["not-api-change"] = {"cases": len(neg), "blamed": len(blamed)}
    return out, summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=Path(__file__).resolve().parent)
    ap.add_argument("--uses", type=Path, help="predictions for uses.jsonl")
    ap.add_argument("--tracebacks", type=Path, help="predictions for tracebacks.jsonl")
    ap.add_argument("--collection", help="score only this collection's items")
    ap.add_argument("--json", type=Path, help="also write the numbers here")
    a = ap.parse_args(argv)
    if not (a.uses or a.tracebacks):
        ap.error("give --uses, --tracebacks or both")
    out: list[str] = []
    summary: dict = {}
    for task, path, scorer in (
        ("uses", a.uses, score_uses),
        ("tracebacks", a.tracebacks, score_tracebacks),
    ):
        if path is None:
            continue
        items = read_jsonl(a.data / f"{task}.jsonl")
        preds = read_predictions(path, {it["id"] for it in items})
        if a.collection:
            items = [it for it in items if it["collection"] == a.collection]
            if not items:
                raise SystemExit(f"no {task} in collection {a.collection!r}")
        lines, summary[task] = scorer(items, preds)
        out += ([""] if out else []) + lines
    print("\n".join(out))
    if a.json:
        a.json.write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
