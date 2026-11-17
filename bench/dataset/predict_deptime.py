"""DepTime's own answers to the benchmark (DT-OSS-14), in the prediction format of README.md.

  uv run deptime index pull --verify
  uv run python bench/dataset/predict_deptime.py <out>

Writes <out>/predictions/deptime-<version>.uses.jsonl and .tracebacks.jsonl, and their entries in about.json. Uses are
asked of `check_symbols` exactly as bench/holdout/score.py asks them (all of an upgrade's uses in one call; `unknown`
and `not_indexed` are abstentions), and tracebacks of `explain_error` with the installed versions, as deptime.bench does.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "holdout"))
from score import ask_check_symbols  # noqa: E402

from deptime import __version__  # noqa: E402
from deptime.config import Settings, load_coverage  # noqa: E402
from deptime.index.location import open_index  # noqa: E402
from deptime.query import DepTime  # noqa: E402


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def _item(rec: dict) -> dict:
    """A use in the shape the holdout scorer asks it."""
    use = rec["use"]
    item = {"kind": use["kind"], "path": use["path"]}
    if use["kind"] == "call":
        item["npos"], item["kwargs"] = use["positional"], use["keywords"]
    return item


def predict_uses(dt: DepTime, uses: list[dict]) -> list[dict]:
    by_upgrade: dict[str, list[dict]] = defaultdict(list)
    for rec in uses:
        by_upgrade[rec["upgrade"]].append(rec)
    out = []
    for recs in by_upgrade.values():
        row = {"package": recs[0]["package"], "to": recs[0]["to"]}
        for rec, said in zip(recs, ask_check_symbols(dt, row, [_item(r) for r in recs]), strict=True):
            out.append({"id": rec["id"], "breaks": said["flagged"] if said["answered"] else None})
    return out


def predict_tracebacks(dt: DepTime, cases: list[dict]) -> list[dict]:
    out = []
    for c in cases:
        res = dt.explain_error(c["traceback"], c.get("installed") or None)
        out.append(
            {
                "id": c["id"],
                "findings": [
                    {
                        "package": f.package,
                        "symbol": f.symbol,
                        "defined_at": f.defined_at,
                        "issue": f.issue,
                        "last_version_with": f.last_version_with,
                        "first_version_with": f.first_version_with,
                        "replacements": [r.target for r in f.replacements[:3]],
                    }
                    for f in res.findings
                ],
            }
        )
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path, help="the bundle's directory (build.py)")
    a = ap.parse_args(argv)
    settings = Settings.from_env()
    store = open_index(settings.index_path)
    if store is None:
        print(f"no index at {settings.index_path}; run `deptime index pull` first", file=sys.stderr)
        return 2
    dt = DepTime(store, load_coverage(settings.coverage_file), settings.index_path)
    preds = a.out / "predictions"
    preds.mkdir(exist_ok=True)
    stem = f"deptime-{__version__}"
    for task, fn in (("uses", predict_uses), ("tracebacks", predict_tracebacks)):
        rows = fn(dt, _jsonl(a.out / f"{task}.jsonl"))
        (preds / f"{stem}.{task}.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
        )
    about_path = preds / "about.json"
    about = json.loads(about_path.read_text(encoding="utf-8")) if about_path.exists() else {}
    built = store.built_at()
    about[f"{stem}.uses.jsonl"] = {
        "what": f"DepTime {__version__}'s `check_symbols` at each use's `to` release, offline, from the index built"
        f" {built}. In-sample: DepTime's fixes were designed from these collections' misses after their first runs.",
    }
    about[f"{stem}.tracebacks.jsonl"] = {
        "what": f"DepTime {__version__}'s `explain_error` with the installed versions, from the index built {built}."
        " In-sample, as above: `dev` is what DepTime was built on, and each holdout set's misses were fixed after"
        " its first run.",
    }
    about_path.write_text(json.dumps(about, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(preds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
