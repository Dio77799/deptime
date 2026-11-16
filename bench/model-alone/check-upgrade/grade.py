"""Score the replies of the model offered `check_upgrade` (DT-QA-23) with the unchanged upgrade grader.

  uv run python bench/model-alone/check-upgrade/grade.py > bench/model-alone/check-upgrade/results-<date>.md

Beside the model alone, the model with the five tools (DT-QA-20) and DepTime's `check_symbols` by itself, first run
and on this index; then the same measures split by whether the model called `check_upgrade` in that upgrade, how it
used the tools, and the grader's own tables on this folder's replies.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("DEPTIME_OFFLINE", "1")

from deptime.config import Settings, load_coverage
from deptime.index.location import open_index
from deptime.query import DepTime

HERE = Path(__file__).parent
ALONE = HERE.parent
MODEL = "qwen3.5-9b"


def _module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


wt = _module(ALONE / "with-tools" / "grade.py", "with_tools_grade")  # its records, usage and graders
up_grade, score = wt.up_grade, wt.score

FIRST = "DepTime `check_symbols`, first run"
NOW = "DepTime `check_symbols` by itself, now"
ALONE_LABEL = f"`{MODEL}` alone"
FIVE = f"`{MODEL}` with the five tools (DT-QA-20)"
SIX = f"`{MODEL}` with the six tools, `check_upgrade` among them"


def main() -> int:
    settings = Settings.from_env()
    store = open_index(settings.index_path)
    dt = DepTime(store, load_coverage(settings.coverage_file), settings.index_path)
    released = json.loads((ALONE / "upgrades" / "released.json").read_text(encoding="utf-8"))
    rows = up_grade.load_rows(released)
    by_upgrade: dict[str, list[dict]] = {}
    for r in rows:
        by_upgrade.setdefault(r["upgrade"], []).append(r)
    for urows in by_upgrade.values():
        first = urows[0]
        answers = score.ask_check_symbols(dt, {"package": first["package"], "to": first["to"]}, urows)
        for r, a in zip(urows, answers, strict=True):
            r["answers"][NOW] = a["flagged"] if a["answered"] else None

    def add(path: Path, label: str) -> dict[str, dict] | None:
        recs = wt.records(path)
        if set(recs) != set(by_upgrade):
            return None
        for upgrade, urows in by_upgrade.items():
            verdicts = up_grade.parse_reply(recs[upgrade]["reply"], len(urows)) or {}
            for r in urows:
                r["answers"][label] = verdicts.get(r["number"])
        return recs

    who = [FIRST, NOW]
    for path, label in (
        (ALONE / "upgrades" / "answers" / f"{MODEL}-run1.jsonl", ALONE_LABEL),
        (ALONE / "with-tools" / "upgrades" / f"{MODEL}-run1.jsonl", FIVE),
    ):
        if add(path, label) is not None:
            who.append(label)
    mine = HERE / "upgrades" / f"{MODEL}-run1.jsonl"
    recs = add(mine, SIX)
    out = [f"Index built {store.built_at()}; DepTime's code at this commit.", ""]
    if recs is None:
        out.append(f"`{mine.relative_to(ALONE.parent.parent)}` doesn't answer every upgrade yet.")
        print("\n".join(out))
        return 1
    who.append(SIX)
    for upgrade, urows in by_upgrade.items():
        called = any(c["tool"] == "check_upgrade" for c in recs[upgrade].get("tool_calls", []))
        for r in urows:
            r["check_upgrade"] = "called `check_upgrade`" if called else "didn't call it"
    out += ["## The comparison", "", "Abstentions count as not flagged.", ""]
    out += up_grade.headline(rows, who, abstain_as_no=True)
    out += ["", *up_grade.per_upgrade(rows, who), ""]
    out += ["## By whether the model called `check_upgrade` in the upgrade", ""]
    out += [*up_grade.split(rows, [NOW, SIX], "check_upgrade"), ""]
    out += ["## Tool use", "", *wt.usage(mine), ""]
    out += ["## The upgrade grader's tables", "", wt.grader_tables(up_grade, HERE / "upgrades")]
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
