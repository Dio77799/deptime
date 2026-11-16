"""Score `deptime check-upgrade --base` on DT-QA-22's update pull requests, by the rules in README.md here.

    # the scored run, once: each pull request as a two-commit git repository, the check run as the Action runs it
    uv run python bench/upgrade-check/prs/check_prs.py run <work dir> --json <rows.json>
    # the audit's environments: every break reported, in the shape DepTime asked about it
    uv run python bench/upgrade-check/prs/check_prs.py audit-envs <rows.json> <work dir>
    # (bench/holdout/probe.py on them: .github/workflows/holdout.yml with SET=bench/upgrade-check/prs/audit)
    uv run python bench/upgrade-check/prs/check_prs.py score <rows.json> <probe out dir> --out <results.md>

<work dir> is find_prs.py's: sources/<owner>__<repo>@<sha>/ holds each commit's files (tarballs, read as data);
repos/<id>/ is built here. Nothing here imports or runs a project's or a package's code: the check reads them, and
the probe runs only on a GitHub runner.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
UPGRADE_CHECK = HERE.parent
HOLDOUT = UPGRADE_CHECK.parent / "holdout"
for p in (HOLDOUT, UPGRADE_CHECK, UPGRADE_CHECK / "audit"):
    sys.path.insert(0, str(p))

import envs  # noqa: E402  (the holdout's environments: Pythons and date cutoffs)
from audit import CALL_KINDS as HAND_KINDS  # noqa: E402  (DT-QA-25's verdict rules, unchanged)
from audit import load_probe, probe_verdict, shapes  # noqa: E402
from run import flagged, read_paths  # noqa: E402  (DT-QA-21's matching rule)
from score import ask_check_symbols, rate  # noqa: E402

from deptime.config import Settings, load_coverage  # noqa: E402
from deptime.index.location import open_index  # noqa: E402
from deptime.models import UpgradeCheckResult  # noqa: E402
from deptime.query import DepTime  # noqa: E402
from deptime.upgrade import project_files, read_code  # noqa: E402

AUDIT = HERE / "audit"
BAR = {"read_updates": 0.90, "recall": 0.90, "fpr": 0.01, "unjustified": 0.05, "read": 0.95}
MIN_BREAKS = 20  # README.md: breaks found gets a verdict only with at least this many breaking uses
_GIT = ["git", "-c", "user.name=qa22", "-c", "user.email=qa22@invalid", "-c", "commit.gpgsign=false"]


def _dt() -> DepTime:
    settings = Settings.from_env()
    store = open_index(settings.index_path)
    if store is None:
        raise SystemExit("no index; run `deptime index pull` first")
    return DepTime(store, load_coverage(settings.coverage_file), settings.index_path)


def _rows() -> list[dict]:
    return [
        json.loads(x) for x in (HERE / "upgrades.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()
    ]


def _slug(row: dict) -> str:
    return row["repo"].removeprefix("https://github.com/").replace("/", "__")


def _fill(repo: Path, src: Path) -> None:
    for entry in repo.iterdir():
        if entry.name != ".git":
            shutil.rmtree(entry) if entry.is_dir() else entry.unlink()
    shutil.copytree(src, repo, dirs_exist_ok=True)


def build_repo(work: Path, row: dict) -> Path:
    """A git repository whose HEAD^ holds the base commit's files and HEAD the head's, as the Action sees them."""
    repo = work / "repos" / row["id"]
    shutil.rmtree(repo, ignore_errors=True)
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    for sha, msg in ((row["base_commit"], "base"), (row["commit"], "head")):
        _fill(repo, work / "sources" / f"{_slug(row)}@{sha}")
        subprocess.run([*_GIT, "-C", str(repo), "add", "-A"], check=True)
        subprocess.run([*_GIT, "-C", str(repo), "commit", "-q", "--allow-empty", "-m", msg], check=True)
    return repo


def project(work: Path, row: dict) -> Path:
    repo = work / "repos" / row["id"]
    return repo / row["dir"] if row["dir"] else repo


def run_check(path: Path) -> tuple[int, str, str]:
    exe = shutil.which("deptime")
    if exe is None:
        raise SystemExit("deptime isn't on PATH; run this with `uv run`")
    env = {**os.environ, "DEPTIME_OFFLINE": "1"}
    p = subprocess.run(
        [exe, "check-upgrade", ".", "--base", "HEAD^", "--format", "json"],
        cwd=path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return p.returncode, p.stdout, p.stderr


# --------------------------------------------------------------------------------------------------------------- run
def parse_result(out: str) -> UpgradeCheckResult:
    """The CLI's JSON (written with `exclude_none`), with the version fields it leaves out restored as None: a package
    added or removed has no `from_version` or `to_version`."""
    doc = json.loads(out)
    changes = (
        [c["change"] for c in doc.get("checked", [])] + doc.get("not_covered", []) + doc.get("skipped", [])
    )
    for c in changes:
        c.setdefault("from_version", None)
        c.setdefault("to_version", None)
    return UpgradeCheckResult.model_validate(doc)


def cmd_run(a: argparse.Namespace) -> int:
    dt = _dt()
    labels = {
        lab["id"]: lab
        for lab in map(json.loads, (HERE / "labels.jsonl").read_text(encoding="utf-8").splitlines())
    }
    uses: list[dict] = []
    prs: list[dict] = []
    for row in _rows():
        build_repo(a.work, row)
        path = project(a.work, row)
        if not path.is_dir():
            code, out, err = 2, "", f"no directory {row['dir']!r} at the head"
        else:
            code, out, err = run_check(path)
        result = parse_result(out) if code in (0, 1) and out.strip() else None
        checked = result.checked if result else []
        titled = next((c for c in checked if c.change.package == row["package"]), None)
        update_read = bool(
            titled and titled.change.from_version == row["from"] and titled.change.to_version == row["to"]
        )
        lab = labels.get(row["id"], {"items": []})
        items = [i for i in lab["items"] if i["label"] in ("works", "breaks")]
        labelled = {i["path"] for i in lab["items"]}
        files = read_code(path, project_files(path)) if path.is_dir() else {}
        seen = read_paths(dt, row, files) if files else set()
        per_use = ask_check_symbols(dt, row, items) if items else []
        breaks = titled.breaks if (titled and update_read) else []
        deprecated = {n.path for n in titled.notices if n.status == "deprecated"} if titled else set()
        for i, cs in zip(items, per_use, strict=True):
            uses.append(
                {
                    "pr": row["id"],
                    "package": row["package"],
                    "stratum": row["stratum"],
                    "bot": row["bot"],
                    "state": row["state"],
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
        prs.append(
            {
                "pr": row["id"],
                "url": row["url"],
                "package": row["package"],
                "from": row["from"],
                "to": row["to"],
                "stratum": row["stratum"],
                "bot": row["bot"],
                "state": row["state"],
                "manifests": row["manifests"],
                "exit": code,
                "stderr": err.strip()[-500:],
                "update_read": update_read,
                "read_as": (
                    [titled.change.from_version, titled.change.to_version, titled.change.source]
                    if titled
                    else None
                ),
                "changes_read": [
                    [c.change.package, c.change.from_version, c.change.to_version, c.change.source]
                    for c in checked
                ],
                "labelled_break": any(i["label"] == "breaks" for i in items),
                "fails": code == 1,
                "packages": [
                    {
                        "package": c.change.package,
                        "from": c.change.from_version,
                        "to": c.change.to_version,
                        "breaks": [
                            {
                                "path": b.path,
                                "kind": b.kind,
                                "kwarg": b.kwarg,
                                "labelled": c.change.package == row["package"] and b.path in labelled,
                                "explanation": b.explanation,
                                "at": [f"{loc.file}:{loc.line}" for loc in b.locations[:3]],
                            }
                            for b in c.breaks
                        ],
                    }
                    for c in checked
                ],
                "files_read": result.files_read if result else 0,
            }
        )
        print(f"{row['id']}: exit {code}, read {update_read}", file=sys.stderr, flush=True)
    doc = {"index_built_at": dt.store.built_at(), "uses": uses, "prs": prs}
    a.json.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    return 0


# -------------------------------------------------------------------------------------------------------- audit envs
def break_id(pr: str, package: str, b: dict) -> str:
    raw = f"{pr}|{package}|{b['path']}|{b['kind']}|{b.get('kwarg') or ''}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def cmd_audit_envs(a: argparse.Namespace) -> int:
    dt = _dt()
    envs.set_cutoff(HERE)
    rows = {r["id"]: r for r in _rows()}
    doc = json.loads(a.rows.read_text(encoding="utf-8"))
    found: dict[str, dict] = {}
    where: dict[str, list[str]] = {}
    for pr in doc["prs"]:
        if not any(p["breaks"] for p in pr["packages"]):
            continue
        path = project(a.work, rows[pr["pr"]])
        files = read_code(path, project_files(path))
        for p in pr["packages"]:
            if not p["breaks"]:
                continue
            date = envs.exclude_newer(p["package"], p["to"])
            eid = f"{p['package']}=={p['to']}@{date}"
            env = found.setdefault(
                eid,
                {
                    "id": eid,
                    "python": envs.NEW_PYTHONS if date == envs.CUTOFF else envs.OLD_PYTHONS,
                    "exclude_newer": date,
                    "requires": [f"{p['package']}=={p['to']}"],
                    "uses": {},
                },
            )
            for b, use in zip(p["breaks"], shapes(dt, p, files, p["breaks"]), strict=True):
                key = hashlib.sha256(json.dumps(use, sort_keys=True).encode()).hexdigest()[:16]
                env["uses"][key] = {"key": key, **use}
                where[break_id(pr["pr"], p["package"], b)] = [eid, key]
    out = [{**e, "uses": sorted(e["uses"].values(), key=lambda x: x["key"])} for e in found.values()]
    out.sort(key=lambda e: e["id"])
    AUDIT.mkdir(exist_ok=True)
    (AUDIT / "envs.json").write_text(json.dumps({"envs": out}, indent=0) + "\n", encoding="utf-8")
    (AUDIT / "breaks.json").write_text(json.dumps(where, indent=0, sort_keys=True) + "\n", encoding="utf-8")
    (AUDIT / "envs-tracebacks.json").write_text(json.dumps({"envs": []}) + "\n", encoding="utf-8")
    (AUDIT / "selection.json").write_text(json.dumps({"cutoff": envs.CUTOFF}) + "\n", encoding="utf-8")
    print(
        f"audit/envs.json: {len(out)} environments, {sum(len(e['uses']) for e in out)} uses", file=sys.stderr
    )
    return 0


# ------------------------------------------------------------------------------------------------------------- score
def verdicts(doc: dict, probe: Path) -> tuple[dict[str, str], dict[str, list[tuple]], int]:
    """Each failing pull request's verdict, each of its breaks' (break, package, verdict, why, id), and how many of
    the audit's environments didn't install."""
    where = json.loads((AUDIT / "breaks.json").read_text(encoding="utf-8"))
    results, failed = load_probe(probe)
    hand_file = AUDIT / "hand-checks.json"
    hand = {
        o["break"]: o
        for o in (json.loads(hand_file.read_text(encoding="utf-8")) if hand_file.exists() else {}).get(
            "checks", []
        )
    }
    pr_verdict: dict[str, str] = {}
    per_break: dict[str, list[tuple]] = {}
    for pr in doc["prs"]:
        if not pr["fails"]:
            continue
        out = []
        for p in pr["packages"]:
            for b in p["breaks"]:
                bid = break_id(pr["pr"], p["package"], b)
                env_id, key = where[bid]
                r = results.get((env_id, key)) if env_id not in failed else None
                v, why = probe_verdict(b, r)
                if v == "true" and b["kind"] in HAND_KINDS:
                    v, why = "cant_tell", f"probe: {why}; needs the hand check of a call break"
                if (h := hand.get(bid)) is not None and v == "cant_tell":
                    v, why = h["verdict"], f"by hand: {h['evidence']}"
                out.append((b, p["package"], v, why, bid))
        got = {x[2] for x in out}
        pr_verdict[pr["pr"]] = (
            "justified" if "true" in got else ("false" if "false" in got else "undetermined")
        )
        per_break[pr["pr"]] = out
    return pr_verdict, per_break, len(failed)


def _share(x: int, n: int) -> float:
    return x / n if n else 0.0


def measures(prs: list[dict], uses: list[dict], verdict: dict[str, str]) -> dict:
    b = [u for u in uses if u["label"] == "breaks"]
    w = [u for u in uses if u["label"] == "works"]
    unjust = [p for p in prs if p["fails"] and verdict.get(p["pr"]) != "justified"]
    return {
        "read_updates": (sum(p["update_read"] for p in prs), len(prs)),
        "recall": (sum(u["flagged"] for u in b), len(b)),
        "fpr": (sum(u["flagged"] for u in w), len(w)),
        "unjustified": (len(unjust), len(prs)),
        "read": (sum(u["read"] for u in uses), len(uses)),
    }


def report(
    doc: dict, verdict: dict[str, str], per_break: dict[str, list[tuple]], failed_envs: int
) -> list[str]:
    prs, uses = doc["prs"], doc["uses"]
    m = measures(prs, uses, verdict)
    share = {k: _share(*v) for k, v in m.items()}
    met = {
        "read_updates": share["read_updates"] >= BAR["read_updates"],
        "recall": share["recall"] >= BAR["recall"] if m["recall"][1] >= MIN_BREAKS else None,
        "fpr": share["fpr"] <= BAR["fpr"],
        "unjustified": share["unjustified"] <= BAR["unjustified"],
        "read": share["read"] >= BAR["read"],
    }

    def yes(k: str) -> str:
        return "too few to judge" if met[k] is None else ("yes" if met[k] else "no")

    counts = Counter(verdict.values())
    out = [
        f"Index built {doc['index_built_at']}. {len(prs)} pull requests, {len(uses)} labelled uses.",
        "",
        "## The bar",
        "",
        "| measure | bar | result | met |",
        "|---|---|---|---|",
        f"| 1. updates read | ≥ 90% | {rate(*m['read_updates'])} | {yes('read_updates')} |",
        f"| 2. breaks found | ≥ 90% | {rate(*m['recall'])} | {yes('recall')} |",
        f"| 3. working uses flagged | ≤ 1% | {rate(*m['fpr'])} | {yes('fpr')} |",
        f"| 4. pull requests failed with no confirmed break | ≤ 5% | {rate(*m['unjustified'])} | {yes('unjustified')} |",
        f"| 5. labelled uses read | ≥ 95% | {rate(*m['read'])} | {yes('read')} |",
        "",
        f"Of {sum(p['fails'] for p in prs)} pull requests the check fails: {counts['justified']} justified,"
        f" {counts['false']} false, {counts['undetermined']} undetermined (lower bound for measure 4, false only:"
        f" {rate(counts['false'], len(prs))}). Audit environments that didn't install: {failed_envs}."
        f" Pull requests where the check stopped with an error: {sum(p['exit'] not in (0, 1) for p in prs)}.",
        "",
        "## Splits",
        "",
        "| | pull requests | updates read | breaks found | working uses flagged | failed, no confirmed break |"
        " labelled uses read |",
        "|---|---|---|---|---|---|---|",
    ]
    groups: list[tuple[str, str, str]] = [("all", "", "")]
    groups += [(f"stratum: {s}", "stratum", s) for s in ("major", "other")]
    groups += [(f"bot: {s}", "bot", s) for s in ("dependabot", "renovate")]
    groups += [(f"state: {s}", "state", s) for s in ("open", "merged", "closed")]
    for label, key, val in groups:
        ps = [p for p in prs if not key or p[key] == val]
        us = [u for u in uses if not key or u[key] == val]
        g = measures(ps, us, verdict)
        out.append(
            f"| {label} | {len(ps)} | {rate(*g['read_updates'])} | {rate(*g['recall'])} | {rate(*g['fpr'])} |"
            f" {rate(*g['unjustified'])} | {rate(*g['read'])} |"
        )

    read_prs = {p["pr"] for p in prs if p["update_read"]}
    b_read = [u for u in uses if u["label"] == "breaks" and u["pr"] in read_prs]
    with_break = [p for p in prs if p["labelled_break"]]
    bu = [u for u in uses if u["label"] == "breaks"]
    wu = [u for u in uses if u["label"] == "works"]
    out += [
        "",
        "## Beside the bar",
        "",
        f"- Breaks found among pull requests whose update was read: {rate(sum(u['flagged'] for u in b_read), len(b_read))}.",
        f"- Pull requests with a labelled break that the check fails: {rate(sum(p['fails'] for p in with_break), len(with_break))}.",
        f"- `check_symbols` asked about each labelled use directly: breaks found"
        f" {rate(sum(u['per_use_flagged'] for u in bu), len(bu))}, working uses flagged"
        f" {rate(sum(u['per_use_flagged'] for u in wu), len(wu))}.",
    ]
    dep = [u for u in wu if u["label_deprecated"]]
    listed = [u for u in wu if u["listed_deprecated"]]
    out.append(
        f"- Deprecations: working uses the probe found deprecated at `to` that the check lists:"
        f" {rate(sum(u['listed_deprecated'] for u in dep), len(dep))}; working uses the check lists as deprecated"
        f" that the probe agrees on: {rate(sum(u['label_deprecated'] for u in listed), len(listed))}."
    )
    g: dict[str, list[dict]] = defaultdict(list)
    for u in bu:
        g[u["change"] or "other"].append(u)
    out += ["", "**Breaks found by change type:**", "", "| change | breaks found |", "|---|---|"]
    out += [f"| {k} | {rate(sum(u['flagged'] for u in v), len(v))} |" for k, v in sorted(g.items())]

    out += ["", "## Updates not read", ""]
    for p in prs:
        if not p["update_read"]:
            out.append(
                f"- `{p['pr']}` ({p['package']} {p['from']} → {p['to']}): changed {', '.join(p['manifests'])};"
                f" read as {p['read_as'] or 'nothing for this package'}"
                + (f"; exit {p['exit']}: {p['stderr'][-200:]}" if p["exit"] not in (0, 1) else "")
            )

    merged_broken = [p for p in prs if p["state"] == "merged" and verdict.get(p["pr"]) == "justified"]
    out += ["", f"## Merged pull requests the check fails with a confirmed break ({len(merged_broken)})", ""]
    out += [f"- `{p['pr']}` {p['url']}" for p in merged_broken]

    misses = [u for u in bu if not u["flagged"]]
    false = [u for u in wu if u["flagged"]]
    out += ["", "## Breaks not found", ""]
    out += [
        f"- `{u['pr']}`: `{u['path']}` ({u['kind']}, {u['change']}){'' if u['read'] else ', not read'}"
        f"{', per-use check flags it' if u['per_use_flagged'] else ''}"
        for u in misses
    ]
    out += ["", "## Working uses flagged", ""]
    out += [f"- `{u['pr']}`: `{u['path']}` ({u['kind']})" for u in false]
    out += ["", "## Every pull request the check fails", ""]
    for p in prs:
        if not p["fails"]:
            continue
        out.append(
            f"- **{verdict[p['pr']]}** `{p['pr']}` ({p['package']} {p['from']} → {p['to']}, {p['state']}) {p['url']}"
        )
        for b, pkg, v, why, bid in per_break[p["pr"]]:
            lab = " (labelled)" if b["labelled"] else ""
            out.append(f"  - {v}: {pkg} `{b['path']}` {b['kind']} {b.get('kwarg') or ''}{lab} [{bid}]: {why}")
    return out


def cmd_score(a: argparse.Namespace) -> int:
    doc = json.loads(a.rows.read_text(encoding="utf-8"))
    verdict, per_break, failed_envs = verdicts(doc, a.probe)
    a.out.write_text("\n".join(report(doc, verdict, per_break, failed_envs)) + "\n", encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("work", type=Path)
    r.add_argument("--json", type=Path, required=True)
    e = sub.add_parser("audit-envs")
    e.add_argument("rows", type=Path)
    e.add_argument("work", type=Path)
    s = sub.add_parser("score")
    s.add_argument("rows", type=Path)
    s.add_argument("probe", type=Path)
    s.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    return {"run": cmd_run, "audit-envs": cmd_audit_envs, "score": cmd_score}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
