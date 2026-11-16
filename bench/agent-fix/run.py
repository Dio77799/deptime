"""Run the agent on an agent-fix study's tasks, by the rules in that study's README.md (`study.py`: DT-QA-05 here by
default, DT-QA-26 in `qa26/` with AGENT_FIX_STUDY=qa26).

    uv run python bench/agent-fix/run.py tasks            # task repositories under the work dir, and the study's tasks.json
    uv run python bench/agent-fix/run.py trial            # the two trial tasks, every arm, not scored
    uv run python bench/agent-fix/run.py run --run 1      # DT-QA-05: run 1 is arms A, B and C, run 2 A and B; DT-QA-26: A, B

The work dir is ~/.cache/deptime-work/qa05 (QA05_WORK overrides), or qa26 (QA26_WORK). Sources are the GitHub tarballs
DT-QA-21 and DT-QA-22 already hold (read as data). Each session gets a fresh copy of its task and runs `claude -p`
confined to it (`--restricted`): file tools only inside the copy, no Bash but the study's pinned `uvx deptime==<pin>
check-upgrade` (and, for DT-QA-26, `rm .deptime-report.md`), so nothing runs the project's code. Transcripts stay in the
work dir; `sessions/<run>/<task>.json` (counts and tool names, no transcript text) and `diffs/<run>/<task>.diff` are
written to the study's directory. A finished session is never run again.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent
HOLDOUT = BENCH / "holdout"
PRS = BENCH / "upgrade-check" / "prs"
REPO_ROOT = BENCH.parent
PLUGIN = REPO_ROOT / "integrations" / "claude-code"
sys.path.insert(0, str(HOLDOUT))

from envs import use_key  # noqa: E402
from study import STUDY  # noqa: E402  (DT-QA-05 or DT-QA-26: AGENT_FIX_STUDY)

OUT = STUDY.out
WORK = STUDY.work
SOURCES = [
    Path("~/.cache/deptime-work/qa21/sources").expanduser(),
    Path("~/.cache/deptime-work/qa22/sources").expanduser(),
]

DEPTIME_PIN = STUDY.deptime_pin
MODEL, EFFORT = "sonnet", "high"
LIMIT_S = 30 * 60
BASE_TOOLS = ["Read", "Edit", "Write", "Glob", "Grep", "WebSearch", "WebFetch"]
PLUGIN_MCP = "mcp__plugin_deptime_deptime"
DEPTIME_CMD = re.compile(
    r"(^|[\s;&|(])(uvx\s+)?deptime(==[\w.]+)?\s"
)  # the command, not a path with the word in it
ARMS_BY_RUN = STUDY.arms_by_run
SEED = STUDY.seed
RETRIES = 2  # README.md: a session ended by the service is run again, at most twice
_GIT = ["git", "-c", "user.name=qa05", "-c", "user.email=qa05@invalid", "-c", "commit.gpgsign=false"]


# ----------------------------------------------------------------------------------------------------------- tasks


def _jsonl(path: Path) -> dict[str, dict]:
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    return {r["id"]: r for r in rows}


def _env_id(set_dir: Path, package: str, version: str) -> str:
    envs = json.loads((set_dir / "envs.json").read_text(encoding="utf-8"))["envs"]
    (env,) = [e["id"] for e in envs if e["id"].startswith(f"{package}=={version}@")]
    return env


def _task(set_name: str, set_dir: Path, row: dict, labels: dict) -> dict:
    """One task: the upgrade, where its source is, and its confirmed breaks (labelled `breaks`) with their lines."""
    where = {use_key(u): u["where"] for u in row["uses"]}
    breaks = []
    for item in labels["items"]:
        if item["label"] != "breaks":
            continue
        use = {k: item[k] for k in ("kind", "path", "npos", "kwargs", "via") if k in item}
        assert use_key(use) == item["key"], item
        breaks.append({"key": item["key"], **use, "change": item.get("change"), "where": where[item["key"]]})
    slug = row["repo"].removeprefix("https://github.com/").replace("/", "__")
    sha = row.get("base_commit") or row["commit"]  # a pull request's base still pins `from`
    return {
        "id": row["id"],
        "set": set_name,
        "repo": row["repo"],
        "source": f"{slug}@{sha}",
        "dir": row.get("dir") or "",
        "package": row["package"],
        "from": row["from"],
        "to": row["to"],
        "python": row["python"],
        "env": _env_id(set_dir, row["package"], row["to"]),
        "breaks": breaks,
    }


def _upward(row: dict) -> bool:
    from packaging.version import Version

    return Version(row["to"]) > Version(row["from"])


def all_tasks(trial: bool = False) -> list[dict]:
    if trial:
        set_dir = HOLDOUT / STUDY.trial_set
        rows, labels = _jsonl(set_dir / "upgrades.jsonl"), _jsonl(set_dir / "labels.jsonl")
        return [_task(STUDY.trial_set, set_dir, rows[i], labels[i]) for i in STUDY.trial_tasks]
    out = []
    for name in STUDY.holdout_sets:
        set_dir = HOLDOUT / name
        rows, labels = _jsonl(set_dir / "upgrades.jsonl"), _jsonl(set_dir / "labels.jsonl")
        if STUDY.holdout_only is not None:
            ids = list(STUDY.holdout_only)
        else:  # every upgrade to a newer version with a labelled break, but the trial's
            ids = [
                i
                for i, lab in labels.items()
                if any(x["label"] == "breaks" for x in lab["items"])
                and _upward(rows[i])
                and (name, i) not in {(STUDY.trial_set, x) for x in STUDY.trial_tasks}
            ]
        out += [_task(name, set_dir, rows[i], labels[i]) for i in ids]
    if STUDY.prs:
        rows, labels = _jsonl(PRS / "upgrades.jsonl"), _jsonl(PRS / "labels.jsonl")
        for i, lab in labels.items():
            if any(x["label"] == "breaks" for x in lab["items"]):
                out.append(_task("prs", PRS, rows[i], lab))
    return out


def _source(name: str) -> Path:
    for root in SOURCES:
        if (root / name).is_dir():
            return root / name
    raise SystemExit(f"no cached source {name} under {', '.join(map(str, SOURCES))}")


def build_task(task: dict) -> Path:
    repo = WORK / "tasks" / task["id"]
    shutil.rmtree(repo, ignore_errors=True)
    shutil.copytree(_source(task["source"]), repo)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run([*_GIT, "-C", str(repo), "add", "-A"], check=True)
    subprocess.run([*_GIT, "-C", str(repo), "commit", "-q", "-m", "task"], check=True)
    return repo


def cmd_tasks(a: argparse.Namespace) -> int:
    tasks, trial = all_tasks(), all_tasks(trial=True)
    for t in tasks + trial:
        build_task(t)
    n = sum(len(t["breaks"]) for t in tasks)
    doc = {"tasks": tasks, "trial": trial}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "tasks.json").write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    print(f"tasks.json: {len(tasks)} tasks, {n} confirmed breaks; {len(trial)} trial tasks", file=sys.stderr)
    return 0


# -------------------------------------------------------------------------------------------------------- sessions


def prompt(arm: str, t: dict) -> str:
    if arm == "B":
        return f"/deptime:fix-upgrade {t['package']} {t['to']} (from {t['from']})"
    return (
        f"This project uses {t['package']} {t['from']}. Updating it to {t['to']} breaks some of its code. "
        f"Change the code so that it works with {t['package']} {t['to']}."
    )


def command(arm: str) -> list[str]:
    tools, allowed = list(BASE_TOOLS), list(BASE_TOOLS)
    cmd = ["claude", "--print", "--model", MODEL, "--effort", EFFORT, "--restricted"]
    if arm in ("B", "C"):
        tools.append("Bash")
        allowed += [*STUDY.bash_rules, PLUGIN_MCP]
        cmd += ["--plugin-dir", str(PLUGIN)]
    return [
        *cmd,
        "--tools",
        ",".join(tools),
        "--allowedTools",
        " ".join(allowed),
        "--permission-mode",
        "dontAsk",
        "--no-session-persistence",
        "--output-format",
        "stream-json",
        "--verbose",
    ]


def child_env() -> dict[str, str]:
    """A clean environment: nothing of the maintainer's session (`ANTHROPIC_*`, `CLAUDE*`), no claude.ai connectors,
    no auto memory."""
    keep = ("HOME", "PATH", "USER", "LOGNAME", "LANG", "TMPDIR", "SHELL")
    env = {k: os.environ[k] for k in keep if k in os.environ}
    env.update(TERM="dumb", ENABLE_CLAUDEAI_MCP_SERVERS="false", CLAUDE_CODE_DISABLE_AUTO_MEMORY="1")
    return env


def summarise(lines: list[str]) -> dict:
    """What a session did, from its stream-json: no transcript text, only counts, tool names, commands DepTime ran
    and URLs fetched."""
    tools: dict[str, int] = {}
    deptime_calls: list[str] = []
    other_bash: list[str] = []  # tried, refused (not a tool in arm A; not allowed in B and C)
    fetched: list[str] = []
    denied = 0
    out: dict = {"result": None, "rate_limit": None, "init_tools": None}
    for line in lines:
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = ev.get("type")
        if kind == "system" and ev.get("subtype") == "init":
            out["init_tools"] = ev.get("tools")
            out["claude_code"] = ev.get("claude_code_version")
            out["model"] = ev.get("model")
        elif kind == "rate_limit_event":
            out["rate_limit"] = ev.get("rate_limit_info") or ev
        elif kind == "assistant":
            for block in ev.get("message", {}).get("content", []):
                if block.get("type") != "tool_use":
                    continue
                name = block.get("name", "")
                tools[name] = tools.get(name, 0) + 1
                inp = block.get("input") or {}
                if name == "Bash":
                    cmd = str(inp.get("command", ""))
                    (deptime_calls if DEPTIME_CMD.search(cmd) else other_bash).append(cmd[:300])
                elif name.startswith(PLUGIN_MCP):
                    deptime_calls.append(name.removeprefix(PLUGIN_MCP + "__"))
                elif name == "Skill" and "deptime" in str(inp):
                    deptime_calls.append(f"skill:{inp.get('skill', inp.get('name', ''))}")
                elif name == "WebFetch":
                    fetched.append(str(inp.get("url", ""))[:300])
        elif kind == "user":
            for block in ev.get("message", {}).get("content", []) or []:
                if isinstance(block, dict) and block.get("type") == "tool_result" and block.get("is_error"):
                    text = json.dumps(block.get("content", ""))
                    if "permission" in text.lower() or "denied" in text.lower():
                        denied += 1
        elif kind == "result":
            out["result"] = {
                k: ev.get(k)
                for k in (
                    "subtype",
                    "is_error",
                    "num_turns",
                    "duration_ms",
                    "total_cost_usd",
                    "usage",
                    "api_error_status",
                )
            }  # the agent's final report is transcript text: never kept here
    out.update(
        tools=tools, deptime_calls=deptime_calls, other_bash=len(other_bash), fetched=fetched, denied=denied
    )
    return out


def service_error(s: dict, timed_out: bool) -> bool:
    """README.md: an error of the service (a rate limit, an outage), not the agent's own stop."""
    if timed_out:
        return False
    r = s.get("result")
    if r is None:
        return True
    return bool(r.get("is_error")) and r.get("subtype") != "error_max_turns"


def _diff(repo: Path) -> str:
    subprocess.run([*_GIT, "-C", str(repo), "add", "-A"], check=True)
    return subprocess.run(
        [*_GIT, "-C", str(repo), "diff", "--cached", "--no-color", "--no-ext-diff"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def one_session(label: str, arm: str, t: dict) -> dict:
    base = WORK / "runs" / label / t["id"]
    for attempt in range(RETRIES + 1):
        shutil.rmtree(base, ignore_errors=True)
        base.mkdir(parents=True)
        repo = base / "repo"
        shutil.copytree(WORK / "tasks" / t["id"], repo)
        cwd = repo / t["dir"] if t["dir"] else repo
        transcript = base / f"transcript-{attempt}.jsonl"
        started = time.time()
        with transcript.open("w", encoding="utf-8") as fh:
            proc = subprocess.Popen(
                command(arm),
                cwd=cwd,
                env=child_env(),
                stdin=subprocess.PIPE,
                stdout=fh,
                stderr=subprocess.DEVNULL,
                text=True,
                start_new_session=True,
            )
            timed_out = False
            try:
                proc.communicate(prompt(arm, t), timeout=LIMIT_S)
            except subprocess.TimeoutExpired:
                timed_out = True
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(30)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
        s = summarise(transcript.read_text(encoding="utf-8").splitlines())
        s.update(
            task=t["id"],
            arm=arm,
            label=label,
            attempt=attempt,
            timed_out=timed_out,
            exit_code=proc.returncode,
            wall_s=round(time.time() - started, 1),
        )
        if not service_error(s, timed_out) or attempt == RETRIES:
            s["service_error"] = service_error(s, timed_out)
            return s | {"diff": _diff(repo)}
        print(f"  service error on {label}/{t['id']} (attempt {attempt}); running again", file=sys.stderr)
        time.sleep(60)
    raise AssertionError("unreachable")


def _pace(s: dict) -> None:
    """Wait out the five-hour window when it is nearly spent; stop when the weekly one is."""
    rl = s.get("rate_limit") or {}
    windows = rl.get("unifiedWindows") or rl.get("windows") or {}
    week = (windows.get("seven_day") or {}).get("utilization")
    five = windows.get("five_hour") or {}
    if week is not None and week >= 0.9:
        raise SystemExit("the weekly window is 90% spent; stopping (rerun the same command later to resume)")
    if (five.get("utilization") or 0) >= 0.9 and five.get("resetsAt"):
        wait = max(0.0, float(five["resetsAt"]) - time.time()) + 60
        print(f"  five-hour window 90% spent; waiting {wait / 60:.0f} min", file=sys.stderr)
        time.sleep(wait)


def run_sessions(label_of, arms: list[str], tasks: list[dict], seed: int, out_dir: Path) -> int:
    order = list(tasks)
    random.Random(seed).shuffle(order)
    for t in order:
        arms_here = list(arms)
        random.Random(f"{seed}|{t['id']}").shuffle(arms_here)
        for arm in arms_here:
            label = label_of(arm)
            summary = out_dir / "sessions" / label / f"{t['id']}.json"
            if summary.exists():
                continue
            print(f"{label} {t['id']}", file=sys.stderr)
            s = one_session(label, arm, t)
            diff = s.pop("diff")
            summary.parent.mkdir(parents=True, exist_ok=True)
            (out_dir / "diffs" / label).mkdir(parents=True, exist_ok=True)
            (out_dir / "diffs" / label / f"{t['id']}.diff").write_text(diff, encoding="utf-8")
            summary.write_text(json.dumps(s, indent=1) + "\n", encoding="utf-8")
            r = s.get("result") or {}
            print(
                f"  turns {r.get('num_turns')}, {s['wall_s']:.0f}s, diff {len(diff.splitlines())} lines, "
                f"deptime {len(s['deptime_calls'])}, timed out {s['timed_out']}",
                file=sys.stderr,
            )
            _pace(s)
    return 0


def cmd_trial(a: argparse.Namespace) -> int:
    trial = json.loads((OUT / "tasks.json").read_text(encoding="utf-8"))["trial"]
    arms = sorted({x for run in ARMS_BY_RUN.values() for x in run})
    return run_sessions(lambda arm: f"trial-{arm}", arms, trial, SEED, WORK / "trial-out")


def cmd_run(a: argparse.Namespace) -> int:
    tasks = json.loads((OUT / "tasks.json").read_text(encoding="utf-8"))["tasks"]
    arms = [x for x in ARMS_BY_RUN[a.run] if a.arm in (None, x)]
    return run_sessions(lambda arm: f"{arm}{a.run}", arms, tasks, SEED * 100 + a.run, OUT)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("tasks").set_defaults(func=cmd_tasks)
    sub.add_parser("trial").set_defaults(func=cmd_trial)
    r = sub.add_parser("run")
    r.add_argument("--run", type=int, choices=sorted(ARMS_BY_RUN), required=True)
    r.add_argument("--arm", choices=["A", "B", "C"])
    r.set_defaults(func=cmd_run)
    a = p.parse_args(argv)
    return a.func(a)


if __name__ == "__main__":
    raise SystemExit(main())
