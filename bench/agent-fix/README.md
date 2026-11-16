# Does an agent fix an update's breaks better with DepTime? (DT-QA-05)

**Purpose:** DepTime decides what a dependency update breaks; the fix is left to the user's coding agent (ADR 0006).
0.2.0 hands the agent its answer: the report's "For a coding agent" block and the Claude Code plugin's
`/deptime:fix-upgrade`, which runs `check-upgrade` and asks the agent to fix exactly the lines it reports (DT-GTM-07).
DT-QA-23 couldn't test that hand-off on real code: its uses were listed, not given as files. Before 1.0 freezes the
hand-off (DT-OSS-17), this asks whether the same agent, on the same real broken updates, leaves working code more
often with `/deptime:fix-upgrade` than without it. It also answers DT-SPIKE-06: with the plugin installed and not
named, does the agent call DepTime at all?

Everything on this page was committed before any agent was run on a task. `run.py` and `score.py` are committed
after the trial and before the first scored run; the trial may change how the agent is started (flags, timeouts),
never the tasks, prompts, measures or bar. The scored runs are made once and reported whichever way they come out.

**What was seen first.** Every task below comes from an earlier set whose labels and `check-upgrade` answers were read
for DT-QA-21, DT-QA-22 and DT-QA-24, and DepTime's index was fixed after some of them: DepTime's half is in-sample.
`/deptime:fix-upgrade` was written on 2026-11-16 without running an agent on any of these tasks. No agent has been run
on any of them.

## The tasks

Every upgrade to a newer version with at least one use labelled `breaks` by running it, from two sets:

- the **2026-11f holdout's 12 upgrades** (`../holdout/2026-11f/`). Its other 15 broken upgrades are downgrades,
  which don't fit "an update broke the code", and are left out;
- **DT-QA-22's 13 pull requests** with a labelled break (`../upgrade-check/prs/`).

25 tasks with 137 labelled breaking uses (the **confirmed breaks**; one task, `jerome3o__schemallm`, has 30). Each
task is a git repository built from the GitHub tarball of the set's commit (the holdout's `commit`, the pull request's
base), keeping the files those sets keep (`.py`, `.txt`, `.toml`, `.cfg`, `.lock`, `.in`, `.gitignore`), committed
once. The working tree is that commit: the project still pins `from`. For a pull request the agent works in its
project directory (`dir`).

**Trial tasks** (not scored, used only to settle how the agent is started): the 2026-11e holdout's
`pin-wayveai__driving-with-llms-openai-up` and `pin-vivekkeshore__flask-dantic-pydantic-up`.

## The arms

The same agent everywhere: Claude Code (`claude -p`, the version installed on the day, recorded), Claude Sonnet 5.5
at high effort, on the maintainer's subscription, with no CLAUDE.md, memory, skills, hooks or MCP servers of the
maintainer's, the environment cleaned of `ANTHROPIC_*` and `CLAUDE*`, one fresh copy of the task per session, and a
30-minute limit per session. Tools in every arm: Read, Edit, Write, Glob, Grep, WebSearch and WebFetch. No arm can
run the project's code or install anything: Bash, where present, is allowed only for `uvx deptime==0.2.1
check-upgrade` and denied for everything else.

| arm | DepTime | prompt | runs per task |
|---|---|---|---|
| **A, alone** | none | the task | 2 |
| **B, hand-off** | the plugin at 0.2.1 (`integrations/claude-code`), Bash for the check | `/deptime:fix-upgrade <package> <to> (from <from>)` | 2 |
| **C, installed, not named** | as B | the task, as A | 1 |

**The task** (A and C): "This project uses {package} {from}. Updating it to {to} breaks some of its code. Change the
code so that it works with {package} {to}." Nothing else: no file, line or name is pointed to.

**How the agent is started** (settled by the trial, `run.py`): `claude --print --restricted --permission-mode dontAsk`
with `--tools` and `--allowedTools` as above, `--plugin-dir integrations/claude-code` in B and C,
`ENABLE_CLAUDEAI_MCP_SERVERS=false` and `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`. `--restricted` ignores the maintainer's
settings and keeps the file tools inside the task's copy, so no session can read this directory's labels; the
claude.ai connectors and auto memory are off. In the trial, B's check ran and read the old pin itself, a compound
Bash command was denied, and A tried Bash and was told it has none.

Order: a fixed seed shuffles the tasks for each run; within a task the arms run back to back in a shuffled order. A
session that ends on an error of the service (a rate limit, an outage), not the agent's own stop, is run again from a
fresh copy, at most twice, and each rerun is recorded. A session that hits the time limit is scored as it stands.

## Scoring a session

Nothing here asks DepTime. Each session leaves a **fixed tree**; its diff against the task's commit is kept.

**Uses.** `../holdout/uses.py`, unchanged and with no cap, reads every use of the package in the task's tree and in
the fixed tree, with the import roots of any module first imported on a line the agent added (other than the project's
own modules and the standard library), so a move to a sibling package (`langchain_text_splitters`) is read too.

**Ground truth.** `../holdout/probe.py`, unchanged, on each use that is new in a fixed tree (a kind, path and shape
the task's tree doesn't have), and on each use on a line the agent added that the task's set doesn't label `works` or
`breaks` (a fix that moves onto a use the project already makes elsewhere is checked too), in the set's own environment for the package at `to` (`envs.json`: the same Python and
date cutoff), through `.github/workflows/holdout.yml`, sandboxed. A use **works**, **breaks** or **can't tell** by
`../holdout/labels.py`'s `works()`, the rule the labels came from. Uses no set ever labels, whatever the probe says
(a member of an object built by a call that isn't a class, a keyword only `**kwargs` takes, a member read off an
instance that the probe doesn't find on the class), are left out of a replacement's judgement below.

**Each confirmed break** is then

- **still broken** if the fixed tree still has a use with its key (kind, path and shape), at any line;
- **removed** if not, and at each of its lines the agent's change deleted the line, commented it out or replaced it
  with no code (`pass`, `...`, `raise NotImplementedError`), or deleted the file;
- **fixed** if not, the change at its lines adds code, and every new use on those added lines works;
- **broken by the fix** if a new use on those added lines breaks (another confirmed break still there is judged on
  its own, not here);
- **can't tell** otherwise: a new use there can't be told, or the added code uses no package the reader sees.

**Hand checks**, as DT-QA-25 and the holdout make them (`../upgrade-check/audit/README.md`): a `can't tell` may be
settled from the library's released source at the version the environment installs, or, for added code that uses no
package, by whether it does what the line it replaces did; recorded in `hand-checks.json` with the file and line that
show it. The breaks to check are written to a file that names neither the arm nor the run, in a shuffled order, and
are checked from that file only; hand checks stop where they can't change a session's verdict. A hand check never
overturns the probe.

**Each session** is

- **fixed:** every confirmed break is fixed, no new use anywhere in the fixed tree breaks, and no manifest pins the
  package to anything but `to`;
- **not fixed:** a confirmed break is still broken, removed or broken by the fix, or a new use breaks, or the package
  is pinned to another version (including back to `from`);
- **can't tell:** otherwise.

**Changes nobody asked for:** lines the diff changes outside every hunk that holds a confirmed break's line or a new
use of the package. Counted per session, with no bar (an agent may fix an unlabelled break there; they are listed).

## Measures and the bar

Over task sessions, with 95% Wilson intervals:

1. **sessions fixed** per arm: fixed / sessions (can't tell counts as not fixed; reported apart);
2. **sessions with a new break** per arm: sessions where the fix itself breaks something (a confirmed break broken by
   the fix, or a new use that breaks);
3. **confirmed breaks fixed** per arm: fixed / (137 × runs).

**The bar: the hand-off is kept for 1.0 if arm B**

- fixes at least **80%** of its sessions, and
- fixes at least as many sessions as arm A, and
- has no more sessions with a new break than arm A.

**If met,** DT-OSS-17 freezes the hand-off as it is. **If missed,** DT-OSS-17 waits: the hand-off and
`/deptime:fix-upgrade` are reworked from the sessions B didn't fix first, and the result says which part failed
(DepTime's answer, the command's instructions or the agent). Either way the result goes in `bench/README.md` and one
line of the README's "Check a dependency update" section.

Reported beside them, with no bar: each measure by set (holdout, pull requests); tasks fixed in both runs of an arm;
the paired comparison of A and B per task (both, B only, A only, neither) with McNemar's exact test; changes nobody
asked for; time, turns and tokens per session; for arm B, the breaks `check-upgrade` reported and missed on each task;
and for arm C, **the DT-SPIKE-06 answer:** sessions that called DepTime (an MCP tool of the plugin or the check) and
what they called, with C's own measures. Sessions that fetched the task's own repository from the web are listed.

## Running it

```bash
uv run python bench/agent-fix/run.py tasks                 # build the task repositories and tasks.json
uv run python bench/agent-fix/run.py trial                 # the two trial tasks, not scored
uv run python bench/agent-fix/run.py run --run 1           # A1, B1 and C1, interleaved; then --run 2: A2 and B2
uv run python bench/agent-fix/score.py envs                # the probe's environments for the new uses
# push to a spike/holdout branch with SET: bench/agent-fix in holdout.yml; then
gh run download <run id> -p 'holdout-*' -D <empty dir>
uv run python bench/agent-fix/score.py hand <that dir>     # hand-todo.json: the blinded hand checks
uv run python bench/agent-fix/score.py score <that dir> --out bench/agent-fix/results-<date>.md
```

Task copies and transcripts live under `~/.cache/deptime-work/qa05/`; the diffs and each session's summary (no
transcript text) are committed with the results.
