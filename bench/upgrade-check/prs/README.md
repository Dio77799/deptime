# The upgrade check on real update pull requests (DT-QA-22)

**Purpose:** measure the check the GitHub Action runs (`deptime check-upgrade --base`) on dependency update pull
requests that Dependabot and Renovate opened in public projects: updates nobody designed a fix from. DT-QA-21 and
DT-QA-24 ran the check on the six holdout sets, which are in-sample for `check_symbols`, with the versions handed to
it. Here the check reads the version change from the pull request's own files, as the Action does, on projects and
releases no earlier set has seen.

Everything on this page, `find_prs.py` and `check_prs.py` was committed before the pull requests were collected. The set is
committed before DepTime runs on it, scored once, and reported whichever way it comes out.

**What was seen first.** Before this page was written, GitHub's search was asked how many pull requests match the
search below for numpy and openai since 2026-09-15 (2,382 and 9,377 from Dependabot; 259 from Renovate for numpy). No
pull request was opened, picked or read.

## The set

### Which pull requests (`find_prs.py`)

For each of the 53 covered packages, GitHub's issue search, newest first, created from **2026-08-15 to 2026-11-14**,
public repositories only:

- Dependabot: `is:pr is:public author:app/dependabot "Bump <name> from" in:title`;
- Renovate: `is:pr is:public author:app/renovate "dependency <name> to" in:title`;

with `<name>` the package's name and, where it differs, the same with `_` for `-` (`huggingface_hub`). The two lists
are merged by creation time, newest first, and read up to 1,000 results each (GitHub's limit). A pull request
**qualifies** when, checked in this order:

1. **One package, named:** the title is a single-package update of this package (`Bump <name> from <a> to <b>[ in
   /<dir>]` after an optional `type(scope):` prefix; `Update dependency <name> to v<b>`, likewise), not a group
   update. The versions are Dependabot's title's, or the row for the package in Renovate's table in the body
   (`` `==1.2.3` -> `==1.3.0` ``); a range there (`^1.2`, `>=1.2`) doesn't qualify.
2. **Indexed releases:** both versions are final releases, the old one older, and both are in DepTime's published
   index on the day of collection (`deptime index pull`).
3. **New code:** the repository isn't a fork, isn't DepTime's own, isn't in one of the six holdout sets, and hasn't
   already given this package a pull request here (one per repository and package: the newest).
4. **A Python update:** the pull request changes at least one Python manifest: `requirements*.txt`, a `.txt` file
   under a `requirements*` directory, `*.in`, `pyproject.toml`, `uv.lock`, `poetry.lock`, `pdm.lock`, `Pipfile`,
   `Pipfile.lock`, `setup.py` or `setup.cfg`. Whether DepTime reads that file is measured, not required.
5. **Code that uses it:** GitHub serves the tarballs of the base and head commits, and the project directory (below)
   at the head has at least three uses of the package (`../../holdout/uses.py`, the holdout's own reader, as in its
   pinned rule) and isn't the package's own source.

The first **three** qualifying pull requests that cross a major version (the first number changes; for `0.x`, the
second) and the first **three** others are kept per package: at most 318. Major updates are kept apart because most
breaks are there and most update pull requests aren't major; each stratum is reported on its own as well as pooled.

**The project directory** is the one the Action would be pointed at (its `path` input): for Dependabot, the title's
`in /<dir>` (the repository's root when there is none); for Renovate, the deepest directory holding every Python
manifest it changes, or that directory's parent when its name starts with `requirements`.

`selection.json` records the searches, the cutoff and every candidate read with the reason it was skipped.

### What a case holds (`upgrades.jsonl`)

One line per pull request, in the holdout's format (`source: "pr"`): the repository, number, bot, state (open,
merged or closed), base and head commits, project directory, package, `from` and `to`, stratum, and the uses
`uses.py` reads at the head under the project directory, at most 40 by the holdout's hash rule.

**Sources:** each commit's GitHub tarball, keeping only `.py`, `.txt`, `.toml`, `.cfg`, `.lock`, `.in` and
`.gitignore` files, read as data. Nothing here runs a project's code.

### Labels (the probe, never DepTime)

As for a holdout set (`../../holdout/README.md`, "Labels"), unchanged: `../../holdout/envs.py` and `labels.py` on this
directory, the probe through `.github/workflows/holdout.yml` (with `SET` pointed here), each package version installed
with PyPI as of 30 days after its release or the cutoff (2026-11-15), whichever comes first. Breaks found by binding a
call are checked by hand against the library's source at `to` (`label-overrides.json`). Labels are committed before
the scored run.

## The scored run (`check_prs.py run`)

For each pull request: a local git repository with two commits, the base's files and then the head's (the tarballs
above), and

```
deptime check-upgrade <project directory> --base HEAD^ --format json
```

as the Action runs it, against the published index on the day of the run (its build time is in the results), with
`DEPTIME_OFFLINE=1` and no suppressions. Every package the check reports is kept, not only the titled one: a lockfile
update often moves other packages too, and a user sees their breaks.

## Matching answers to labels

As DT-QA-21 matches them (`../README.md`), on the titled package:

- a use is **read** when DepTime's reader reads its path in the project directory;
- a use is **flagged** when a break the check reports for the titled package has its path and is `missing`, or the
  use is a call and the break is `missing_args`, `too_many_positional`, `raises`, or `rejected_kwarg` for a keyword
  it passes;
- a pull request whose update the check doesn't read (below) flags none of its uses.

## Every break, checked (the audit)

Every break the check reports, on any package, is put to the probe at its `to` version, as DT-QA-25 did
(`../audit/README.md`, "Each break's verdict" and "Hand checks", unchanged): true, false or can't tell; a call break
the probe finds by binding is true only once the library's source at `to` confirms it (`audit/hand-checks.json`),
and hand checks stop where they can't change a pull request's verdict. A pull request the check fails is
**justified** when a break is true, **false** when none is true and one is false, **undetermined** otherwise. The
audit's environments are built from the scored run's output, after it.

## Measures and the bar

Pooled over the set, with 95% Wilson intervals:

| measure | bar |
|---|---|
| 1. **updates read:** pull requests whose titled change (package, `from`, `to`) the check reads from the files | ≥ 90% |
| 2. **breaks found:** flagged breaking uses / breaking uses | ≥ 90% |
| 3. **working uses flagged:** flagged working uses / working uses | ≤ 1% |
| 4. **pull requests failed with no confirmed break:** (false + undetermined) / pull requests | ≤ 5% |
| 5. **labelled uses read:** read / labelled uses | ≥ 95% |

Measure 2 gets a verdict only with at least 20 breaking uses; with fewer it is reported as too few to judge.

The bars are DT-QA-21's, with measure 4 counting only failures no confirmed break justifies (DT-QA-25's rule) over
every pull request, since a team sees the check on all of them, and measure 1 added: an update the check can't read
is one it can't check.

Reported beside them, with no bar: each measure by stratum (major, other), by bot and by state; breaks found among
pull requests whose update was read; pull requests with a labelled break that the check fails; `check_symbols` asked
about each labelled use directly (`../../holdout/score.py`'s rule) on the same index; deprecations as DT-QA-21 reports
them; for each update not read, the manifest files it changed; merged pull requests the check fails with a
confirmed break; and every break reported, with its verdict.

**Whichever way it comes out,** the numbers go in the README with 0.2.0 (DT-OSS-16). Every false break is a wrong
answer and gets a backlog item. **If measure 4 is missed,** the false breaks are fixed before 0.2.0. Other misses are
worked on as patterns by the holdout rule (two or more cases, or any false alarm); a run after a fix is reported as a
second, in-sample run, never in place of this one.

## Running it

```bash
uv run deptime index pull
W=~/.cache/deptime-work/qa22
uv run python bench/upgrade-check/prs/find_prs.py $W            # resumable; then commit selection.json, upgrades.jsonl
uv run python bench/holdout/envs.py bench/upgrade-check/prs    # push to spike/holdout with SET pointed here
gh run download <run id> -p 'holdout-*' -D $W/probe-labels
uv run python bench/holdout/labels.py bench/upgrade-check/prs $W/probe-labels   # then commit the labels
uv run python bench/upgrade-check/prs/check_prs.py run $W --json $W/rows.json          # the scored run, once
uv run python bench/upgrade-check/prs/check_prs.py audit-envs $W/rows.json $W          # push with SET=.../prs/audit
gh run download <run id> -p 'holdout-*' -D $W/probe-audit
uv run python bench/upgrade-check/prs/check_prs.py score $W/rows.json $W/probe-audit \
    --out bench/upgrade-check/prs/results-<date>.md
```
