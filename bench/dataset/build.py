"""Build the public API-change benchmark (DT-OSS-14) from the sets committed in this repository.

  uv run python bench/dataset/build.py <out>            uses.jsonl, tracebacks.jsonl, README.md, score.py, LICENSE
  uv run python bench/dataset/predict_deptime.py <out>  <out>/predictions/deptime-<version>.*.jsonl (needs the index)
  uv run python bench/dataset/predict_models.py <out>   <out>/predictions/<model>.uses.jsonl (DT-QA-18's answers)
  uv run python bench/dataset/build.py <out> --pack     results.md, then <out>.tar.gz and <out>.tar.gz.sha256

The data reads only committed files, so one commit always builds the same data; `--pack` gives the same tarball for the
same files. What each field means is in README.md, which
is also the dataset's own README.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

from packaging.version import Version

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent
REPO = BENCH.parent
sys.path.insert(0, str(BENCH / "holdout"))
from envs import use_key  # noqa: E402

NAME = "deptime-api-change-benchmark"
VERSION = "1"
# The use sets in the order they were collected; the name is the directory's, so an id leads back to it.
USE_SETS = [
    *sorted(p for p in (BENCH / "holdout").glob("2026-11*") if p.is_dir()),
    BENCH / "upgrade-check" / "prs",
]
SOURCES = {"pinned": "pinned", "tmb": "timemachine-bench", "pr": "pull-request"}
SCORED = ("works", "breaks")


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def _collection(path: Path) -> str:
    return path.name


def uses() -> list[dict]:
    """One record per labelled use (`works` or `breaks`); the probe's `excluded` uses are left out."""
    out = []
    for root in USE_SETS:
        name = _collection(root)
        rows = {r["id"]: r for r in _jsonl(root / "upgrades.jsonl")}
        for lab in _jsonl(root / "labels.jsonl"):
            row = rows[lab["id"]]
            where = {use_key(u): u["where"] for u in row["uses"]}
            for item in lab["items"]:
                if item["label"] not in SCORED:
                    continue
                use = {"kind": item["kind"], "path": item["path"]}
                if item["kind"] == "call":
                    use["positional"] = item.get("npos") or 0
                    use["keywords"] = list(item.get("kwargs", []))
                if item.get("via") == "instance":
                    use["via"] = "instance"
                rec = {
                    "id": f"{name}/{row['id']}/{item['key']}",
                    "collection": name,
                    "upgrade": f"{name}/{row['id']}",
                    "package": row["package"],
                    "from": row["from"],
                    "to": row["to"],
                    "direction": "down" if Version(row["to"]) < Version(row["from"]) else "up",
                    "python": row["python"],
                    "use": use,
                    "source": SOURCES[row["source"]],
                    "repo": row["repo"],
                    "commit": row["commit"],
                    "where": where[item["key"]],
                }
                if row.get("url"):
                    rec["pull_request"] = row["url"]
                if row.get("stratum") == "exercise":
                    rec["exercise"] = True
                rec["label"] = item["label"]
                if item["label"] == "breaks":
                    rec["change"] = item["change"]
                    rec["detail"] = item.get("detail", "")
                else:
                    rec["deprecated"] = bool(item.get("deprecated"))
                out.append(rec)
    ids = [r["id"] for r in out]
    assert len(ids) == len(set(ids)), "duplicate use id"
    return out


def tracebacks() -> list[dict]:
    """The six holdout sets' tracebacks (`holdout`), the rest of bench/cases that came from a real report (`dev`), and
    the false-blame set's tracebacks with another cause (`not-api-change`)."""
    out = []
    held: set[str] = set()
    for root in USE_SETS:
        tb = root / "tracebacks.jsonl"
        if not tb.exists():
            continue
        for c in _jsonl(tb):
            held.add(c["id"])
            out.append(_traceback(c, "holdout", _collection(root)))
    for f in sorted((BENCH / "cases").glob("*.jsonl")):
        for c in _jsonl(f):
            if c["id"] in held or c.get("source") == "constructed":
                continue
            out.append(_traceback(c, "dev", "cases"))
    for c in _jsonl(BENCH / "false-blame" / "cases.jsonl"):
        out.append(
            {
                "id": c["id"],
                "split": "not-api-change",
                "collection": "false-blame",
                "source": c["source"],
                "installed": c["installed"],
                "traceback": c["traceback"],
                "expected": None,
                "package": c["package"],
                "cause": c["cause"],
                "evidence": c["evidence"],
            }
        )
    ids = [r["id"] for r in out]
    assert len(ids) == len(set(ids)), "duplicate traceback id"
    return out


def _traceback(c: dict, split: str, collection: str) -> dict:
    rec = {
        "id": c["id"],
        "split": split,
        "collection": collection,
        "source": c["source"],
        "installed": c.get("installed") or {},
        "traceback": c["traceback"],
        "expected": c["expected"],
        "evidence": c["evidence"],
    }
    if "check" in c:
        rec["check"] = c["check"]
    return rec


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def build(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    _write_jsonl(out / "uses.jsonl", uses())
    _write_jsonl(out / "tracebacks.jsonl", tracebacks())
    shutil.copyfile(HERE / "README.md", out / "README.md")
    shutil.copyfile(HERE / "score.py", out / "score.py")
    shutil.copyfile(REPO / "LICENSE", out / "LICENSE")


def results(out: Path) -> str:
    """Every prediction file in <out>/predictions, scored by the bundle's own score.py."""
    lines = [
        "# Reference results",
        "",
        "Each file in `predictions/`, scored by `score.py` (`python score.py --uses ... --tracebacks ...`). A file",
        "that answers one collection only is scored on that collection (`--collection`). See README.md for what each",
        "baseline is and which of its numbers are in-sample.",
    ]
    preds = sorted((out / "predictions").glob("*.jsonl"))
    for p in preds:
        task = "uses" if p.name.endswith(".uses.jsonl") else "tracebacks"
        args = [sys.executable, "-I", str(out / "score.py"), "--data", str(out), f"--{task}", str(p)]
        meta = json.loads((out / "predictions" / "about.json").read_text(encoding="utf-8")).get(p.name, {})
        if meta.get("collection"):
            args += ["--collection", meta["collection"]]
        report = subprocess.run(args, check=True, capture_output=True, text=True).stdout
        lines += ["", f"## `predictions/{p.name}`", "", meta.get("what", ""), "", report.rstrip()]
    return "\n".join(lines) + "\n"


def pack(out: Path) -> Path:
    """<out>.tar.gz with fixed times and owners, so the same files give the same bytes, and its sha256."""
    (out / "results.md").write_text(results(out), encoding="utf-8")
    tar_path = out.parent / f"{out.name}.tar.gz"
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for f in sorted(p for p in out.rglob("*") if p.is_file()):
            info = tarfile.TarInfo(f"{out.name}/{f.relative_to(out).as_posix()}")
            data = f.read_bytes()
            info.size, info.mtime, info.mode = len(data), 0, 0o644
            tar.addfile(info, io.BytesIO(data))
    with tar_path.open("wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename="") as gz:
        gz.write(buf.getvalue())
    digest = hashlib.sha256(tar_path.read_bytes()).hexdigest()
    (out.parent / f"{tar_path.name}.sha256").write_text(f"{digest}  {tar_path.name}\n", encoding="utf-8")
    return tar_path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path, help=f"the bundle's directory, e.g. dist/{NAME}-v{VERSION}")
    ap.add_argument("--pack", action="store_true", help="score predictions/ and write the tarball")
    a = ap.parse_args(argv)
    if a.pack:
        print(pack(a.out))
    else:
        build(a.out)
        print(a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
