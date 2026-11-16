"""Score DT-QA-05's sessions, by the rules in README.md here ("Scoring a session", "Measures and the bar").

    uv run python bench/agent-fix/score.py envs            # envs.json, uses.json: the probe's work for the fixed trees
    # bench/holdout/probe.py on them: .github/workflows/holdout.yml with SET=bench/agent-fix, on a spike branch
    uv run python bench/agent-fix/score.py hand <probe out dir>     # hand-todo.json: the blinded can't-tells
    uv run python bench/agent-fix/score.py score <probe out dir> --out bench/agent-fix/results-<date>.md

Nothing here asks DepTime about a session, imports or runs a project's or a package's code: uses are read with the
holdout's own reader (`../holdout/uses.py`), and the probe runs only on a GitHub runner. DepTime is asked once per task
(`check-upgrade` on the task's tree) only to report, for arm B, which confirmed breaks it reported.

**Which uses the probe runs.** Every use in a fixed tree that the task's tree doesn't have (README.md), and every use
on a line the agent added that the task's set doesn't label works or breaks. The second only adds ground truth: a fix that moves a
line onto a use the project already makes elsewhere (`client.chat.completions.create`) still gets that use checked.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent
HOLDOUT = BENCH / "holdout"
sys.path.insert(0, str(HOLDOUT))  # before this directory, whose own score.py and run.py are not the holdout's

from envs import use_key  # noqa: E402
from labels import var_keyword_only, works  # noqa: E402  (the rule the labels came from)
from run import WORK  # noqa: E402  (this directory's run.py: the holdout has none)
from score import rate  # noqa: E402  (../holdout/score.py: a share with its 95% Wilson interval)
from uses import Use, uses_in_tree  # noqa: E402

from deptime.config import load_coverage  # noqa: E402

BAR_FIXED = 0.80  # README.md: arm B fixes at least 80% of its sessions
SCORED = ["A1", "A2", "B1", "B2", "C1"]
MANIFEST = re.compile(
    r"(^|/)(.*requirements.*\.txt|.*\.in|pyproject\.toml|setup\.cfg|setup\.py|Pipfile|.*\.lock)$"
)
NO_CODE = re.compile(r"^\s*(#.*|pass|\.\.\.|raise NotImplementedError(\(.*\))?|)\s*$")
STDLIB = set(sys.stdlib_module_names)


def _tasks() -> dict[str, dict]:
    return {t["id"]: t for t in json.loads((HERE / "tasks.json").read_text(encoding="utf-8"))["tasks"]}


def _sessions() -> list[dict]:
    out = []
    for label in SCORED:
        for f in sorted((HERE / "sessions" / label).glob("*.json")):
            s = json.loads(f.read_text(encoding="utf-8"))
            s["diff"] = (HERE / "diffs" / label / f"{s['task']}.diff").read_text(encoding="utf-8")
            out.append(s)
    return out


def _import_names(package: str) -> tuple[str, ...]:
    from packaging.utils import canonicalize_name

    for p in load_coverage().packages:
        if canonicalize_name(p.name) == canonicalize_name(package):
            return tuple(p.import_names)
    raise KeyError(package)


def _set_dir(t: dict) -> Path:
    return BENCH / "upgrade-check" / "prs" if t["set"] == "prs" else HOLDOUT / t["set"]


def _labels(t: dict) -> dict[str, str]:
    """use key -> the set's label for this task's uses (works, breaks, excluded)."""
    for line in (_set_dir(t) / "labels.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["id"] == t["id"]:
            return {i["key"]: i["label"] for i in row["items"]}
    return {}


def _env_spec(t: dict) -> dict:
    envs = json.loads((_set_dir(t) / "envs.json").read_text(encoding="utf-8"))["envs"]
    (env,) = [e for e in envs if e["id"] == t["env"]]
    return {k: env[k] for k in ("id", "python", "exclude_newer", "requires")}


def _use_dict(u: Use) -> dict:
    d: dict = {"kind": u.kind, "path": u.path}
    if u.kind == "call":
        d.update(npos=u.npos, kwargs=list(u.kwargs))
    if u.via != "import":
        d["via"] = u.via
    return d


# ------------------------------------------------------------------------------------------------------------ diffs


def parse_diff(text: str) -> dict[str, dict]:
    """file (new path, or old for a deletion) -> {"old": old path, "deleted", "added_file", "blocks"}; each block is a
    run of changed lines: (old line numbers removed, [(new line number, text) added], old line before it)."""
    files: dict[str, dict] = {}
    cur = None
    old_no = new_no = 0
    block = None

    def close():
        nonlocal block
        if cur is not None and block is not None and (block["removed"] or block["added"]):
            cur["blocks"].append(block)
        block = None

    for line in text.splitlines():
        if line.startswith("diff --git "):
            close()
            m = re.match(r"diff --git a/(.*) b/(.*)$", line)
            cur = {"old": m.group(1), "new": m.group(2), "deleted": False, "added_file": False, "blocks": []}
            files[m.group(2)] = cur
            continue
        if cur is None:
            continue
        if line.startswith("deleted file mode"):
            cur["deleted"] = True
        elif line.startswith("new file mode"):
            cur["added_file"] = True
        elif line.startswith("@@"):
            close()
            m = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
            old_no, new_no = int(m.group(1)), int(m.group(3))
            if m.group(2) == "0":
                old_no += 1  # an empty old range is written as the line before it
        elif line.startswith("---") or line.startswith("+++"):
            continue
        elif line.startswith("-"):
            block = block or {"removed": [], "added": [], "at_old": old_no}
            block["removed"].append(old_no)
            old_no += 1
        elif line.startswith("+"):
            block = block or {"removed": [], "added": [], "at_old": old_no}
            block["added"].append((new_no, line[1:]))
            new_no += 1
        elif line.startswith(" ") or line == "":
            close()
            old_no += 1
            new_no += 1
    close()
    return files


def new_line(f: dict | None, old: int) -> int:
    """Where an unchanged old line sits in the new file."""
    shift = 0
    for b in (f or {}).get("blocks", []):
        start = b["removed"][0] if b["removed"] else b["at_old"]
        if start > old:
            break
        shift += len(b["added"]) - len(b["removed"])
    return old + shift


def _rel(t: dict, path: str) -> str | None:
    """A diff path (from the repository's root) as a path under the task's project directory."""
    if not t["dir"]:
        return path
    prefix = t["dir"].rstrip("/") + "/"
    return path[len(prefix) :] if path.startswith(prefix) else None


def added_lines(t: dict, files: dict[str, dict]) -> dict[str, set[int]]:
    out: dict[str, set[int]] = defaultdict(set)
    for path, f in files.items():
        if (rel := _rel(t, path)) is not None and not f["deleted"]:
            for b in f["blocks"]:
                out[rel].update(n for n, _ in b["added"])
    return out


def extra_roots(t: dict, files: dict[str, dict], tree: Path) -> tuple[str, ...]:
    """Modules first imported on an added line: not the standard library, not the project's own."""
    own = {p.stem for p in tree.rglob("*.py")} | {
        p.name for p in tree.rglob("*") if p.is_dir()
    }  # a script's sibling too
    found = set()
    for path, f in files.items():
        if not path.endswith(".py"):
            continue
        for b in f["blocks"]:
            for _, text in b["added"]:
                m = re.match(r"\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", text)
                if m and not text.lstrip().startswith("from ."):
                    top = (m.group(1) or m.group(2)).split(".")[0]
                    if top not in STDLIB and top not in own:
                        found.add(top)
    return tuple(sorted(found))


# --------------------------------------------------------------------------------------------------- reading uses


def session_uses(t: dict, s: dict) -> dict:
    """The task tree's and the fixed tree's uses, read with the package's roots and the session's extra roots."""
    files = parse_diff(s["diff"])
    task_tree = WORK / "tasks" / t["id"] / t["dir"]
    fixed_tree = WORK / "runs" / s["label"] / t["id"] / "repo" / t["dir"]
    roots = _import_names(t["package"])
    extra = tuple(r for r in extra_roots(t, files, fixed_tree) if r not in roots)
    before = {use_key(_use_dict(u)): u for u in uses_in_tree(task_tree, roots + extra)}
    after = {use_key(_use_dict(u)): u for u in uses_in_tree(fixed_tree, roots + extra)}
    return {"files": files, "before": before, "after": after, "extra": extra}


def to_probe(t: dict, s: dict, read: dict, labels: dict[str, str]) -> set[str]:
    """The fixed tree's use keys the probe must run: new ones, and those on added lines the set never labelled."""
    added = added_lines(t, read["files"])
    keys = set(read["after"]) - set(read["before"])
    for k, u in read["after"].items():
        if labels.get(k) in ("works", "breaks"):
            continue
        if any(int(w.rsplit(":", 1)[1]) in added.get(w.rsplit(":", 1)[0], ()) for w in u.where):
            keys.add(k)
    return keys


def cmd_envs(a: argparse.Namespace) -> int:
    tasks = _tasks()
    envs: dict[str, dict] = {}
    for s in _sessions():
        t = tasks[s["task"]]
        read = session_uses(t, s)
        spec = _env_spec(t)
        env = envs.setdefault(spec["id"], {**spec, "uses": {}})
        for k in to_probe(t, s, read, _labels(t)):
            env["uses"][k] = {"key": k, **_use_dict(read["after"][k])}
    out = [{**e, "uses": sorted(e["uses"].values(), key=lambda x: x["key"])} for e in envs.values()]
    out = [e for e in out if e["uses"]]
    out.sort(key=lambda e: e["id"])
    (HERE / "envs.json").write_text(json.dumps({"envs": out}, indent=0) + "\n", encoding="utf-8")
    (HERE / "envs-tracebacks.json").write_text(json.dumps({"envs": []}) + "\n", encoding="utf-8")
    print(f"envs.json: {len(out)} environments, {sum(len(e['uses']) for e in out)} uses", file=sys.stderr)
    return 0


# --------------------------------------------------------------------------------------------------------- verdicts


def load_probe(out_dir: Path) -> tuple[dict[tuple[str, str], dict], set[str]]:
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


SOURCE = "can't tell (source)"  # settled only from the released source (README.md, "Hand checks")


def use_verdict(r: dict | None, use: dict, called: bool, roots: tuple[str, ...]) -> str:
    """works / breaks / can't tell / unlabelled for one use at `to`, by labels.py's rule for `to`. `unlabelled`: a
    use no set ever labels, whatever the probe says (a member of an object a call that isn't a class built, a keyword
    only **kwargs takes, an attribute that may be set on instances); it is left out of a replacement's judgement.

    Two answers need the library's source (SOURCE): a module of another package, which the probe's environment
    doesn't install (it installs the task's package and what that requires), so "No module named" there says nothing
    about the fix; and a call the probe finds doesn't bind, which the holdout's labels count as a break only once the
    source confirms it (pydantic models whose signature shows only their camelCase aliases bind by name)."""
    root = use["path"].split(".")[0]
    if (
        r is not None
        and r.get("resolved") is False
        and root not in roots
        and f"No module named '{root}'" in (r.get("error") or "")
    ):
        return SOURCE
    if r is not None and r.get("resolved") and use.get("via") == "instance" and not r.get("builder_is_class"):
        return "unlabelled"
    ok, why = works(r, use, called)
    if ok is None:
        return "can't tell"
    if ok:
        return "unlabelled" if use["kind"] == "call" and var_keyword_only(r) else "works"
    if use.get("via") == "instance" and why == "removed":
        return "unlabelled"
    if use["kind"] == "call" and why != "removed":
        return SOURCE
    return "breaks"


def _bid(session: str, task: str, key: str) -> str:
    return hashlib.sha256(f"{session}|{task}|{key}".encode()).hexdigest()[:12]


def judge(t: dict, s: dict, probe: dict, hand: dict[str, dict]) -> dict:
    """Every confirmed break's verdict and the session's, by README.md's rules."""
    read = session_uses(t, s)
    labels = _labels(t)
    files, after = read["files"], read["after"]
    by_rel = {r: f for p, f in files.items() if (r := _rel(t, p)) is not None}
    calls = {u.path for u in after.values() if u.kind == "call"}

    roots = _import_names(t["package"])
    use_hand = _use_hand()

    def verdict_of(k: str) -> str:
        u = _use_dict(after[k])
        if labels.get(k) in ("works", "breaks") and k in read["before"]:
            return labels[k]
        if (t["env"], k) in use_hand:
            return use_hand[(t["env"], k)]["verdict"]
        return use_verdict(probe.get((t["env"], k)), u, u["kind"] == "name" and u["path"] in calls, roots)

    def at(rel: str, line: int) -> list[str]:
        return [k for k, u in after.items() if f"{rel}:{line}" in u.where]

    probed = {k: verdict_of(k) for k in to_probe(t, s, read, labels)}
    new_breaks = sorted(after[k].path for k, v in probed.items() if v == "breaks" and k not in read["before"])
    confirmed = {b["key"] for b in t["breaks"]}

    breaks = []
    for b in t["breaks"]:
        bid = _bid(s["label"], t["id"], b["key"])
        if b["key"] in after:
            breaks.append({"key": b["key"], "path": b["path"], "verdict": "still broken", "id": bid})
            continue
        replaced, removed, relevant = False, 0, []
        for w in b["where"]:
            rel, line = w.rsplit(":", 1)
            line = int(line)
            f = by_rel.get(rel)
            if f is not None and f["deleted"]:
                removed += 1
                continue
            blk = next((x for x in (f or {}).get("blocks", []) if line in x["removed"]), None)
            if blk is None:  # the line is unchanged: what it uses now comes from a change elsewhere
                relevant += at(rel, new_line(f, line))
                continue
            code = [n for n, text in blk["added"] if not NO_CODE.match(text)]
            if not code:
                removed += 1
                continue
            replaced = True
            relevant += [k for n in code for k in at(rel, n)]
        relevant = sorted(set(relevant) - confirmed)  # a confirmed break still there is judged on its own
        verdicts = [v for k in relevant if (v := probed.get(k) or verdict_of(k)) != "unlabelled"]
        verdicts = ["can't tell" if v == SOURCE else v for v in verdicts]
        if not replaced and not relevant:
            v = "removed"
        elif "breaks" in verdicts:
            v = "broken by the fix"
        elif verdicts and all(x == "works" for x in verdicts):
            v = "fixed"
        else:
            v = "can't tell"
        if v == "can't tell" and bid in hand:
            v = hand[bid]["verdict"]
        breaks.append(
            {
                "key": b["key"],
                "path": b["path"],
                "verdict": v,
                "id": bid,
                "relevant": [after[k].path for k in relevant],
                "relevant_keys": relevant,
            }
        )

    pinned_away = pinned_elsewhere(t, files)
    pending = sorted(k for k, v in probed.items() if v == SOURCE and k not in read["before"])
    verdicts = Counter(b["verdict"] for b in breaks)
    if (
        verdicts["still broken"]
        or verdicts["removed"]
        or verdicts["broken by the fix"]
        or verdicts["broken"]
        or new_breaks
        or pinned_away
    ):
        session = "not fixed"
    elif all(b["verdict"] == "fixed" for b in breaks) and not pending:
        session = "fixed"
    else:
        session = "can't tell"
    new_break = bool(new_breaks) or verdicts["broken by the fix"] > 0 or verdicts["broken"] > 0
    return {
        "session": session,
        "breaks": breaks,
        "new_breaks": new_breaks,
        "new_break": new_break,
        "pinned_away": pinned_away,
        "unasked": unasked(t, files, breaks, after, set(read["after"]) - set(read["before"])),
        "extra_roots": list(read["extra"]),
        "pending": [(t["env"], k, _use_dict(after[k])) for k in pending]
        + [
            (t["env"], k, _use_dict(after[k]))
            for b in breaks
            if b["verdict"] == "can't tell"
            for k in b.get("relevant_keys", [])
            if verdict_of(k) == SOURCE
        ],
    }


def pinned_elsewhere(t: dict, files: dict[str, dict]) -> list[str]:
    """Added manifest lines that pin the package to anything but `to` (README.md: such a session isn't fixed)."""
    from packaging.utils import canonicalize_name

    name = canonicalize_name(t["package"])
    out = []
    for path, f in files.items():
        if not MANIFEST.search(path):
            continue
        for b in f["blocks"]:
            for _, text in b["added"]:
                m = re.match(
                    r"\s*[\"']?([A-Za-z0-9_.\-]+)(?:\[[^\]]*\])?[\"']?\s*(?:=\s*[\"'])?\s*([\^~<>=!][^;#\"',]*)",
                    text,
                )
                if not m or canonicalize_name(m.group(1)) != name:
                    continue
                ok = _allows(m.group(2).strip().replace(" ", ""), t["to"])
                if not ok:
                    out.append(f"{path}: {text.strip()[:120]}")
    return out


def _allows(spec: str, version: str) -> bool:
    """Whether a pin allows `version`: PEP 440, or Poetry's `^` and `~` (`^0.28.1` is >=0.28.1,<0.29.0)."""
    from packaging.specifiers import InvalidSpecifier, SpecifierSet
    from packaging.version import InvalidVersion, Version

    try:
        if spec[:1] in "^~" and not spec.startswith("~="):
            base = Version(spec[1:])
            rel = [*base.release, 0, 0]
            if spec[0] == "^":
                i = next((n for n, x in enumerate(base.release) if x), len(base.release) - 1)
            else:
                i = 1 if len(base.release) > 1 else 0
            upper = [*rel[:i], rel[i] + 1]
            return base <= Version(version) < Version(".".join(map(str, upper)))
        return version in SpecifierSet(spec)
    except (InvalidSpecifier, InvalidVersion):
        return False


def unasked(t: dict, files: dict[str, dict], breaks: list[dict], after: dict, new_keys: set[str]) -> dict:
    """Changed lines in Python files outside every block that holds a confirmed break's line or a new use."""
    break_lines = defaultdict(set)
    for b in t["breaks"]:
        for w in b["where"]:
            rel, line = w.rsplit(":", 1)
            break_lines[rel].add(int(line))
    new_lines = defaultdict(set)
    for k in new_keys:
        for w in after[k].where:
            rel, line = w.rsplit(":", 1)
            new_lines[rel].add(int(line))
    lines = 0
    where = []
    for path, f in files.items():
        rel = _rel(t, path)
        if rel is None or not path.endswith(".py"):
            continue
        for blk in f["blocks"]:
            hit = set(blk["removed"]) & break_lines[rel] or {n for n, _ in blk["added"]} & new_lines[rel]
            if not hit:
                lines += len(blk["removed"]) + len(blk["added"])
                where.append(f"{rel}:{blk['removed'][0] if blk['removed'] else blk['at_old']}")
    return {"lines": lines, "where": where}


# ------------------------------------------------------------------------------------------------------ hand checks


def cmd_hand(a: argparse.Namespace) -> int:
    """The can't-tells that can change a session's verdict, in a shuffled order, naming neither arm nor run."""
    tasks = _tasks()
    probe, _ = load_probe(a.probe)
    hand = _hand()
    todo = []
    uses: dict[tuple[str, str], dict] = {}
    for s in _sessions():
        t = tasks[s["task"]]
        j = judge(t, s, probe, hand)
        if j["session"] != "can't tell":
            continue  # hand checks stop where they can't change the verdict
        for env, key, use in j["pending"]:  # uses only the released source can settle, each checked once
            uses[(env, key)] = {"env": env, "key": key, "package": t["package"], **use}
        files = parse_diff(s["diff"])
        for b in j["breaks"]:
            if b["verdict"] != "can't tell":
                continue
            (tb,) = [x for x in t["breaks"] if x["key"] == b["key"]]
            hunks = []
            for w in tb["where"]:
                rel, line = w.rsplit(":", 1)
                for p, f in files.items():
                    if _rel(t, p) == rel:
                        for blk in f["blocks"]:
                            if int(line) in blk["removed"]:
                                hunks.append({"at": w, "added": [x for _, x in blk["added"]]})
            todo.append(
                {
                    "id": b["id"],
                    "package": t["package"],
                    "to": t["to"],
                    "break": {
                        k: tb[k]
                        for k in ("path", "kind", "npos", "kwargs", "via", "change", "where")
                        if k in tb
                    },
                    "replacement": hunks,
                    "uses_to_check": b["relevant"],
                }
            )
    random.Random(5).shuffle(todo)
    use_list = sorted(uses.values(), key=lambda u: (u["env"], u["path"], u["key"]))
    doc = {"uses": use_list, "breaks": todo}
    (HERE / "hand-todo.json").write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    print(f"hand-todo.json: {len(use_list)} uses and {len(todo)} breaks to check by hand", file=sys.stderr)
    return 0


def _use_hand() -> dict[tuple[str, str], dict]:
    f = HERE / "hand-checks.json"
    if not f.exists():
        return {}
    return {(c["env"], c["key"]): c for c in json.loads(f.read_text(encoding="utf-8")).get("uses", [])}


def _hand() -> dict[str, dict]:
    f = HERE / "hand-checks.json"
    if not f.exists():
        return {}
    return {c["id"]: c for c in json.loads(f.read_text(encoding="utf-8")).get("checks", [])}


# ------------------------------------------------------------------------------------------------------------ score


def deptime_reports(t: dict) -> list:
    """check-upgrade's breaks on the task's tree, for arm B's column (the only time DepTime is asked here)."""
    tree = WORK / "tasks" / t["id"] / t["dir"]
    cmd = [
        str(Path(sys.executable).with_name("deptime")),
        "check-upgrade",
        str(tree),
        "--package",
        t["package"],
    ]
    cmd += ["--from", t["from"], "--to", t["to"], "--format", "json"]
    out = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, "DEPTIME_OFFLINE": "1"})
    if out.returncode not in (0, 1):
        return []
    doc = json.loads(out.stdout)
    return [SimpleNamespace(**b) for c in doc["checked"] for b in c["breaks"]]


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value for b and c discordant pairs."""
    from math import comb

    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2**n)


def cmd_score(a: argparse.Namespace) -> int:
    import importlib.util

    spec = importlib.util.spec_from_file_location("upgrade_check_run", BENCH / "upgrade-check" / "run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    flagged = mod.flagged  # DT-QA-21's matching rule

    tasks = _tasks()
    probe, failed = load_probe(a.probe)
    hand = _hand()
    rows = []
    for s in _sessions():
        t = tasks[s["task"]]
        rows.append(
            {**{k: s[k] for k in ("task", "arm", "label")}, "s": s, "t": t, **judge(t, s, probe, hand)}
        )
    lines = report(rows, tasks, failed, flagged)
    a.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {a.out}", file=sys.stderr)
    return 0


def report(rows: list[dict], tasks: dict, failed: set[str], flagged) -> list[str]:
    arms = ["A", "B", "C"]
    by_arm = {x: [r for r in rows if r["arm"] == x] for x in arms}

    def fixed(rs):
        return sum(r["session"] == "fixed" for r in rs)

    out = ["# Does an agent fix an update's breaks better with DepTime? Results (DT-QA-05)", ""]
    out += [
        f"Protocol: `README.md` here. Probe environments that didn't install: {sorted(failed) or 'none'}.",
        "",
    ]
    out += [
        "| arm | sessions | 1. sessions fixed | can't tell | 2. sessions with a new break | 3. confirmed breaks fixed |"
    ]
    out += ["|---|---|---|---|---|---|"]
    for x in arms:
        rs = by_arm[x]
        if not rs:
            continue
        nb = sum(len(r["breaks"]) for r in rs)
        fb = sum(b["verdict"] == "fixed" for r in rs for b in r["breaks"])
        out.append(
            f"| {x} | {len(rs)} | {rate(fixed(rs), len(rs))} | {sum(r['session'] == "can't tell" for r in rs)} | "
            f"{rate(sum(r['new_break'] for r in rs), len(rs))} | {rate(fb, nb)} |"
        )
    a_rs, b_rs = by_arm["A"], by_arm["B"]
    if a_rs and b_rs:
        fa, fbx = fixed(a_rs) / len(a_rs), fixed(b_rs) / len(b_rs)
        na, nbx = sum(r["new_break"] for r in a_rs), sum(r["new_break"] for r in b_rs)
        checks = [
            (f"B fixes at least {BAR_FIXED:.0%} of its sessions", fbx >= BAR_FIXED),
            ("B fixes at least as many sessions as A", fixed(b_rs) >= fixed(a_rs)),
            ("B has no more sessions with a new break than A", nbx <= na),
        ]
        out += ["", "**The bar:**", ""]
        out += [f"- {name}: {'met' if ok else 'missed'}" for name, ok in checks]
        out += [
            "",
            f"**Verdict: {'met' if all(ok for _, ok in checks) else 'missed'}** (A {fa:.1%}, B {fbx:.1%}).",
        ]

    out += ["", "## By set", "", "| arm | set | sessions | fixed |", "|---|---|---|---|"]
    for x in arms:
        for st in ("2026-11f", "prs"):
            rs = [r for r in by_arm[x] if r["t"]["set"] == st]
            if rs:
                out.append(f"| {x} | {st} | {len(rs)} | {rate(fixed(rs), len(rs))} |")

    out += ["", "## A and B paired (each task and run)", ""]
    pair = Counter()
    for t in tasks:
        for run in (1, 2):
            ra = next((r for r in rows if r["task"] == t and r["label"] == f"A{run}"), None)
            rb = next((r for r in rows if r["task"] == t and r["label"] == f"B{run}"), None)
            if ra and rb:
                pair[(ra["session"] == "fixed", rb["session"] == "fixed")] += 1
    out.append(
        f"Both fixed {pair[(True, True)]}, B only {pair[(False, True)]}, A only {pair[(True, False)]}, neither "
        f"{pair[(False, False)]}; McNemar's exact p = {mcnemar_exact(pair[(False, True)], pair[(True, False)]):.3f}."
    )
    out += [
        "",
        "Tasks fixed in both runs: "
        + ", ".join(
            f"{x} {sum(all(r['session'] == 'fixed' for r in by_arm[x] if r['task'] == t) and sum(1 for r in by_arm[x] if r['task'] == t) == 2 for t in tasks)}"
            for x in ("A", "B")
        )
        + f" of {len(tasks)}.",
    ]

    out += ["", "## Each task", "", "| task | breaks | DepTime reports | " + " | ".join(SCORED) + " |"]
    out += ["|---|---|---|" + "---|" * len(SCORED)]
    for tid, t in tasks.items():
        reported = deptime_reports(t)
        n_rep = sum(flagged(b, reported) for b in t["breaks"])
        cells = []
        for label in SCORED:
            r = next((r for r in rows if r["task"] == tid and r["label"] == label), None)
            if r is None:
                cells.append("-")
                continue
            c = Counter(b["verdict"] for b in r["breaks"])
            mark = {"fixed": "fixed", "not fixed": "no", "can't tell": "?"}[r["session"]]
            cells.append(f"{mark} ({c['fixed']}/{len(r['breaks'])})")
        out.append(f"| `{tid}` | {len(t['breaks'])} | {n_rep} | " + " | ".join(cells) + " |")

    out += ["", "## Sessions not fixed, and why", ""]
    for r in rows:
        if r["session"] == "fixed":
            continue
        c = Counter(b["verdict"] for b in r["breaks"] if b["verdict"] != "fixed")
        why = ", ".join(f"{n} {v}" for v, n in sorted(c.items()))
        if r["new_breaks"]:
            why += f"; new uses that break: {', '.join(r['new_breaks'][:5])}"
        if r["pinned_away"]:
            why += f"; pinned away: {'; '.join(r['pinned_away'][:3])}"
        out.append(f"- {r['label']} `{r['task']}`: {r['session']}: {why}")

    out += ["", "## Changes nobody asked for", "", "| arm | sessions with any | lines |", "|---|---|---|"]
    for x in arms:
        rs = by_arm[x]
        if rs:
            out.append(
                f"| {x} | {sum(r['unasked']['lines'] > 0 for r in rs)} of {len(rs)} | {sum(r['unasked']['lines'] for r in rs)} |"
            )

    out += [
        "",
        "## Cost",
        "",
        "| arm | median minutes | median turns | median output tokens | timed out |",
        "|---|---|---|---|---|",
    ]
    for x in arms:
        rs = by_arm[x]
        if not rs:
            continue
        med = lambda v: sorted(v)[len(v) // 2] if v else 0  # noqa: E731
        mins = [r["s"]["wall_s"] / 60 for r in rs]
        turns = [(r["s"].get("result") or {}).get("num_turns") or 0 for r in rs]
        toks = [((r["s"].get("result") or {}).get("usage") or {}).get("output_tokens") or 0 for r in rs]
        out.append(
            f"| {x} | {med(mins):.1f} | {med(turns)} | {med(toks)} | {sum(r['s']['timed_out'] for r in rs)} |"
        )

    out += ["", "## DT-SPIKE-06: does the agent call DepTime when it isn't named? (arm C)", ""]
    c_rs = by_arm["C"]
    called = [r for r in c_rs if r["s"]["deptime_calls"]]
    out.append(f"{len(called)} of {len(c_rs)} sessions called DepTime.")
    for r in called:
        out.append(f"- `{r['task']}`: {', '.join(r['s']['deptime_calls'][:6])}")

    own = [
        r
        for r in rows
        if any(r["t"]["repo"].lower().removeprefix("https://") in u.lower() for u in r["s"]["fetched"])
    ]
    out += ["", f"Sessions that fetched the task's own repository: {len(own)}"]
    out += [f"- {r['label']} `{r['task']}`" for r in own]
    out += [
        "",
        f"Service reruns: {sum(r['s']['attempt'] for r in rows)}; sessions ended by the service after reruns: "
        f"{sum(r['s'].get('service_error', False) for r in rows)}.",
    ]
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("envs").set_defaults(func=cmd_envs)
    h = sub.add_parser("hand")
    h.add_argument("probe", type=Path)
    h.set_defaults(func=cmd_hand)
    s = sub.add_parser("score")
    s.add_argument("probe", type=Path)
    s.add_argument("--out", type=Path, required=True)
    s.set_defaults(func=cmd_score)
    a = p.parse_args(argv)
    return a.func(a)


if __name__ == "__main__":
    raise SystemExit(main())
