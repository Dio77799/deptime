# Are the clean upgrades' failures real? (DT-QA-25)

**Purpose:** DT-QA-21's third measure, "clean upgrades the check fails", counts an upgrade as clean when every
*labelled* use works, and counts any break the check reports there as a false failure. Some of those breaks are on
uses nobody labelled: the probe excluded them, or the 40-use cap left them out, and 43 of DT-QA-21's 81 are
TimeMachine-bench upgrades, chosen because they break, whose breaking uses the holdout drops by design. So the measure
can't tell a false alarm from a real break the labels don't cover. This audit asks the probe about every break the
check reports on a clean upgrade, and measures the failures nothing confirms.

Everything on this page and `audit.py` was committed before the audit's first scored run. It is run once, on DT-QA-24's
output, and reported whichever way it comes out; DT-QA-21's and DT-QA-24's measures stand as they are, beside it.

**What was seen first.** Before this page was written, DT-QA-21's results listed every clean upgrade's breaks, and a
development run of DT-CORE-69 was looked at for the same upgrades with the reasons the holdout's labels give for those
paths: a mix of breaks the probe found failing at `to`, keywords only `**kwargs` takes, imports the probe couldn't
make, and at least one call the holdout checked by hand and found working (huggingface_hub's
`snapshot_download(local_dir_use_symlinks=)`). No break was put to the probe for this audit before this commit.

## What is run

- **Cases:** every break `check-upgrade` reports on a clean upgrade in DT-QA-24's run (`run.py --json`), as one use in
  the shape DepTime asked about it: the path; for a call, the most arguments any call passes by position and every
  keyword the calls pass; and whether it is read off an object a call built.
- **Ground truth:** `bench/holdout/probe.py`, unchanged, on the holdout's own environment for the package at `to`
  (`<set>/envs.json`: the same Pythons and date cutoff), through `.github/workflows/holdout.yml` with `SET` pointed
  here. The probe imports the package, so it runs only there: sandboxed, no network.

## Each break's verdict

From the probe's result for its use at `to`:

| break | true | false | can't tell |
|---|---|---|---|
| any | the path doesn't resolve (unless set on instances at run time: false) | | the import fails for another reason; the environment didn't install |
| `missing` | | resolves | |
| `raises` | built to fail | not built to fail | |
| `rejected_kwarg` | the keyword is absent, or positional-only | the keyword is a named parameter | only `**kwargs` takes it; no signature |
| `too_many_positional`, `missing_args` | doesn't bind, with "too many positional" / "missing a required" | binds | doesn't bind for another reason; no signature |

**Hand checks.** As the holdout does for its labels, a call break the probe finds by binding (`rejected_kwarg`,
`too_many_positional`, `missing_args`) is true only once the package's released source at `to` confirms it; until then
it is "can't tell". A "can't tell" break may be settled by hand from the source at `to`, recorded in
`hand-checks.json` with the file and line that show it, as `label-overrides.json` records the holdout's. A hand check
never overturns the probe's `false`. Hand checks are made only where they can change an upgrade's verdict: an upgrade
with a break already true needs none, and within an upgrade they stop at the first break confirmed true.

## Each upgrade's verdict

- **justified:** at least one break is true;
- **false:** none is true and at least one is false;
- **undetermined:** every break is "can't tell".

## The measure and the bar

**Clean upgrades whose failure no confirmed break justifies** (false + undetermined) / clean upgrades in DT-QA-24's
run, with a 95% Wilson interval: **at most 5%**, the same bar as DT-QA-21's third measure, now counting only failures
nothing confirms. Reported beside it, with no bar: the lower bound (false only), and every false break.

**If met,** Phase 3 (the GitHub Action, DT-GTM-06) starts. **If missed,** it waits, and the false breaks are worked on
first. Either way every false break is a wrong answer, so each gets a backlog item (the holdout rule: any false alarm
is a pattern).

## Running it

```bash
uv run python bench/upgrade-check/audit/audit.py envs ~/.cache/deptime-work/qa21/rows-qa24.json \
    ~/.cache/deptime-work/qa21/sources
# push to spike/holdout with SET: bench/upgrade-check/audit in holdout.yml; then
gh run download <run id> -p 'holdout-*' -D <empty dir>
uv run python bench/upgrade-check/audit/audit.py score ~/.cache/deptime-work/qa21/rows-qa24.json <that dir> \
    --out bench/upgrade-check/audit/results-<date>.md
```
