# The paste-in instructions, tried in a fresh project (DT-GTM-05)

**Question:** a project that connects DepTime and pastes in `integrations/snippets/` (the `AGENTS.md` block, or the
Cursor rule): does its coding agent call DepTime at the moments the text names, and would it have called it anyway
without the text?

This is a try, not a scored measurement: one session per cell, no bar, no percentages. It decides what the docs say
about the snippets, nothing in the README's numbers.

## Setup

- **Fresh project:** for each session, `run.py` makes a new folder under `~/.cache/deptime-work/snippets/`, with
  the task's files, a `.venv` holding the task's pinned packages, and one git commit. Nothing else from the
  maintainer's setup: no other instruction files, and DepTime (`uvx deptime==1.0.3 mcp`) is the only MCP server
  the session has.
- **Clients:**
  - Codex CLI 0.166.0 (`codex exec --json`, sandbox `workspace-write` with network, `gpt-6-luna` at reasoning
    effort `medium`; the account's other MCP servers turned off, except the built-in
    `codex_apps` and a plugin's, which can't be). Codex reads `AGENTS.md`.
  - Claude Code 2.1.327 (`claude -p`, Sonnet at effort `high`, `--strict-mcp-config`, tools Bash, Read, Edit,
    Write, Glob, Grep and DepTime's, child environment stripped of `ANTHROPIC_*` and `CLAUDE*`). Claude Code reads
    `AGENTS.md` when a project has no `CLAUDE.md`; not with `--restricted`, which turns instruction files off, so
    the sessions run without it.
  - Cursor, with the rule as `.cursor/rules/deptime.mdc`, only if it is installed when the run happens; it is
    not installed on the test machine as this is written.
- **Arms:** `snippet`: the project's `AGENTS.md` is the snippet (its `##` section, without the "Paste into"
  comment); for Cursor, the rule file. `none`: no instruction file, so the agent has only DepTime's own MCP
  server instructions and tool descriptions.
- **Tasks** (the prompt never names DepTime):
  - `error`: httpx 0.28.1 installed; `fetch.py` builds `httpx.Client(proxies=...)`. Prompt: "Running
    `.venv/bin/python fetch.py` fails. Fix it." The snippet names `explain_error`.
  - `memory`: pydantic 2.12 installed, empty `models.py`. Prompt: "In models.py, add a pydantic model `User` with
    `name` and `email`, where the email is stored lowercased, and a function `to_json(user)` that returns it as a
    JSON string." The snippet names `check_symbols`.
  - `upgrade`: `requirements.txt` pins `flask==2.3.3`; `app.py` imports `Markup` and `escape` from flask (both
    gone in 3.0). Prompt: "Update Flask to 3.1.2 in requirements.txt and make sure the app still works." The
    snippet names `check_upgrade`.

2 clients × 2 arms × 3 tasks = 12 sessions, plus 6 if Cursor is run.

## Trial (before the scored sessions)

Two trial sessions on `error` (one per client, `snippet` arm) found three setup faults, fixed before any scored
session; the trials are discarded:

- the account's default Codex model, `gpt-6.1-sol`, is refused to the Codex CLI on a ChatGPT login, so Codex runs
  `gpt-6-luna`, the CLI's first listed model;
- `run.py`, started with `uv run`, put this repo's `.venv/bin` on the agent's PATH, and Codex found and ran the
  development `deptime` command instead of the MCP tools it reported missing (with a clean PATH and the account's
  Blender server off it lists and calls all six); the PATH is now cleaned;
- `claude --restricted` loads no `AGENTS.md` or `CLAUDE.md` (checked with a test instruction); Claude Code's trial
  read the snippet only because it ran `cat AGENTS.md` itself. Instruction files also don't load from the system
  temp folder, so the projects stay under `~/.cache`.

## What is recorded

For each session: each DepTime tool called (MCP, or the `deptime` command through the shell), whether the first
call came before the agent's first edit, and whether the task ended working (`run.py check`: `fetch.py` exits 0;
`to_json(User(name="A", email="A@B.COM"))` holds `a@b.com` with no deprecation warning; with Flask 3.1.2
installed, `GET /?name=<b>` returns the escaped name). Transcripts stay in the work folder, not in the repo.

## What follows from it

- In the `snippet` arm, a client that calls DepTime in the `error` and `upgrade` tasks keeps the snippet as
  written; one that doesn't gets the snippet's wording changed and tried again on the task it missed.
- A client that calls DepTime as often in the `none` arm doesn't need the snippet: the docs say so.
- The `memory` task is reported but decides nothing: calling a checker for code that already works is a judgment
  call, and the snippet asks for it only "from memory".
