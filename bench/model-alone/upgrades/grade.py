"""Score a model's verdicts on the 2026-11f upgrade checks beside DepTime's first run (DT-QA-18).

  uv run python bench/model-alone/upgrades/grade.py --dates                      released.json, from the local index
  uv run python bench/model-alone/upgrades/grade.py --shortcuts > shortcuts.md   the no-knowledge rules alone
  uv run python bench/model-alone/upgrades/grade.py > results-<date>.md          every answers/*.jsonl as well

The rule is in README.md and was committed before any model was asked. A use is flagged when the answer says it
breaks: the model's "breaks", DepTime's first run as bench/holdout/2026-11f/baseline.json records it, or a rule's
guess. "unknown", a missing verdict and DepTime's abstentions are abstentions. Rates and intervals are
bench/holdout/score.py's.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

from cases import SET, load_upgrades
from packaging.version import Version

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "holdout"))
from score import rate

HERE = Path(__file__).parent
ANSWERS = HERE / "answers"
RELEASED = HERE / "released.json"
# Anthropic gives Claude Sonnet 5.5 a training data cutoff of June 2026 (../README.md).
AFTER_CUTOFF = "2026-07-01"
VERDICTS = {"works": False, "work": False, "breaks": True, "break": True, "broken": True, "unknown": None}


# ---------------------------------------------------------------------------------------------- the uses
def series(version: str) -> tuple[int, ...]:
    """The release series: the first number, or the first two below 1.0 (0.27 and 0.28 are different series)."""
    release = Version(version).release
    return release[:2] if release[0] == 0 else release[:1]


def load_rows(released: dict[str, str | None]) -> list[dict]:
    """One row per scored use, with its label, its splits and DepTime's first-run answers."""
    baseline = json.loads((SET / "baseline.json").read_text(encoding="utf-8"))["uses"]
    rows = []
    for up in load_upgrades():
        newer = max(up["from"], up["to"], key=Version)
        day = released.get(f"{up['package']}=={newer}")
        for n, item in enumerate(up["items"], 1):
            first = baseline[f"{up['id']}|{item['key']}"]
            assert first["label"] == item["label"], (up["id"], item["key"])
            rows.append(
                {
                    **item,
                    "number": n,
                    "upgrade": up["id"],
                    "package": up["package"],
                    "from": up["from"],
                    "to": up["to"],
                    "direction": up["direction"],
                    "newer_release": "unknown date"
                    if day is None
                    else ("from 2026-07-01 (after the cutoff)" if day >= AFTER_CUTOFF else "by 2026-06-30"),
                    "series": "differs" if series(up["from"]) != series(up["to"]) else "same",
                    "answers": {
                        "DepTime `check_symbols`, first run": first["check_symbols"],
                        "DepTime `diff_versions`, first run": first["diff_versions"],
                    },
                }
            )
    return rows


# ---------------------------------------------------------------------------------------------- rules that know nothing
SHORTCUTS = {
    "Rule: everything works": lambda r: False,
    "Rule: breaks when the first number differs": lambda r: (
        Version(r["from"]).release[0] != Version(r["to"]).release[0]
    ),
    "Rule: breaks when the series differs (0.x: the second number)": lambda r: r["series"] == "differs",
    "Rule: everything breaks going down": lambda r: r["direction"] == "down",
}


# ---------------------------------------------------------------------------------------------- the model's replies
def parse_reply(text: str, count: int) -> dict[int, bool | None] | None:
    """Use number -> flagged (True), not (False) or abstained (None), for the numbers the reply gives a verdict.
    The first JSON object in the reply; a list of `count` verdicts is read in order. Form isn't marked: a code fence,
    text around it, case and spaces."""
    decoder = json.JSONDecoder()
    for match in re.finditer(r"[\{\[]", text):
        try:
            value, _ = decoder.raw_decode(text, match.start())
        except ValueError:
            continue
        if isinstance(value, list) and len(value) == count:
            value = {str(n): v for n, v in enumerate(value, 1)}
        if not isinstance(value, dict):
            continue
        out: dict[int, bool | None] = {}
        for key, verdict in value.items():
            number = str(key).strip().rstrip(".")
            word = verdict.strip().lower() if isinstance(verdict, str) else None
            if number.isdigit() and 1 <= int(number) <= count and word in VERDICTS:
                out[int(number)] = VERDICTS[word]
        return out
    return None


def load_answers(rows: list[dict]) -> tuple[list[str], list[str]]:
    """Adds each answers/*.jsonl's verdicts to the rows; returns the answerers' names and a note per file."""
    by_upgrade: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_upgrade[r["upgrade"]].append(r)
    names, notes = [], []
    for path in sorted(ANSWERS.glob("*.jsonl")):
        records = {
            x["id"]: x
            for x in (json.loads(s) for s in path.read_text(encoding="utf-8").splitlines() if s.strip())
        }
        model_ids = sorted({str(x.get("model_id")) for x in records.values()})
        name = f"{', '.join(model_ids)} alone ({path.stem.split('-')[-1].replace('run', 'run ')})"
        unparsed = missing = unknown = 0
        for upgrade, urows in by_upgrade.items():
            record = records.get(upgrade)
            verdicts = parse_reply(record["reply"], len(urows)) if record else None
            if record and verdicts is None:
                unparsed += 1
            for r in urows:
                if verdicts is None or r["number"] not in verdicts:
                    missing += 1
                    r["answers"][name] = None
                else:
                    unknown += verdicts[r["number"]] is None
                    r["answers"][name] = verdicts[r["number"]]
        tokens = [x.get("output_tokens") or 0 for x in records.values()]
        seconds = [x.get("seconds") or 0 for x in records.values()]
        notes.append(
            f"- **{name}** (`{path.name}`): {len(records)} replies for {len(by_upgrade)} upgrades;"
            f" {unparsed} not a JSON object; {missing} uses without a verdict and {unknown} `unknown`, both counted"
            f" as abstentions; median {statistics.median(tokens or [0]):.0f} output tokens and"
            f" {statistics.median(seconds or [0]):.0f} s a call."
        )
        names.append(name)
    return names, notes


# ---------------------------------------------------------------------------------------------- scoring
def counts(rows: list[dict], who: str, abstain_as_no: bool = False) -> dict[str, int]:
    c = {"tp": 0, "fp": 0, "fn": 0, "tn": 0, "abstain_breaks": 0, "abstain_works": 0}
    for r in rows:
        flagged = r["answers"].get(who)
        if flagged is None and not abstain_as_no:
            c["abstain_breaks" if r["label"] == "breaks" else "abstain_works"] += 1
            continue
        if r["label"] == "breaks":
            c["tp" if flagged else "fn"] += 1
        else:
            c["fp" if flagged else "tn"] += 1
    return c


def headline(rows: list[dict], who: list[str], abstain_as_no: bool) -> list[str]:
    out = [
        "| Answered by | Breaks found (recall) | Working uses flagged | Precision | Abstained |",
        "|---|---|---|---|---|",
    ]
    for name in who:
        c = counts(rows, name, abstain_as_no)
        abstained = "-" if abstain_as_no else f"{c['abstain_breaks']} breaks, {c['abstain_works']} works"
        out.append(
            f"| {name} | {rate(c['tp'], c['tp'] + c['fn'])} | {rate(c['fp'], c['fp'] + c['tn'])}"
            f" | {rate(c['tp'], c['tp'] + c['fp'])} | {abstained} |"
        )
    return out


def per_upgrade(rows: list[dict], who: list[str]) -> list[str]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        groups[r["upgrade"]].append(r)
    clean = [g for g in groups.values() if all(r["label"] == "works" for r in g)]
    broken = [g for g in groups.values() if any(r["label"] == "breaks" for r in g)]
    out = [
        "| Answered by | Upgrades where every use works, with a false alarm | Upgrades with a break, at least one found |",
        "|---|---|---|",
    ]
    for name in who:
        alarms = sum(any(r["answers"].get(name) and r["label"] == "works" for r in g) for g in clean)
        found = sum(any(r["answers"].get(name) and r["label"] == "breaks" for r in g) for g in broken)
        out.append(f"| {name} | {rate(alarms, len(clean))} | {rate(found, len(broken))} |")
    return out


def split(rows: list[dict], who: list[str], key: str, recall_only: bool = False) -> list[str]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if not recall_only or r["label"] == "breaks":
            groups[r.get(key) or "-"].append(r)
    head = "breaks" if recall_only else "uses (breaks/works)"
    out = [f"| {key} | {head} | " + " | ".join(who) + " |", "|---|---|" + "---|" * len(who)]
    for group, g in sorted(groups.items()):
        nb = sum(r["label"] == "breaks" for r in g)
        cells = []
        for name in who:
            c = counts(g, name, abstain_as_no=True)
            recall = rate(c["tp"], c["tp"] + c["fn"])
            cells.append(recall if recall_only else f"{recall}; flagged {rate(c['fp'], c['fp'] + c['tn'])}")
        size = str(nb) if recall_only else f"{len(g)} ({nb}/{len(g) - nb})"
        out.append(f"| {group} | {size} | " + " | ".join(cells) + " |")
    return out


def describe(r: dict) -> str:
    if r["kind"] == "call":
        args = ["_"] * (r.get("npos") or 0) + [f"{k}=" for k in r.get("kwargs", [])]
        return f"{r['path']}({', '.join(args)})"
    return r["path"]


def report(rows: list[dict], who: list[str], notes: list[str], models: list[str]) -> str:
    nb = sum(r["label"] == "breaks" for r in rows)
    out = [
        f"**Uses:** {len(rows)} ({nb} break, {len(rows) - nb} work) in {len({r['upgrade'] for r in rows})} upgrades"
        " of the 2026-11f holdout.",
        "",
        *notes,
        "",
        "### Abstentions count as not flagged",
        "",
        "How a check on a pull request behaves: an answer that isn't `breaks` doesn't fail it.",
        "",
        *headline(rows, who, abstain_as_no=True),
        "",
        "### Abstentions apart",
        "",
        "As the holdout's own results count them (`../../holdout/score.py`).",
        "",
        *headline(rows, who, abstain_as_no=False),
        "",
        "Rates with 95% Wilson intervals. Uses within one project aren't independent, so the intervals are narrower"
        " than they should be; the per-upgrade table is the check on that.",
        "",
        "### Per upgrade",
        "",
        *per_upgrade(rows, who),
        "",
        "### Splits (fixed in advance; abstentions count as not flagged)",
        "",
        "Each cell is the breaks found, then the working uses flagged.",
        "",
        "**Direction** (`down`: the code was written for a newer release than the one it gets):",
        "",
        *split(rows, who, "direction"),
        "",
        "**The newer of the two releases**, by its upload to PyPI (`released.json`), against the training cutoff:",
        "",
        *split(rows, who, "newer_release"),
        "",
        "**Whether the release series differs** (the first number, or the first two below 1.0), which the question"
        " shows:",
        "",
        *split(rows, who, "series"),
        "",
        "**Change type of each break** (breaks found):",
        "",
        *split(rows, who, "change", recall_only=True),
    ]
    for name in models:
        fps = [r for r in rows if r["label"] == "works" and r["answers"].get(name)]
        fns = [r for r in rows if r["label"] == "breaks" and r["answers"].get(name) is False]
        abst = [r for r in rows if r["label"] == "breaks" and r["answers"].get(name) is None]
        out += ["", f"<details><summary>{name}: working uses flagged ({len(fps)})</summary>", ""]
        out += [f"- `{r['package']}` {r['from']} → {r['to']}: `{describe(r)}`" for r in fps]
        out += ["", "</details>", "", f"<details><summary>{name}: breaks missed ({len(fns)})</summary>", ""]
        out += [f"- `{r['package']}` {r['from']} → {r['to']}: `{describe(r)}` ({r['change']})" for r in fns]
        out += [
            "",
            "</details>",
            "",
            f"<details><summary>{name}: breaks abstained on ({len(abst)})</summary>",
            "",
        ]
        out += [f"- `{r['package']}` {r['from']} → {r['to']}: `{describe(r)}` ({r['change']})" for r in abst]
        out += ["", "</details>"]
    return "\n".join(out)


def write_dates() -> int:
    """released.json: the day PyPI received each release the questions name, read from the local index."""
    from deptime.config import Settings
    from deptime.index.location import open_index

    store = open_index(Settings.from_env().index_path)
    if store is None:
        print("no index; run `deptime index pull` first", file=sys.stderr)
        return 2
    wanted = {(u["package"], v) for u in load_upgrades() for v in (u["from"], u["to"])}
    dates = {}
    for package, version in sorted(wanted):
        row = store.release(package, version)
        dates[f"{package}=={version}"] = ((row["released_at"] or "")[:10] or None) if row else None
    RELEASED.write_text(json.dumps(dates, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{len(dates)} releases, {sum(v is None for v in dates.values())} without a date", file=sys.stderr)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dates", action="store_true", help="write released.json from the local index")
    parser.add_argument("--shortcuts", action="store_true", help="the rules and DepTime only, no replies")
    args = parser.parse_args()
    if args.dates:
        return write_dates()
    rows = load_rows(json.loads(RELEASED.read_text(encoding="utf-8")))
    for name, rule in SHORTCUTS.items():
        for r in rows:
            r["answers"][name] = rule(r)
    deptime = [n for n in rows[0]["answers"] if n.startswith("DepTime")]
    models, notes = ([], []) if args.shortcuts else load_answers(rows)
    print(report(rows, deptime + models + list(SHORTCUTS), notes, models))
    return 0


if __name__ == "__main__":
    sys.exit(main())
