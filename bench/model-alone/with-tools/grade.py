"""Score the with-tools replies (DT-QA-20) with the unchanged model-alone graders, beside DepTime as it is now.

  uv run python bench/model-alone/with-tools/grade.py > bench/model-alone/with-tools/results-<date>.md

Three parts: (1) a comparison of each model with tools, the same model alone (its model-alone replies) and DepTime
answering by itself, today and on its first run; (2) how much of DepTime's own right answers the model kept, and what
it added; (3) how it used the tools. Then each grader's own tables, run on this folder's replies.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import sys
from collections import Counter
from pathlib import Path

os.environ.setdefault("DEPTIME_OFFLINE", "1")

from deptime.bench import run
from deptime.config import Settings, load_coverage
from deptime.index.location import open_index
from deptime.query import DepTime

HERE = Path(__file__).parent
ALONE = HERE.parent
sys.path[:0] = [str(ALONE), str(ALONE / "upgrades"), str(ALONE.parent / "holdout")]


def _module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tb_grade = _module(ALONE / "grade.py", "traceback_grade")
up_grade = _module(ALONE / "upgrades" / "grade.py", "upgrade_grade")
score = _module(ALONE.parent / "holdout" / "score.py", "holdout_score")
rate = score.rate


def records(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    return {
        r["id"]: r
        for r in (json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip())
    }


def tracebacks(dt: DepTime, name: str) -> list[str]:
    cases = {c["id"]: c for c in tb_grade.load_cases()}
    rows = json.loads((ALONE / "boundaries.json").read_text(encoding="utf-8"))
    coverage = load_coverage()
    first, _ = tb_grade.first_run()
    now = {r.id: r.passed for r in run(dt, list(cases.values()))}

    def marks(path: Path) -> dict[str, bool] | None:
        recs = records(path)
        if set(recs) != set(cases):
            return None
        return {i: tb_grade.grade(cases[i], recs[i]["reply"], rows[i], coverage)["passed"] for i in cases}

    tools = marks(HERE / "tracebacks" / f"{name}-run1.jsonl")
    alone = marks(ALONE / "answers" / f"{name}-run1.jsonl")
    n = len(cases)
    out = [
        "| Answered by | Right package, name and release |",
        "|---|---|",
        f"| DepTime by itself, first run | {rate(sum(first.values()), n)} |",
        f"| DepTime by itself, now (fixes since were designed from these cases) | {rate(sum(now.values()), n)} |",
    ]
    if alone:
        out.append(f"| `{name}` alone | {rate(sum(alone.values()), n)} |")
    if tools:
        out.append(f"| `{name}` with DepTime's tools | {rate(sum(tools.values()), n)} |")
        right = [i for i in cases if now[i]]
        wrong = [i for i in cases if not now[i]]
        out += [
            "",
            f"Of the {len(right)} cases DepTime by itself answers right now, the model with its tools answers"
            f" {rate(sum(tools[i] for i in right), len(right))} right; of the {len(wrong)} it misses, the model gets"
            f" {sum(tools[i] for i in wrong)}.",
        ]
    return out


def upgrades(dt: DepTime, name: str) -> list[str]:
    released = json.loads((ALONE / "upgrades" / "released.json").read_text(encoding="utf-8"))
    rows = up_grade.load_rows(released)
    by_upgrade: dict[str, list[dict]] = {}
    for r in rows:
        by_upgrade.setdefault(r["upgrade"], []).append(r)
    for urows in by_upgrade.values():
        first = urows[0]
        answers = score.ask_check_symbols(dt, {"package": first["package"], "to": first["to"]}, urows)
        for r, a in zip(urows, answers, strict=True):
            r["answers"]["DepTime `check_symbols` by itself, now"] = a["flagged"] if a["answered"] else None

    def add(path: Path, label: str) -> bool:
        recs = records(path)
        if set(recs) != set(by_upgrade):
            return False
        for upgrade, urows in by_upgrade.items():
            verdicts = up_grade.parse_reply(recs[upgrade]["reply"], len(urows)) or {}
            for r in urows:
                r["answers"][label] = verdicts.get(r["number"])
        return True

    who = ["DepTime `check_symbols`, first run", "DepTime `check_symbols` by itself, now"]
    if add(ALONE / "upgrades" / "answers" / f"{name}-run1.jsonl", f"`{name}` alone"):
        who.append(f"`{name}` alone")
    if add(HERE / "upgrades" / f"{name}-run1.jsonl", f"`{name}` with DepTime's tools"):
        who.append(f"`{name}` with DepTime's tools")
    out = ["Abstentions count as not flagged.", "", *up_grade.headline(rows, who, abstain_as_no=True)]
    out += ["", *up_grade.per_upgrade(rows, who)]
    return out


def usage(path: Path) -> list[str]:
    recs = list(records(path).values())
    if not recs:
        return []
    used = [r for r in recs if r.get("tool_calls")]
    calls = Counter(c["tool"] for r in recs for c in r.get("tool_calls", []))
    failed = sum(not c["ok"] for r in recs for c in r.get("tool_calls", []))
    no_reply = sum(not (r.get("reply") or "").strip() for r in recs)
    return [
        f"- Questions where it called a tool: {rate(len(used), len(recs))}; calls by tool: "
        + ", ".join(f"`{t}` {n}" for t, n in calls.most_common())
        + f"; calls that returned an error: {failed}.",
        f"- Replies with no text: {no_reply}; failed conversations: {sum(1 for r in recs if r.get('failed'))};"
        f" cost ${sum(r.get('cost') or 0 for r in recs):.4f}.",
    ]


def grader_tables(module, folder: Path) -> str:
    module.ANSWERS = folder
    argv, sys.argv = sys.argv, ["grade.py"]
    buffer = io.StringIO()
    try:
        with contextlib.redirect_stdout(buffer):
            module.main()
    finally:
        sys.argv = argv
    return buffer.getvalue()


def main() -> int:
    settings = Settings.from_env()
    store = open_index(settings.index_path)
    dt = DepTime(store, load_coverage(settings.coverage_file), settings.index_path)
    names = sorted(
        {
            p.stem.rsplit("-run", 1)[0]
            for test in ("tracebacks", "upgrades")
            for p in (HERE / test).glob("*.jsonl")
        }
    )
    out = [f"Index built {store.built_at()}; DepTime's code at this commit.", ""]
    for name in names:
        out += [f"## `{name}`", "", "### Tracebacks", "", *tracebacks(dt, name), ""]
        out += [*usage(HERE / "tracebacks" / f"{name}-run1.jsonl"), "", "### Upgrade checks", ""]
        out += [*upgrades(dt, name), "", *usage(HERE / "upgrades" / f"{name}-run1.jsonl"), ""]
    out += ["## The tracebacks grader's tables", "", grader_tables(tb_grade, HERE / "tracebacks")]
    out += ["## The upgrade grader's tables", "", grader_tables(up_grade, HERE / "upgrades")]
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
