"""Audit the clean upgrades `check-upgrade` fails (DT-QA-25), by the rules in README.md here.

    # 1. the probe's environments: each break reported on a clean upgrade, in the shape DepTime asked about
    uv run python bench/upgrade-check/audit/audit.py envs <rows.json> <sources dir> --out bench/upgrade-check/audit/
    # 2. run bench/holdout/probe.py on them (.github/workflows/holdout.yml with SET=bench/upgrade-check/audit)
    # 3. score
    uv run python bench/upgrade-check/audit/audit.py score <rows.json> <probe out dir> --out <results.md>

<rows.json> is `run.py --json`'s output for DT-QA-24. Nothing here imports or runs a project's or a package's code: the
probe does that, sandboxed, on a GitHub runner.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
HOLDOUT = HERE.parent.parent / "holdout"
sys.path.insert(0, str(HOLDOUT))
sys.path.insert(0, str(HERE.parent))

from score import rate  # noqa: E402

from deptime.config import Settings, load_coverage  # noqa: E402
from deptime.index.location import open_index  # noqa: E402
from deptime.query import DepTime  # noqa: E402
from deptime.upgrade import _Read, project_files, read_code, uses_in  # noqa: E402

BAR = 0.05  # README.md: clean upgrades whose failure no confirmed break justifies, at most
CALL_KINDS = {
    "rejected_kwarg",
    "too_many_positional",
    "missing_args",
}  # confirmed by hand, as the holdout does


def slug(repo: str) -> str:
    return repo.removeprefix("https://github.com/").replace("/", "__")


def break_id(upgrade: str, b: dict) -> str:
    return hashlib.sha256(f"{upgrade}|{b['path']}|{b['kind']}|{b.get('kwarg') or ''}".encode()).hexdigest()[
        :16
    ]


def clean_failures(rows: dict) -> list[dict]:
    return [u for u in rows["upgrades"] if u["clean"] and u["fails"]]


def _set_rows(name: str) -> dict[str, dict]:
    lines = (HOLDOUT / name / "upgrades.jsonl").read_text(encoding="utf-8").splitlines()
    return {r["id"]: r for r in map(json.loads, lines)}


def _env_spec(name: str, row: dict) -> dict:
    """The holdout's own environment for the package at `to` (`<set>/envs.json`): same Pythons and date cutoff."""
    prefix = f"{row['package']}=={row['to']}@"
    envs = json.loads((HOLDOUT / name / "envs.json").read_text(encoding="utf-8"))["envs"]
    (env,) = [e for e in envs if e["id"].startswith(prefix)]
    return {k: env[k] for k in ("id", "python", "exclude_newer", "requires")}


def shapes(dt: DepTime, row: dict, code: dict[str, str], breaks: list[dict]) -> list[dict]:
    """Each break's use as DepTime asked about it: its path, and for a call the most arguments by position and the
    keywords the project's calls pass (`_code_queries`), and whether it was read off an object a call built."""
    spec = dt._spec(row["package"])
    read = _Read()
    for text in code.values():
        if (found := uses_in(text, tuple(spec.import_names))) is not None:
            read.merge("", found)
    queries = {q.path: q for q in dt._code_queries(spec.name, row["to"], [], read.uses)[0]}
    out = []
    for b in breaks:
        q = queries[b["path"]]
        use: dict = {"path": b["path"], "kind": "name"}
        if b["kind"] in CALL_KINDS or b["kind"] == "raises":
            use.update(kind="call", npos=q.positional or 0, kwargs=list(q.kwargs))
        if b["path"] not in read.uses.paths:
            use["via"] = "instance"
        out.append(use)
    return out


def cmd_envs(a: argparse.Namespace) -> int:
    rows = json.loads(a.rows.read_text(encoding="utf-8"))
    settings = Settings.from_env()
    store = open_index(settings.index_path)
    if store is None:
        print("no index; run `deptime index pull` first", file=sys.stderr)
        return 2
    dt = DepTime(store, load_coverage(settings.coverage_file), settings.index_path)
    envs: dict[str, dict] = {}
    where: dict[str, list[str]] = {}  # break id -> [env id, use key]
    for u in clean_failures(rows):
        row = _set_rows(u["set"])[u["upgrade"]]
        src = a.sources / f"{slug(row['repo'])}@{row['commit']}"
        code = read_code(src, project_files(src))
        spec = _env_spec(u["set"], row)
        env = envs.setdefault(spec["id"], {**spec, "uses": {}})
        for b, use in zip(u["breaks"], shapes(dt, row, code, u["breaks"]), strict=True):
            key = hashlib.sha256(json.dumps(use, sort_keys=True).encode()).hexdigest()[:16]
            env["uses"][key] = {"key": key, **use}
            where[break_id(u["upgrade"], b)] = [spec["id"], key]
    out = [{**e, "uses": sorted(e["uses"].values(), key=lambda x: x["key"])} for e in envs.values()]
    out.sort(key=lambda e: e["id"])
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "envs.json").write_text(json.dumps({"envs": out}, indent=0) + "\n", encoding="utf-8")
    (a.out / "breaks.json").write_text(json.dumps(where, indent=0, sort_keys=True) + "\n", encoding="utf-8")
    (a.out / "envs-tracebacks.json").write_text(json.dumps({"envs": []}) + "\n", encoding="utf-8")
    print(f"envs.json: {len(out)} environments, {sum(len(e['uses']) for e in out)} uses", file=sys.stderr)
    return 0


# ----------------------------------------------------------------------------------------------------------- score
def probe_verdict(b: dict, r: dict | None) -> tuple[str, str]:
    """README.md's rule: (true | false | cant_tell, why) from the probe's result for the break's use at `to`."""
    if r is None:
        return "cant_tell", "not probed (the environment didn't install)"
    if r.get("resolved") is None:
        return "cant_tell", f"the import failed: {r.get('error', '')[:120]}"
    if r["resolved"] is False:
        if r.get("set_on_instances"):
            return "false", "set on instances at run time"
        return "true", f"doesn't resolve: {r.get('error', '')[:120]}"
    kind = b["kind"]
    if kind == "missing":
        return "false", "resolves"
    if kind == "raises":
        return ("true", "built to fail") if r.get("raises_when_called") else ("false", "not built to fail")
    if r.get("signature") is None:
        return "cant_tell", f"no signature: {r.get('bind_error', '')[:120]}"
    if kind == "rejected_kwarg":
        how = (r.get("kwargs") or {}).get(b["kwarg"])
        if how == "absent" or how == "named:POSITIONAL_ONLY":
            return "true", f"`{b['kwarg']}` {how} in {r['signature'][:160]}"
        if how == "var_keyword":
            return "cant_tell", f"`{b['kwarg']}` only **kwargs takes"
        return "false", f"`{b['kwarg']}` {how}"
    err = r.get("bind_error") or ""
    if r.get("binds"):
        return "false", "the call shape binds"
    want = "too many positional" if kind == "too_many_positional" else "missing a required"
    return (
        ("true", err[:160]) if want in err else ("cant_tell", f"doesn't bind for another reason: {err[:120]}")
    )


def load_probe(out_dir: Path) -> tuple[dict[tuple[str, str], dict], set[str]]:
    """(env id, use key) -> result; and the environments that didn't install."""
    results: dict[tuple[str, str], dict] = {}
    failed: set[str] = set()
    for f in sorted(out_dir.rglob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            rec = json.loads(line)
            if rec.get("result") != "ok":
                failed.add(rec["id"])
                continue
            for r in rec["results"]:
                results[(rec["id"], r["key"])] = r
    return results, failed


def cmd_score(a: argparse.Namespace) -> int:
    rows = json.loads(a.rows.read_text(encoding="utf-8"))
    where = json.loads((HERE / "breaks.json").read_text(encoding="utf-8"))
    results, failed = load_probe(a.probe)
    hand = {
        o["break"]: o
        for o in json.loads((HERE / "hand-checks.json").read_text(encoding="utf-8")).get("checks", [])
    }
    clean_total = sum(u["clean"] for u in rows["upgrades"])
    verdicts: dict[str, str] = {}
    lines: list[str] = []
    counts: Counter[str] = Counter()
    false_breaks: list[str] = []
    for u in clean_failures(rows):
        out = []
        for b in u["breaks"]:
            bid = break_id(u["upgrade"], b)
            env_id, key = where[bid]
            r = results.get((env_id, key)) if env_id not in failed else None
            verdict, why = probe_verdict(b, r)
            if verdict == "true" and b["kind"] in CALL_KINDS:
                verdict, why = "cant_tell", f"probe: {why}; needs the hand check of a call break"
            if (h := hand.get(bid)) is not None and verdict == "cant_tell":
                verdict, why = h["verdict"], f"by hand: {h['evidence']}"
            out.append((b, verdict, why, bid))
            if verdict == "false":
                false_breaks.append(
                    f"{u['upgrade']}: `{b['path']}` {b['kind']} {b.get('kwarg') or ''} ({why})"
                )
        got = {v for _, v, _, _ in out}
        upgrade_verdict = "justified" if "true" in got else ("false" if "false" in got else "undetermined")
        verdicts[u["upgrade"]] = upgrade_verdict
        counts[upgrade_verdict] += 1
        lines.append(
            f"- **{upgrade_verdict}** {u['set']} `{u['upgrade']}` ({u['package']} {u['from']} → {u['to']}"
            f"{', tmb' if u['direction'] == 'tmb' else ''})"
        )
        for b, v, why, bid in out:
            lines.append(f"  - {v}: `{b['path']}` {b['kind']} {b.get('kwarg') or ''} [{bid}]: {why}")
    unjustified = counts["false"] + counts["undetermined"]
    share = unjustified / clean_total if clean_total else 0.0
    head = [
        "## The bar",
        "",
        "| measure | bar | result | met |",
        "|---|---|---|---|",
        f"| clean upgrades whose failure no confirmed break justifies | ≤ 5% | {rate(unjustified, clean_total)} |"
        f" {'yes' if share <= BAR else 'no'} |",
        "",
        f"Of {sum(counts.values())} clean upgrades the check fails: {counts['justified']} justified,"
        f" {counts['false']} false, {counts['undetermined']} undetermined. Lower bound (false only):"
        f" {rate(counts['false'], clean_total)}. Environments that didn't install: {len(failed)}.",
        "",
        f"## False breaks ({len(false_breaks)})",
        "",
        *[f"- {x}" for x in false_breaks],
        "",
        "## Every clean upgrade the check fails",
        "",
        *lines,
    ]
    a.out.write_text("\n".join(head) + "\n", encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("envs")
    e.add_argument("rows", type=Path)
    e.add_argument("sources", type=Path)
    e.add_argument("--out", type=Path, default=HERE)
    s = sub.add_parser("score")
    s.add_argument("rows", type=Path)
    s.add_argument("probe", type=Path)
    s.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    return cmd_envs(a) if a.cmd == "envs" else cmd_score(a)


if __name__ == "__main__":
    raise SystemExit(main())
