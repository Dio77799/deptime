# The fixed hand-off on broken updates nobody has seen (DT-QA-27)

**Purpose:** DT-QA-26 (`../qa26/README.md`, `../qa26/results-2026-11-16.md`) found that Claude Code on Sonnet left 66
broken updates working in 69.7% of sessions alone and in 72.7% with `/deptime:fix-upgrade`. It met two parts of the
bar (B at least as many sessions as A, no more new breaks) and missed 80%. Of B's four losses to A, three came from the
command, which told the agent to leave a break with no stated replacement, and one from DepTime, which missed a
streamlit call through the module's bound-method aliases. DT-GTM-09 changed the command and the report's agent block
to rewrite such breaks from the new version's source, DT-DATA-83 fixed the streamlit miss, and 0.2.3 released both.
This asks the question once more, on a holdout set collected after both changes and never looked at before: does the
agent leave working code in at least 80% of sessions with `/deptime:fix-upgrade`, and at least as often as without
it? DT-OSS-17 (the 1.0 promise) waits for the answer (the maintainer's call, 2026-11-16).

Everything on this page is committed before any agent is run on a task of this study. The scripts are DT-QA-26's
(`../run.py`, `../score.py`, `../study.py`), with only this study's entry and the new set's source folder added. The
trial may change how the agent is started (flags, timeouts), never the tasks, prompts, measures or bar; any such change
is committed before the first scored run. The scored runs are made once and reported whichever way they come out.

**What was seen first.** Nothing. Every task comes from holdout set 2026-11g (`../../holdout/2026-11g/`), collected on
2026-11-16 after 0.2.3 was released. Its labels come from the probe alone; neither DepTime nor an agent had been run
on any of its upgrades when this page was committed, and no fix in DepTime or the command was shaped on it. Unlike
DT-QA-05 and DT-QA-26, both halves are out of sample. None of its projects is in an earlier holdout set or DT-QA-22's
pull requests.

## The tasks

Every upgrade to a newer version with at least one use labelled `breaks` by running it in holdout set 2026-11g: **60
tasks** in 58 projects and on 20 packages, with **373 confirmed breaks** (the uses labelled `breaks`; six tasks have 20
or more). The list is `tasks.json`, built by `run.py tasks` from the set's files alone. Each task is a git repository
built from the GitHub tarball of the holdout's `commit`, keeping the files the holdout keeps, committed once; the
working tree still pins `from`.

**Trial tasks** (not scored, used only to settle how the agent is started): DT-QA-05's and DT-QA-26's, the 2026-11e
holdout's `pin-wayveai__driving-with-llms-openai-up` and `pin-vivekkeshore__flask-dantic-pydantic-up`.

## The arms

DT-QA-26's agent and setup, unchanged but for the release: Claude Code (`claude -p`; the version each session reports
is recorded), Claude Sonnet 5.5 at high effort, on the maintainer's subscription, `--restricted --permission-mode
dontAsk`, no CLAUDE.md, memory, skills, hooks or MCP servers of the maintainer's, one fresh copy of the task per
session, a 30-minute limit. Tools in both arms: Read, Edit, Write, Glob, Grep, WebSearch and WebFetch. Neither arm can
run the project's code or install anything.

| arm | DepTime | prompt | runs per task |
|---|---|---|---|
| **A, alone** | none | the task | 1 |
| **B, hand-off** | the plugin at 0.2.3 (`integrations/claude-code`); Bash only for `uvx deptime==0.2.3 check-upgrade` and `rm .deptime-report.md`, the two commands the command's `allowed-tools` names | `/deptime:fix-upgrade <package> <to> (from <from>)` | 1 |

**The task** (A): "This project uses {package} {from}. Updating it to {to} breaks some of its code. Change the code so
that it works with {package} {to}." B's prompt is DT-QA-05's, as `run.py` writes it.

**The shell.** As before, `dontAsk` denies every Bash command but the two above, and each denied command is counted.

Order: a fixed seed (27) shuffles the tasks; within a task the arms run back to back in a shuffled order. A session
that ends on an error of the service (a rate limit, an outage), not the agent's own stop, is run again from a fresh
copy, at most twice, and each rerun is recorded. A session that hits the time limit is scored as it stands.

## Scoring a session

Exactly DT-QA-26's rules (`../qa26/README.md`, "Scoring a session"), with `score.py` as committed here, which includes
the scoring corrections DT-QA-26 disclosed (git-quoted paths, a namespace sibling named by its dotted path, Poetry's
bare pins). In short: `../../holdout/uses.py`, unchanged and uncapped, reads the uses in the task's tree and the fixed
tree; `../../holdout/probe.py`, unchanged, runs every new use and every unlabelled use on an added line in the set's
own environment at `to`, through `.github/workflows/holdout.yml` with `SET: bench/agent-fix/qa27`; each confirmed
break is **still broken**, **removed**, **fixed**, **broken by the fix** or **can't tell**; each session is **fixed**
(every confirmed break fixed, no new use breaks, no manifest pins the package to anything but `to`), **not fixed** or
**can't tell**. Hand checks settle a `can't tell` from the library's released source, blind to arm (`hand-todo.json`
names neither arm nor run), stop where they can't change a verdict, never overturn the probe, and are recorded in
`hand-checks.json` with the file and line that show them. A scoring bug found after the runs is fixed in `score.py`,
the earlier studies are re-scored to show it changes none of their tables, and the fix is disclosed in the results.

Nothing in the scoring asks DepTime about a session. DepTime is asked once per task, offline, only to report which
confirmed breaks `check-upgrade` reported (a column, no bar).

## Measures and the bar

Over sessions, with 95% Wilson intervals:

1. **sessions fixed** per arm: fixed / 60 (can't tell counts as not fixed; reported apart);
2. **sessions with a new break** per arm: sessions where the fix itself breaks something;
3. **confirmed breaks fixed** per arm: fixed / 373.

**The bar: the hand-off is kept for 1.0 if arm B**

- fixes at least **80%** of its sessions, and
- fixes at least as many sessions as arm A, and
- has no more sessions with a new break than arm A.

DT-QA-05's and DT-QA-26's bar, unchanged.

**If met,** DT-OSS-17 freezes the hand-off (the command and the report's "For a coding agent" block) as it is. **If
missed,** the 1.0 promise leaves the command and the agent block out of what it freezes, both are marked experimental
in the plugin's README and CHANGELOG.md, and the plugin's README leads with asking the agent in plain words with the
plugin installed; whether to rework the command again first is the maintainer's call. The result says which part lost
B its sessions (DepTime's answer, the command's instructions, the shell or the agent). Either way the result goes in
`bench/README.md` and one line of the README's "Check a dependency update" section.

Reported beside them, with no bar: the paired comparison of A and B per task (both, B
only, A only, neither) with McNemar's exact test; changes nobody asked for; time, turns and tokens per session; Bash
commands denied per arm; for arm B, the sessions that ran the check and the breaks `check-upgrade` reported and missed
on each task; sessions that fetched the task's own repository from the web; and, read by hand, how DT-QA-26's loss
causes fared (B's breaks with no stated replacement, and whether each was rewritten or left).

## Running it

```bash
export AGENT_FIX_STUDY=qa27
uv run python bench/agent-fix/run.py tasks                 # task repositories and qa27/tasks.json
uv run python bench/agent-fix/run.py trial                 # the two trial tasks, A and B, not scored
uv run python bench/agent-fix/run.py run --run 1           # A1 and B1, interleaved
uv run python bench/agent-fix/score.py envs                # qa27/envs.json: the probe's environments for the new uses
# push to a spike/holdout branch with SET: bench/agent-fix/qa27 in holdout.yml; then
gh run download <run id> -p 'holdout-*' -D <empty dir>
uv run python bench/agent-fix/score.py hand <that dir>     # qa27/hand-todo.json: the blinded hand checks
uv run python bench/agent-fix/score.py score <that dir> --out bench/agent-fix/qa27/results-<date>.md
```

Task copies and transcripts live under `~/.cache/deptime-work/qa27/`; the diffs and each session's summary (no
transcript text) are committed with the results.
