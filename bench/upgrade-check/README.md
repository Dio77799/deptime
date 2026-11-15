# The upgrade check, end to end (DT-QA-21)

**Purpose:** measure `deptime check-upgrade` as a project would run it: on the whole project, read by DepTime's own
reader, with no list of uses handed to it. The holdout scores (`../holdout/`) ask `check_symbols` about each labelled
use directly, so they measure the index and the query, never the reader, and never what a check on a pull request
shows: whether the check fails.

Everything on this page and `run.py` was committed before the first scored run. It is run once and reported whichever
way it comes out.

**What it is not.** The six sets are in-sample for `check_symbols`: fixes were designed from their misses. What is new
here is the reader (`src/deptime/snippet.py`) on whole projects, the filter that sets apart a use flagged at the old
version too, and the per-upgrade verdict. A first measure on update pull requests nobody designed a fix from is
DT-QA-22.

## What is run

- **Cases:** the six holdout sets' upgrades that have a labelled use (`works` or `breaks`): 1,131 upgrades of 637
  projects at a fixed commit, with 14,427 uses that work and 866 that break, labelled by running them
  (`../holdout/README.md`). 976 upgrades are clean: every labelled use works.
- **Sources:** each project at its recorded commit, fetched as `../holdout/find_pinned.py` fetches them: GitHub's
  tarball, keeping only `.py`, `.txt`, `.toml` and `.cfg` files, read as data. A source that can't be fetched (a
  repository deleted or made private since) is listed and left out of every count.
- **The call:** for each upgrade, `deptime.upgrade.check_upgrade` (the function behind `deptime check-upgrade
  --package P --from F --to T`) with the set's package, `from` and `to`, on every Python file `project_files` lists
  (no git in a tarball: the walk that leaves out virtual environments, build output and caches). No suppressions.
- **Index:** the published index as `deptime index pull` installs it on the day of the run; the results give its
  build time.

## Matching answers to labels

Each labelled use counts once per upgrade it is labelled in, as the holdout scorer counts it.

- A use is **read** when the reader reads its path in the project (it is among the queries `check-upgrade` asks).
- A use is **flagged** when one of the upgrade's breaks has its path and:
  - the break is `missing` (any use); or
  - the use is a call, and the break is `missing_args`, `too_many_positional` or `raises`, or `rejected_kwarg` for a
    keyword this use passes.
- A use not read, answered `unknown`, or set apart as `failing_before` is **not flagged**: that is how the check on a
  pull request behaves.
- An upgrade **fails** when `check-upgrade` reports any break, on a labelled use or not (the command's exit code 1).

## Measures

Pooled over the six sets and per set, with 95% Wilson intervals:

1. **Breaks found:** flagged breaking uses / breaking uses.
2. **Working uses flagged:** flagged working uses / working uses. And precision.
3. **Clean upgrades the check fails:** clean upgrades with any break reported / clean upgrades. This counts breaks on
   uses nobody labelled (excluded by the probe, or beyond the 40-use cap), since a user sees those too.
4. **Labelled uses the reader reads:** read / labelled.

Reported beside them, with no bar: upgrades with a labelled break that the check fails; the same rates on read uses
only; `check_symbols` asked about each labelled use directly on the same index (`../holdout/score.py`'s rule), which
shows what the reader and the filter cost; splits by direction (`up`, `down`, `tmb`), kind of use and change type;
deprecations (working uses the probe found deprecated that the check lists, and the other way round; 2026-11 has no
deprecation labels); and every break reported, with the ones on unlabelled paths listed, not scored.

## The bar

Fixed now, pooled over the six sets:

| measure | bar |
|---|---|
| breaks found | ≥ 90% |
| working uses flagged | ≤ 1% |
| clean upgrades the check fails | ≤ 5% |
| labelled uses the reader reads | ≥ 95% |

Asked about each labelled use directly, 2026-11f's first run found 96.7% of its breaks and flagged 0.1% of its
working uses (the README's "Why the upgrade check" table), so the bar leaves the reader and the filter some room and
no more. The clean
upgrade bar is a check a team keeps turned on: one false failure in twenty clean updates at most.

**If all four are met,** Phase 3 (the GitHub Action, DT-GTM-06) starts on this command as it is. **If one is
missed,** the Action waits; the misses are worked on as patterns by the holdout rule (two or more cases, or any false
alarm), and the run after a fix is reported as a second, in-sample run, never in place of this one.

## Running it

```bash
uv run deptime index pull
uv run python bench/upgrade-check/run.py ~/.cache/deptime-work/qa21/sources \
    --out bench/upgrade-check/results-<date>.md --json ~/.cache/deptime-work/qa21/rows.json
```
