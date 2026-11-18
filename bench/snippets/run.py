"""DT-GTM-05: the paste-in instructions, tried in a fresh project (protocol: README.md beside this file).

    uv run python bench/snippets/run.py run [--client codex|claude] [--arm snippet|none] [--task error|memory|upgrade]
    uv run python bench/snippets/run.py report

Each session gets a new project folder under ~/.cache/deptime-work/snippets/<client>-<arm>-<task>/project, its
transcript beside it (outside the project, so the agent never reads it). A finished session is skipped on a rerun.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SNIPPETS = REPO / "integrations" / "snippets"
WORK = Path.home() / ".cache" / "deptime-work" / "snippets"
DEPTIME = "deptime==1.0.3"
TIMEOUT = 15 * 60

TASKS: dict[str, dict] = {
    "error": {
        "packages": ["httpx==0.28.1"],
        "files": {
            "fetch.py": (
                "import httpx\n\n\n"
                "def make_client() -> httpx.Client:\n"
                '    return httpx.Client(proxies="http://localhost:8080", timeout=5)\n\n\n'
                'if __name__ == "__main__":\n'
                "    with make_client() as client:\n"
                '        print("client ready:", type(client).__name__)\n'
            ),
        },
        "prompt": "Running `.venv/bin/python fetch.py` fails. Fix it.",
        "check": "import subprocess, sys; sys.exit(subprocess.run([sys.executable, 'fetch.py']).returncode)",
    },
    "memory": {
        "packages": ["pydantic==2.12.5"],
        "files": {"models.py": ""},
        "prompt": (
            "In models.py, add a pydantic model `User` with `name` and `email`, where the email is stored lowercased, "
            "and a function `to_json(user)` that returns it as a JSON string."
        ),
        "check": (
            "import warnings; warnings.simplefilter('error', DeprecationWarning)\n"
            "import models\n"
            "out = models.to_json(models.User(name='A', email='A@B.COM'))\n"
            "assert isinstance(out, str) and 'a@b.com' in out, out\n"
        ),
    },
    "upgrade": {
        "packages": ["flask==2.3.3"],
        "files": {
            "requirements.txt": "flask==2.3.3\n",
            "app.py": (
                "from flask import Flask, Markup, escape, request\n\n"
                "app = Flask(__name__)\n\n\n"
                '@app.route("/")\n'
                "def hello():\n"
                '    name = escape(request.args.get("name", "world"))\n'
                '    return Markup("<h1>Hello, {}!</h1>").format(name)\n'
            ),
        },
        "prompt": "Update Flask to 3.1.2 in requirements.txt and make sure the app still works.",
        "pre_check": ["flask==3.1.2"],
        "check": (
            "from importlib.metadata import version; assert version('flask') == '3.1.2', version('flask')\n"
            "assert 'flask==3.1.2' in open('requirements.txt').read().lower().replace(' ', '')\n"
            "import app\n"
            "body = app.app.test_client().get('/?name=<b>').get_data(as_text=True)\n"
            "assert '&lt;b&gt;' in body and '<b>' not in body, body\n"
        ),
    },
}
CLIENTS = ("codex", "claude")
ARMS = ("snippet", "none")


def snippet_text(client: str) -> tuple[str, str]:
    """(relative path, text) of the instruction file the `snippet` arm adds."""
    if client == "cursor":
        return ".cursor/rules/deptime.mdc", (SNIPPETS / "cursor-deptime.mdc").read_text()
    text = (SNIPPETS / "agents-md-deptime.md").read_text()
    return "AGENTS.md", text[text.index("## ") :]


def git(project: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(project), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        check=True,
        capture_output=True,
    )


def make_project(session: Path, client: str, arm: str, task: str) -> Path:
    project = session / "project"
    if session.exists():
        shutil.rmtree(session)
    project.mkdir(parents=True)
    t = TASKS[task]
    for name, text in t["files"].items():
        (project / name).write_text(text)
    if arm == "snippet":
        rel, text = snippet_text(client)
        (project / rel).parent.mkdir(parents=True, exist_ok=True)
        (project / rel).write_text(text)
    (project / ".gitignore").write_text(".venv/\n")
    subprocess.run(["uv", "venv", "-q", "--python", "3.12", str(project / ".venv")], check=True)
    subprocess.run(
        ["uv", "pip", "install", "-q", "--python", str(project / ".venv" / "bin" / "python"), *t["packages"]],
        check=True,
    )
    git(project, "init", "-q")
    git(project, "add", "-A")
    git(project, "commit", "-qm", "start")
    return project


def clean_env() -> dict[str, str]:
    keep = ("HOME", "PATH", "USER", "LOGNAME", "LANG", "TMPDIR", "SHELL")
    env = {k: os.environ[k] for k in keep if k in os.environ}
    env["TERM"] = "dumb"
    return env


def command(client: str, project: Path) -> tuple[list[str], dict[str, str]]:
    env = clean_env()
    if client == "codex":
        return [
            "codex",
            "exec",
            "--json",
            "-C",
            str(project),
            "-s",
            "workspace-write",
            "-c",
            "sandbox_workspace_write.network_access=true",
            "-c",
            'model_reasoning_effort="medium"',
            "-c",
            "mcp_servers.chrome-devtools.enabled=false",
            "-c",
            "mcp_servers.node_repl.enabled=false",
            "-c",
            'mcp_servers.deptime.command="uvx"',
            "-c",
            f'mcp_servers.deptime.args=["{DEPTIME}", "mcp"]',
            "-",
        ], env
    config = project.parent / "mcp.json"
    config.write_text(json.dumps({"mcpServers": {"deptime": {"command": "uvx", "args": [DEPTIME, "mcp"]}}}))
    env.update(ENABLE_CLAUDEAI_MCP_SERVERS="false", CLAUDE_CODE_DISABLE_AUTO_MEMORY="1")
    tools = "Bash,Read,Edit,Write,Glob,Grep"
    return [
        "claude",
        "--print",
        "--model",
        "sonnet",
        "--effort",
        "high",
        "--restricted",
        "--strict-mcp-config",
        "--mcp-config",
        str(config),
        "--tools",
        tools,
        "--allowedTools",
        f"{tools.replace(',', ' ')} mcp__deptime",
        "--permission-mode",
        "dontAsk",
        "--no-session-persistence",
        "--output-format",
        "stream-json",
        "--verbose",
    ], env


def run_session(client: str, arm: str, task: str) -> None:
    session = WORK / f"{client}-{arm}-{task}"
    if (session / "summary.json").exists():
        print(f"skip {session.name} (done)")
        return
    project = make_project(session, client, arm, task)
    cmd, env = command(client, project)
    print(f"run  {session.name}", flush=True)
    start = time.monotonic()
    with (session / "transcript.jsonl").open("w") as out, (session / "stderr.txt").open("w") as err:
        try:
            proc = subprocess.run(
                cmd,
                cwd=project,
                env=env,
                input=TASKS[task]["prompt"],
                text=True,
                stdout=out,
                stderr=err,
                timeout=TIMEOUT,
            )
            code = proc.returncode
        except subprocess.TimeoutExpired:
            code = "timeout"
    seconds = round(time.monotonic() - start)
    summary = {"client": client, "arm": arm, "task": task, "exit": code, "seconds": seconds}
    summary.update(read_transcript(client, (session / "transcript.jsonl").read_text().splitlines()))
    summary["works"] = check(project, task)
    (session / "summary.json").write_text(json.dumps(summary, indent=2))
    print(f"     {line(summary)}", flush=True)


def read_transcript(client: str, lines: list[str]) -> dict:
    """The ordered tool steps: ("deptime", tool), ("edit", path) or ("shell", command); DepTime through the shell
    counts as a DepTime step."""
    steps: list[list[str]] = []
    for raw in lines:
        try:
            ev = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if client == "codex":
            item = ev.get("item") or {}
            if ev.get("type") != "item.completed":
                continue
            kind = item.get("type")
            if kind == "mcp_tool_call":
                steps.append([f"mcp:{item.get('server')}", str(item.get("tool"))])
            elif kind == "file_change":
                steps.append(["edit", ",".join(c.get("path", "") for c in item.get("changes", []))])
            elif kind == "command_execution":
                steps.append(["shell", str(item.get("command"))[:300]])
        elif ev.get("type") == "assistant":
            for block in ev.get("message", {}).get("content", []):
                if block.get("type") != "tool_use":
                    continue
                name, inp = block.get("name", ""), block.get("input") or {}
                if name.startswith("mcp__"):
                    _, server, tool = name.split("__", 2)
                    steps.append([f"mcp:{server}", tool])
                elif name in ("Edit", "Write"):
                    steps.append(["edit", str(inp.get("file_path"))])
                elif name == "Bash":
                    steps.append(["shell", str(inp.get("command"))[:300]])
                else:
                    steps.append(["tool", name])
    for s in steps:
        if s[0] == "shell" and "deptime" in s[1] and "check-upgrade" in s[1]:
            s[0] = "deptime-cli"
    deptime = [i for i, s in enumerate(steps) if s[0] in ("mcp:deptime", "deptime-cli")]
    edits = [i for i, s in enumerate(steps) if s[0] == "edit"]
    return {
        "deptime_calls": [
            steps[i][1] if steps[i][0] == "mcp:deptime" else "cli check-upgrade" for i in deptime
        ],
        "deptime_before_first_edit": bool(deptime) and (not edits or deptime[0] < edits[0]),
        "other_mcp": sorted({s[0] for s in steps if s[0].startswith("mcp:") and s[0] != "mcp:deptime"}),
        "steps": steps,
    }


def check(project: Path, task: str) -> bool:
    python = project / ".venv" / "bin" / "python"
    t = TASKS[task]
    if t.get("pre_check"):
        reqs = ["-r", "requirements.txt"] if (project / "requirements.txt").exists() else t["pre_check"]
        subprocess.run(
            ["uv", "pip", "install", "-q", "--python", str(python), *reqs], cwd=project, check=False
        )
    proc = subprocess.run([str(python), "-c", t["check"]], cwd=project, capture_output=True, text=True)
    if proc.returncode:
        (project.parent / "check.txt").write_text(proc.stdout + proc.stderr)
    return proc.returncode == 0


def line(s: dict) -> str:
    calls = ", ".join(s["deptime_calls"]) or "none"
    first = "before first edit" if s["deptime_before_first_edit"] else "after an edit / never"
    return (
        f"{s['client']:6} {s['arm']:7} {s['task']:7} DepTime: {calls} ({first}); "
        f"works: {s['works']}; {s['seconds']} s; exit {s['exit']}"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--client", choices=CLIENTS)
    r.add_argument("--arm", choices=ARMS)
    r.add_argument("--task", choices=sorted(TASKS))
    sub.add_parser("report")
    a = ap.parse_args()
    if a.cmd == "run":
        for client in [a.client] if a.client else CLIENTS:
            for arm in [a.arm] if a.arm else ARMS:
                for task in [a.task] if a.task else TASKS:
                    run_session(client, arm, task)
    else:
        for path in sorted(WORK.glob("*/summary.json")):
            print(line(json.loads(path.read_text())))
    sys.exit(0)


if __name__ == "__main__":
    main()
