"""After the results, not part of the protocol (DT-QA-18): each break's own release against the training cutoff.

  uv run python bench/model-alone/upgrades/posthoc.py >> bench/model-alone/upgrades/results-<date>.md

The split fixed in advance dates the newer of an upgrade's two releases. A break can be older than that release: code
moving from 1.2 to 1.9 breaks on a name 1.4 removed. This finds the release that made each break, from the index,
with `check_symbols` (the holdout scorer's reading of its answer): upgrading, the first release after `from` whose
answer flags the use; going down, the first release after `to` whose answer doesn't (the one that added it). A break
whose answer at `to` isn't a flag, or with no such release, is left undated. It writes breaking-releases.json and
prints one table.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

from cases import load_upgrades
from grade import AFTER_CUTOFF, load_answers, load_rows, rate
from packaging.version import Version

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "holdout"))
from score import ask_check_symbols

from deptime.config import Settings, load_coverage
from deptime.index.location import open_index
from deptime.query import DepTime

HERE = Path(__file__).parent


def flagged(dt: DepTime, package: str, version: str, item: dict) -> bool | None:
    answer = ask_check_symbols(dt, {"package": package, "to": version}, [item])[0]
    return answer["flagged"] if answer["answered"] else None


def main() -> int:
    settings = Settings.from_env()
    store = open_index(settings.index_path)
    dt = DepTime(store, load_coverage(settings.coverage_file), settings.index_path)
    out = {}
    for up in load_upgrades():
        releases = [r for r in store.releases(up["package"]) if not Version(r["version"]).is_prerelease]
        lo, hi = sorted((Version(up["from"]), Version(up["to"])))
        between = [r for r in releases if lo < Version(r["version"]) <= hi]  # oldest first
        for item in up["items"]:
            if item["label"] != "breaks":
                continue
            key = f"{up['id']}|{item['key']}"
            if flagged(dt, up["package"], up["to"], item) is not True:
                out[key] = None
                continue
            want = (
                up["direction"] != "down"
            )  # upgrading: the first flag; going down: the first release without one
            found = next((r for r in between if flagged(dt, up["package"], r["version"], item) is want), None)
            out[key] = found and {"version": found["version"], "released": (found["released_at"] or "")[:10]}
    (HERE / "breaking-releases.json").write_text(
        json.dumps(out, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )

    every = load_rows(json.loads((HERE / "released.json").read_text(encoding="utf-8")))
    models, _ = load_answers(every)  # every use, so each reply is read against all its numbers
    rows = [r for r in every if r["label"] == "breaks"]
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        made = out.get(f"{r['upgrade']}|{r['key']}")
        group = (
            "undated"
            if not made or not made["released"]
            else (
                "from 2026-07-01 (after the cutoff)" if made["released"] >= AFTER_CUTOFF else "by 2026-06-30"
            )
        )
        groups[group].append(r)
    who = [n for n in rows[0]["answers"] if n.startswith("DepTime")] + models
    print("\n### After the results: the release that made each break\n")
    print(
        "Not fixed in advance. The split above dates the newer of an upgrade's two releases; this dates the release"
        " that made the break, found with the index (`posthoc.py`, `breaking-releases.json`). Breaks found:\n"
    )
    print("| breaking release | breaks | " + " | ".join(who) + " |")
    print("|---|---|" + "---|" * len(who))
    for group, g in sorted(groups.items()):
        cells = [rate(sum(bool(r["answers"].get(n)) for r in g), len(g)) for n in who]
        print(f"| {group} | {len(g)} | " + " | ".join(cells) + " |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
