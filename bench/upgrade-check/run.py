"""Score `deptime check-upgrade` end to end on the holdout projects (DT-QA-21), by the rules in README.md here.

    uv run python bench/upgrade-check/run.py <sources dir> --out <results.md> [--json <rows.json>] [--sets 2026-11f ...]

<sources dir> holds each project's source at its commit as <owner>__<repo>@<commit>/ (fetched here when missing, as
`../holdout/find_pinned.py` fetches them: the GitHub tarball, only .py, .txt, .toml and .cfg files kept, read as data).
Each upgrade runs through `deptime.upgrade.check_upgrade`, the function behind `deptime check-upgrade --package P
--from F --to T`, against the index in DEPTIME_HOME. Nothing here runs any project's code.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
HOLDOUT = HERE.parent / "holdout"
sys.path.insert(0, str(HOLDOUT))

from find_pinned import fetch_source  # noqa: E402  (the benchmark's own fetcher, never DepTime's reader)
from score import _v, ask_check_symbols, rate  # noqa: E402

from deptime.config import Settings, load_coverage  # noqa: E402
from deptime.index.location import open_index  # noqa: E402
from deptime.models import DependencyChange  # noqa: E402
from deptime.query import DepTime  # noqa: E402
from deptime.upgrade import _Read, check_upgrade, project_files, read_code, uses_in  # noqa: E402

SETS = ("2026-11", "2026-11b", "2026-11c", "2026-11d", "2026-11e", "2026-11f")
CALL_KINDS = {"missing_args", "too_many_positional", "raises"}
# The bar, fixed in README.md before the first run: pooled over the six sets, unread and `unknown` as not flagged.
BAR = {"recall": 0.90, "fpr": 0.01, "clean_alarms": 0.05, "read": 0.95}


def slug(repo: str) -> str:
    return repo.removeprefix("https://github.com/").replace("/", "__")


def source(sources: Path, row: dict) -> Path | None:
    dest = sources / f"{slug(row['repo'])}@{row['commit']}"
    try:
        fetch_source(row["repo"].removeprefix("https://github.com/"), row["commit"], dest)
    except Exception as exc:  # a repository deleted or made private since the set was collected
        print(f"{row['id']}: source unavailable: {type(exc).__name__}: {exc}", file=sys.stderr)
        return None
    return dest if dest.is_dir() else None


def read_paths(dt: DepTime, row: dict, code: dict[str, str]) -> set[str]:
    """The paths DepTime's reader reads for the package in the project: the queries check-upgrade asks."""
    spec = dt._spec(row["package"])
    read = _Read()
    for rel, text in code.items():
        if (found := uses_in(text, tuple(spec.import_names))) is not None:
            read.merge(rel, found)
    queries, _ = dt._code_queries(spec.name, row["to"], [], read.uses)
    return {q.path for q in queries}


def flagged(item: dict, breaks: list) -> bool:
    """Whether check-upgrade's breaks flag this labelled use (README.md, "Matching")."""
    for b in breaks:
        if b.path != item["path"]:
            continue
        if b.kind == "missing":
            return True
        if item["kind"] == "call" and (
            b.kind in CALL_KINDS or (b.kind == "rejected_kwarg" and b.kwarg in item.get("kwargs", []))
        ):
            return True
    return False


def run(
    dt: DepTime, sources: Path, sets: list[str], holdout: Path = HOLDOUT
) -> tuple[list[dict], list[dict], list[str]]:
    uses: list[dict] = []
    upgrades: list[dict] = []
    unavailable: list[str] = []
    for name in sets:
        root = holdout / name
        rows = {
            r["id"]: r
            for r in map(json.loads, (root / "upgrades.jsonl").read_text(encoding="utf-8").splitlines())
        }
        for lab in map(json.loads, (root / "labels.jsonl").read_text(encoding="utf-8").splitlines()):
            row = rows[lab["id"]]
            items = [i for i in lab["items"] if i["label"] in ("works", "breaks")]
            if not items:
                continue
            src = source(sources, row)
            if src is None:
                unavailable.append(f"{name} {row['id']}")
                continue
            code = read_code(src, project_files(src))
            change = DependencyChange(package=row["package"], from_version=row["from"], to_version=row["to"])
            result = check_upgrade(dt, row["id"], code, [change])
            pkg = result.checked[0] if result.checked else None
            breaks = pkg.breaks if pkg else []
            notices = pkg.notices if pkg else []
            seen = read_paths(dt, row, code)
            per_use = ask_check_symbols(dt, row, items)  # score.py's per-use answer, for comparison
            direction = (
                "tmb" if row["source"] == "tmb" else ("down" if _v(row["to"]) < _v(row["from"]) else "up")
            )
            labelled = {i["path"] for i in lab["items"]}
            deprecated = {n.path for n in notices if n.status == "deprecated"}
            for i, cs in zip(items, per_use, strict=True):
                uses.append(
                    {
                        "set": name,
                        "upgrade": row["id"],
                        "direction": direction,
                        "package": row["package"],
                        "path": i["path"],
                        "kind": i["kind"] + (" (instance)" if i.get("via") == "instance" else ""),
                        "label": i["label"],
                        "change": i.get("change"),
                        "label_deprecated": bool(i.get("deprecated")),
                        "read": i["path"] in seen,
                        "flagged": flagged(i, breaks),
                        "listed_deprecated": i["path"] in deprecated,
                        "per_use_flagged": cs["answered"] and cs["flagged"],
                    }
                )
            upgrades.append(
                {
                    "set": name,
                    "upgrade": row["id"],
                    "direction": direction,
                    "package": row["package"],
                    "from": row["from"],
                    "to": row["to"],
                    "clean": all(i["label"] == "works" for i in items),
                    "fails": result.breaks > 0,
                    "breaks": [
                        {
                            "path": b.path,
                            "kind": b.kind,
                            "kwarg": b.kwarg,
                            "labelled": b.path in labelled,
                            "explanation": b.explanation,
                            "at": [f"{loc.file}:{loc.line}" for loc in b.locations[:3]],
                        }
                        for b in breaks
                    ],
                    "files_read": result.files_read,
                    "files_unreadable": len(result.files_unreadable),
                    "failing_before": sum(n.status == "failing_before" for n in notices),
                    "unknown": sum(n.status == "unknown" for n in notices),
                }
            )
    return uses, upgrades, unavailable


def _share(x: int, n: int) -> float:
    return x / n if n else 0.0


def report(uses: list[dict], upgrades: list[dict], unavailable: list[str], built_at: str | None) -> list[str]:
    out = [f"Index built {built_at}.", ""]

    def use_rows(rows: list[dict], key: str = "flagged", only_read: bool = False) -> tuple[str, str, str]:
        rows = [r for r in rows if r["read"]] if only_read else rows
        b = [r for r in rows if r["label"] == "breaks"]
        w = [r for r in rows if r["label"] == "works"]
        tp, fp = sum(r[key] for r in b), sum(r[key] for r in w)
        return rate(tp, len(b)), rate(fp, len(w)), rate(tp, tp + fp)

    def upgrade_rows(rows: list[dict]) -> tuple[str, str]:
        clean = [u for u in rows if u["clean"]]
        broken = [u for u in rows if not u["clean"]]
        return rate(sum(u["fails"] for u in clean), len(clean)), rate(
            sum(u["fails"] for u in broken), len(broken)
        )

    def read_rate(rows: list[dict]) -> str:
        return rate(sum(r["read"] for r in rows), len(rows))

    groups: dict[str, list[str]] = {"all six sets": list(SETS)} | {s: [s] for s in SETS}
    out += [
        "## End to end",
        "",
        "Unread uses and `unknown` count as not flagged. 95% Wilson intervals.",
        "",
        "| set | breaks found | working uses flagged | precision | clean upgrades failed | upgrades with a break"
        " failed | labelled uses read |",
        "|---|---|---|---|---|---|---|",
    ]
    for label, names in groups.items():
        us = [r for r in uses if r["set"] in names]
        ups = [u for u in upgrades if u["set"] in names]
        if not us:
            continue
        rec, fpr, prec = use_rows(us)
        clean, broken = upgrade_rows(ups)
        out.append(f"| {label} | {rec} | {fpr} | {prec} | {clean} | {broken} | {read_rate(us)} |")

    out += [
        "",
        "## Beside the per-use answer",
        "",
        "`check_symbols` asked about each labelled use directly (`../holdout/score.py`'s rule, today's index): what"
        " the reader and the old-version filter cost.",
        "",
        "| set | per use: breaks found | per use: working flagged | check-upgrade, read uses only: breaks found |"
        " read uses only: working flagged |",
        "|---|---|---|---|---|",
    ]
    for label, names in groups.items():
        us = [r for r in uses if r["set"] in names]
        if not us:
            continue
        prec_rec, prec_fpr, _ = use_rows(us, "per_use_flagged")
        r_rec, r_fpr, _ = use_rows(us, only_read=True)
        out.append(f"| {label} | {prec_rec} | {prec_fpr} | {r_rec} | {r_fpr} |")

    out += ["", "## Splits (all six sets)", ""]
    for title, key in (("Direction", "direction"), ("Kind of use", "kind")):
        out += [f"**{title}:**", "", "| | breaks found | working uses flagged | read |", "|---|---|---|---|"]
        g: dict[str, list[dict]] = defaultdict(list)
        for r in uses:
            g[r[key]].append(r)
        for k, rows in sorted(g.items()):
            rec, fpr, _ = use_rows(rows)
            out.append(f"| {k} | {rec} | {fpr} | {read_rate(rows)} |")
        out.append("")
    out += ["**Change type (breaks found):**", "", "| change | breaks found |", "|---|---|"]
    g = defaultdict(list)
    for r in uses:
        if r["label"] == "breaks":
            g[r["change"] or "other"].append(r)
    for k, rows in sorted(g.items()):
        out.append(f"| {k} | {rate(sum(r['flagged'] for r in rows), len(rows))} |")

    dep = [r for r in uses if r["label"] == "works" and r["label_deprecated"]]
    listed = [r for r in uses if r["label"] == "works" and r["listed_deprecated"]]
    out += [
        "",
        "## Deprecations (reported, no bar)",
        "",
        f"Working uses the probe found deprecated at `to`: listed as deprecated in"
        f" {rate(sum(r['listed_deprecated'] for r in dep), len(dep))}. Working uses listed as deprecated: the probe"
        f" agrees for {rate(sum(r['label_deprecated'] for r in listed), len(listed))}. (2026-11 has no deprecation"
        " labels.)",
    ]

    total = sum(len(u["breaks"]) for u in upgrades)
    unlabelled = [(u, b) for u in upgrades for b in u["breaks"] if not b["labelled"]]
    clean_alarms = [u for u in upgrades if u["clean"] and u["fails"]]
    out += [
        "",
        "## Every break reported",
        "",
        f"{total} breaks in {sum(u['fails'] for u in upgrades)} of {len(upgrades)} upgrades;"
        f" {len(unlabelled)} on a path with no label in its upgrade (excluded by the probe, or beyond the 40-use cap):"
        " listed below, not scored.",
        "",
        "**Clean upgrades the check fails:**",
        "",
    ]
    for u in clean_alarms:
        for b in u["breaks"]:
            where = ", ".join(b["at"])
            out.append(
                f"- {u['set']} `{u['upgrade']}` ({u['package']} {u['from']} → {u['to']}): {b['explanation']}"
                f" {'(labelled works)' if b['labelled'] else '(unlabelled)'} at {where}"
            )
    out += ["", "**Unlabelled breaks in upgrades that have a labelled break:**", ""]
    for u, b in unlabelled:
        if not u["clean"]:
            out.append(f"- {u['set']} `{u['upgrade']}`: {b['explanation']} at {', '.join(b['at'])}")
    misses = [r for r in uses if r["label"] == "breaks" and not r["flagged"]]
    false = [r for r in uses if r["label"] == "works" and r["flagged"]]
    out += ["", "**Breaks not found:**", ""]
    out += [
        f"- {r['set']} `{r['upgrade']}`: `{r['path']}` ({r['kind']}, {r['change']})"
        f"{'' if r['read'] else ', not read'}{', per-use check flags it' if r['per_use_flagged'] else ''}"
        for r in misses
    ]
    out += ["", "**Working uses flagged:**", ""]
    out += [f"- {r['set']} `{r['upgrade']}`: `{r['path']}` ({r['kind']})" for r in false]
    out += ["", f"**Sources unavailable ({len(unavailable)}):** " + (", ".join(unavailable) or "none"), ""]

    b = [r for r in uses if r["label"] == "breaks"]
    w = [r for r in uses if r["label"] == "works"]
    clean = [u for u in upgrades if u["clean"]]
    got = {
        "recall": _share(sum(r["flagged"] for r in b), len(b)),
        "fpr": _share(sum(r["flagged"] for r in w), len(w)),
        "clean_alarms": _share(sum(u["fails"] for u in clean), len(clean)),
        "read": _share(sum(r["read"] for r in uses), len(uses)),
    }
    met = {
        "recall": got["recall"] >= BAR["recall"],
        "fpr": got["fpr"] <= BAR["fpr"],
        "clean_alarms": got["clean_alarms"] <= BAR["clean_alarms"],
        "read": got["read"] >= BAR["read"],
    }
    out = [
        "## The bar",
        "",
        "| measure (all six sets) | bar | result | met |",
        "|---|---|---|---|",
        f"| breaks found | ≥ 90% | {100 * got['recall']:.1f}% | {'yes' if met['recall'] else 'no'} |",
        f"| working uses flagged | ≤ 1% | {100 * got['fpr']:.2f}% | {'yes' if met['fpr'] else 'no'} |",
        f"| clean upgrades the check fails | ≤ 5% | {100 * got['clean_alarms']:.1f}% |"
        f" {'yes' if met['clean_alarms'] else 'no'} |",
        f"| labelled uses the reader reads | ≥ 95% | {100 * got['read']:.1f}% | {'yes' if met['read'] else 'no'} |",
        "",
        *out,
    ]
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("sources", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--json", type=Path)
    ap.add_argument("--sets", nargs="*", default=list(SETS))
    a = ap.parse_args(argv)
    settings = Settings.from_env()
    store = open_index(settings.index_path)
    if store is None:
        print(f"no index at {settings.index_path}; run `deptime index pull` first", file=sys.stderr)
        return 2
    dt = DepTime(store, load_coverage(settings.coverage_file), settings.index_path)
    a.sources.mkdir(parents=True, exist_ok=True)
    uses, upgrades, unavailable = run(dt, a.sources, a.sets)
    a.out.write_text(
        "\n".join(report(uses, upgrades, unavailable, store.built_at())) + "\n", encoding="utf-8"
    )
    if a.json:
        a.json.write_text(
            json.dumps({"uses": uses, "upgrades": upgrades, "unavailable": unavailable}, indent=1)
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
