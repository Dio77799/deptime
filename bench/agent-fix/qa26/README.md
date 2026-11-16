# Does the reworked hand-off fix an update's breaks better? (DT-QA-26)

**Purpose:** DT-QA-05 (`../README.md`, `../results-2026-11-16.md`) found that Claude Code on Sonnet left 25 real broken
updates working in 80% of sessions alone and in 64% with `/deptime:fix-upgrade`. Its 8 losses came from the command,
not from a wrong answer of DepTime's: it told the agent to leave `unknown` uses alone, to stop when a pin was unread,
and it handed over a report too long for the shell. DT-GTM-08 reworked the command and the report's agent block, and
0.2.2 released them. This asks the same question again, on broken updates the reworked command was never shaped on:
does the agent leave working code at least as often with `/deptime:fix-upgrade` as without it? DT-OSS-17 (the 1.0
promise) waits for the answer.

Everything on this page is committed before any agent is run on a task of this study. The scripts are DT-QA-05's
(`../run.py`, `../score.py`), made to run a second study (`../study.py`) and committed with this page: re-scoring
DT-QA-05 with them gives its committed tables unchanged. The trial may change how the agent is started (flags,
timeouts), never the tasks, prompts, measures or bar; any such change is committed before the first scored run. The
scored runs are made once and reported whichever way they come out.

**What was seen first.** Every task comes from the holdout sets 2026-11 to 2026-11e, whose labels and `check-upgrade`
answers were read for DT-QA-21, DT-QA-24 and DT-QA-25, and DepTime's index was fixed after some of them: DepTime's half
is in-sample, as in DT-QA-05. The command's half is not: DT-GTM-08 was written from DT-QA-05's sessions (2026-11f and
DT-QA-22's pull requests) and smoke-tested on two 2026-11f tasks. No agent has been run on any task below; none of
their 66 projects is one of DT-QA-05's.

## The tasks

Every upgrade to a newer version with at least one use labelled `breaks` by running it, in the holdout sets 2026-11,
2026-11b, 2026-11c, 2026-11d and 2026-11e (`../../holdout/`), less the two trial tasks: **66 tasks** (9, 11, 11, 23 and
12 by set) in 66 projects and on 24 packages, with **379 confirmed breaks** (the uses labelled `breaks`; four tasks
have 20 or more). The list is `tasks.json`, built by `run.py tasks` from the sets' files alone. Each task is a git
repository built from the GitHub tarball of the holdout's `commit`, keeping the files the holdout keeps, committed
once; the working tree still pins `from`.

**Trial tasks** (not scored, used only to settle how the agent is started): DT-QA-05's, the 2026-11e holdout's
`pin-wayveai__driving-with-llms-openai-up` and `pin-vivekkeshore__flask-dantic-pydantic-up`.

## The arms

DT-QA-05's agent and setup, unchanged but for the release: Claude Code (`claude -p`, 2.1.325 on the day this was
written; the version each session reports is recorded), Claude Sonnet 5.5 at high effort, on the maintainer's
subscription, `--restricted --permission-mode dontAsk`, no CLAUDE.md, memory, skills, hooks or MCP servers of the
maintainer's, one fresh copy of the task per session, a 30-minute limit. Tools in both arms: Read, Edit, Write, Glob,
Grep, WebSearch and WebFetch. Neither arm can run the project's code or install anything.

| arm | DepTime | prompt | runs per task |
|---|---|---|---|
| **A, alone** | none | the task | 1 |
| **B, hand-off** | the plugin at 0.2.2 (`integrations/claude-code`); Bash only for `uvx deptime==0.2.2 check-upgrade` and `rm .deptime-report.md`, the two commands the command's `allowed-tools` names | `/deptime:fix-upgrade <package> <to> (from <from>)` | 1 |

**The task** (A): "This project uses {package} {from}. Updating it to {to} breaks some of its code. Change the code so
that it works with {package} {to}." B's prompt is DT-QA-05's, as `run.py` writes it.

One run per arm on 66 tasks rather than two on 25: more projects, and 66 pairs for the paired comparison. **Arm C**
(the plugin installed and not named) is left out: DT-QA-05 answered DT-SPIKE-06 (25 of 25 sessions called DepTime),
and the question here is the reworked command.

**The shell.** As in DT-QA-05, `dontAsk` denies every Bash command but the two above: `claude -p` can't ask a person.
The reworked command asks for no pipe or redirect (it writes the report with `--output` and reads it with Read), so
this shell no longer stands between B and the report. A command the agent adds anyway (`; echo`, a pipe) is still
denied, and counted.

Order: a fixed seed (26) shuffles the tasks; within a task the arms run back to back in a shuffled order. A session
that ends on an error of the service (a rate limit, an outage), not the agent's own stop, is run again from a fresh
copy, at most twice, and each rerun is recorded. A session that hits the time limit is scored as it stands.

## Scoring a session

Exactly DT-QA-05's rules (`../README.md`, "Scoring a session"), with `score.py` as committed here, which includes the
four corrections DT-QA-05 made before its summary. In short: `../../holdout/uses.py`, unchanged and uncapped, reads
the uses in the task's tree and the fixed tree; `../../holdout/probe.py`, unchanged, runs every new use and every
unlabelled use on an added line in the set's own environment at `to`, through `.github/workflows/holdout.yml` with
`SET: bench/agent-fix/qa26`; each confirmed break is **still broken**, **removed**, **fixed**, **broken by the fix** or
**can't tell**; each session is **fixed** (every confirmed break fixed, no new use breaks, no manifest pins the package
to anything but `to`), **not fixed** or **can't tell**. Hand checks settle a `can't tell` from the library's released
source, blind to arm (`hand-todo.json` names neither arm nor run), stop where they can't change a verdict, never
overturn the probe, and are recorded in `hand-checks.json` with the file and line that show them.

Nothing in the scoring asks DepTime about a session. DepTime is asked once per task, offline, only to report which
confirmed breaks `check-upgrade` reported (a column, no bar).

## Measures and the bar

Over sessions, with 95% Wilson intervals:

1. **sessions fixed** per arm: fixed / 66 (can't tell counts as not fixed; reported apart);
2. **sessions with a new break** per arm: sessions where the fix itself breaks something;
3. **confirmed breaks fixed** per arm: fixed / 379.

**The bar: the hand-off is kept for 1.0 if arm B**

- fixes at least **80%** of its sessions, and
- fixes at least as many sessions as arm A, and
- has no more sessions with a new break than arm A.

DT-QA-05's bar, unchanged.

**If met,** DT-OSS-17 freezes the hand-off (the command and the report's "For a coding agent" block) as it is. **If
missed,** there is no third rework before 1.0: the 1.0 promise (DT-OSS-17) leaves the command and the agent block out
of what it freezes, both are marked experimental in the plugin's README and CHANGELOG.md, and the plugin's README
leads with asking the agent in plain words with the plugin installed (DT-QA-05's arm C, 80%, in-sample there). The
result says which part lost B its sessions (DepTime's answer, the command's instructions, the shell or the agent).
Either way the result goes in `bench/README.md` and one line of the README's "Check a dependency update" section.

Reported beside them, with no bar: each measure by set; the paired comparison of A and B per task (both, B only, A
only, neither) with McNemar's exact test; changes nobody asked for; time, turns and tokens per session; Bash commands
denied per arm; for arm B, the sessions that ran the check and the breaks `check-upgrade` reported and missed on each
task; sessions that fetched the task's own repository from the web.

## Running it

```bash
export AGENT_FIX_STUDY=qa26
uv run python bench/agent-fix/run.py tasks                 # task repositories and qa26/tasks.json
uv run python bench/agent-fix/run.py trial                 # the two trial tasks, A and B, not scored
uv run python bench/agent-fix/run.py run --run 1           # A1 and B1, interleaved
uv run python bench/agent-fix/score.py envs                # qa26/envs.json: the probe's environments for the new uses
# push to a spike/holdout branch with SET: bench/agent-fix/qa26 in holdout.yml; then
gh run download <run id> -p 'holdout-*' -D <empty dir>
uv run python bench/agent-fix/score.py hand <that dir>     # qa26/hand-todo.json: the blinded hand checks
uv run python bench/agent-fix/score.py score <that dir> --out bench/agent-fix/qa26/results-<date>.md
```

Task copies and transcripts live under `~/.cache/deptime-work/qa26/`; the diffs and each session's summary (no
transcript text) are committed with the results.
