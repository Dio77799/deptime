# Tracebacks that aren't version breaks (DT-QA-17)

**Question:** when a traceback that looks like a version break has another cause (a typo, a broken install, a file
named like the package, the project's own bug), how often does `explain_error` blame a release anyway?

Every traceback in `bench/cases` and the six holdout sets is a real break, so nothing measures this yet. The upgrade
checks have the matching measure (working uses flagged); this is that measure for tracebacks.

This protocol was committed before any case was collected or scored. The set is scored once, and that first score is
the number to report, whichever way it comes out.

## The set

About 30 real tracebacks from GitHub issues, collected by these rules (the DT-QA-01 rules in `bench/README.md`,
except that the cause is *not* a change between releases).

**Where to look.** Each covered package's own GitHub repository (from its PyPI project URLs; a package whose issues
aren't on GitHub is skipped). Closed issues only, created on or before 2026-11-17, newest first:

```
repo:<owner>/<name> is:issue is:closed created:<=2026-11-17 "<text>"   sort: created, newest first
```

with `<text>` taken in this order: `has no attribute`, `cannot import name`, `unexpected keyword argument`,
`No module named`, `required positional argument`. These are the error shapes `explain_error` reads as possible
version breaks. For each query, the first 10 results are read in order.

**Order.** Packages in `coverage.toml` order (Tier A, then Tier B). Round 1 reads each package's queries in order and keeps its first qualifying case; if
the set has fewer than 30 cases after every package, round 2 keeps a second case per package, in the same order,
reading the results round 1 didn't. Collection stops at 30 cases, or when round 2 ends.

**A candidate qualifies when** all of these hold:

1. It has a traceback, or at least the final `SomeError: message` line, pasted as text.
2. The installed version of the package is stated in the thread (the issue template, a `pip freeze`, a lockfile, a
   maintainer's reply) and is an indexed release.
3. The thread settles the cause, through a maintainer's reply or the reporter's confirmed fix, and the cause is one
   of:
   - `never_existed`: a name, module or argument no release of the package has had (a typo, a name from another
     library, a hallucinated API);
   - `install`: a broken or partial install, a missing optional dependency or extra, two copies of the package, a
     stale build, fixed without changing any version;
   - `shadowing`: a local file or module named like the package or one of its modules;
   - `usage`: the project's own bug (the wrong object, a call in the wrong place), with the API unchanged;
   - `environment`: anything else outside the package's releases, such as a Python version the release doesn't
     support.
4. The library's source at the installed version agrees: the name or argument is there (or, for `never_existed`, was
   never in any indexed release), checked by reading the source, never by running DepTime.

**Skipped:** a cause that is a change between releases of any distribution (the package, a dependency, a plugin),
including a regression a later release fixed; a thread whose fix was upgrading or downgrading anything; a thread
that doesn't settle the cause; a traceback only in a screenshot. Each candidate read is recorded in `selection.json`
with its query and verdict, kept or the reason it was skipped.

**Privacy:** as DT-QA-01 (`bench/README.md`): usernames and project names in paths replaced, the path's shape kept;
no tokens, hostnames or `pip freeze`.

**Case format** (`cases.jsonl`): `id`, `source` (the issue URL), `traceback`, `installed` (`{package: version}`, as
the thread states them), `package`, `cause` (one of the five above), `evidence` (the comment that settles the cause,
quoted, and the source at the installed version that confirms it).

## Scoring (fixed now)

```bash
uv run deptime index pull --verify
uv run python bench/false-blame/score.py bench/false-blame/cases.jsonl > bench/false-blame/results-<date>.md
```

Each case is asked once, as an agent would ask it: `explain_error(traceback, installed_versions=installed)`, with
the default `min_confidence`, on the published index of the day (its build time goes in the results).

- **Blames a release** when any finding's `issue` says something changed between releases: `symbol_removed`,
  `symbol_not_yet_added`, `param_removed`, `param_not_yet_added`, `param_now_required`, `param_kind_changed` or
  `module_removed`.
- **Doesn't blame** otherwise: no finding, `never_existed`, `present_in_installed_version`, or only a note or
  `not_covered`.

Reported: the share of cases blamed, with a 95% Wilson interval (the headline), split by the top blaming finding's
`confidence` and by `cause`; and what the answers that don't blame said (finding kinds, abstentions), with
`never_existed` answers on `never_existed` cases counted apart as answers that point at the real cause. Each blamed
case is listed with the finding.

## What the result decides (fixed now)

There is no pass mark: nothing measured this before. Each blamed case is a wrong answer, so under the
[holdout rule](../holdout/README.md) (any wrong answer is worked on) each becomes a To-do item, one per cause in
DepTime. The result goes in `bench/README.md`'s table, not the project README.

After the first score the cases stay as a regression check. A fix designed from them can only be scored in-sample
on this set, and is reported as such.
