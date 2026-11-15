# DepTime backlog

**Active again since 2026-11-15: the upgrade check.** Maintenance mode ran from 2026-11-13. It ended when the
model comparisons (DT-QA-16 to DT-QA-20) showed where DepTime adds the most: deciding, with no model in the loop,
which of a project's code a dependency update breaks. Everything done before 2026-11-13, with its measurements, is in
[docs/backlog-archive.md](docs/backlog-archive.md), which is frozen.

**How to read this**
- **IDs** look like `DT-<EPIC>-NN` and are referenced from the docs and code. Put the ID in commit messages and PR
  titles. An ID that isn't on this page is in the archive.
- **Priority:** `P0` blocks a release · `P1` needed · `P2` nice to have · `P3` rare.
- **Size:** `S` ≤ ½ day · `M` 1–2 days · `L` 3–5 days.
- **Direction:** free, open source (MIT), local-first ([ADR 0007](docs/adr/0007-open-source-local-first.md)).
- **Keeping this page short:** one line per change. Measurements go in `bench/**/results-*.md` and in commit bodies,
  not here.

---

## Current state: public alpha, v0.1.17

- **Released:** 0.1.17 (2026-11-15) is on PyPI, the MCP Registry and GitHub: Phase 1's fixes (DT-CORE-63, -64,
  -67), the first code change since 0.1.13.
- **Index:** 53 packages and 6,800 releases on 2026-11-13 (`SNAPSHOT_FORMAT` 26, schema 2); `index.sqlite.xz` is
  51.0 MB and the `.gz` 78.5 MB. `build-index` runs at 04:17 and 16:17 UTC, replaces the rolling `index` release and
  signs it. A build with no extraction change usually takes under 20 minutes; a `SNAPSHOT_FORMAT` bump means one cold
  build of about 3.7 hours.
- **Checks that run without anyone:** `ci` on every push (502 offline tests), and `bench` on every code change and
  every published index. `bench` fails on a benchmark drop of more than 2 points or a false-positive rate up by more
  than 1, and on the published index itself (`tests/test_golden.py`, DT-QA-03): older than 48 h, a package's newest
  release on PyPI for more than 24 h without being indexed, or a Tier A package's newest release without the names
  its documentation uses.
- **How well it works:** the README's table, which leads with first runs on unseen cases. Across the six holdout sets'
  first runs, `explain_error` names the right package, name and release for 86.9% of tracebacks (166/191), and
  `check_symbols` has flagged under 1% of working code for four sets running while finding 96.6% or more of the
  breaks. A model alone, with no tools, scores 66% to 84% on the same tracebacks (DT-QA-16), and Claude Sonnet 5.5 alone
  finds 90.8% of 2026-11f's breaks while flagging 0.2% of its working code (DT-QA-18).

| Milestone | Exit criterion | Status |
|---|---|---|
| **M0 Spikes** | S1 go/no-go (false-absent ≤ 10%); S2–S7 answered | S1 to S4 passed (S1 at 1.2%); S5 done but for the GUI clients; S6 and S7 open, below |
| **M1 Local alpha** | Public repo; index published; `uvx deptime mcp` works from PyPI; benchmark ≥ 70% | Met: every holdout's first run is above 70% |
| **M2 Distribution** | Registries, plugin, snippets, demo GIF, 5 rename-map pages | Registries, plugin, pages and the demo done; the hosting is below |
| **M3 Optional hosted** | Public endpoint for web clients | Not planned |

## Why the upgrade check

On the 2026-11f holdout's upgrades (2,265 uses of covered packages in 171 upgrades of real projects, labelled by
running them; first runs, abstentions counted as not flagged):

| Who decides | Breaks found | Working code flagged | Clean upgrades with a false alarm |
|---|---|---|---|
| DepTime by itself (`check_symbols`) | 96.7% | 0.1% | 0 of 144 |
| Claude Sonnet 5.5 alone | 90.8% | 0.2% | 0 of 144 |
| DeepSeek V4.1 Flash alone | 80.9% | 2.7% | 18 of 144 |
| Qwen3.5 9B alone | 30.9% | 15.4% | 74 of 144 |
| Qwen3.5 9B with DepTime's tools | 82.2% | 4.5% | 25 of 144 |

- DepTime by itself already answers at the level a check on pull requests needs, offline, free and the same every
  time. No command runs it over a whole project yet.
- A model in the loop costs precision: Qwen with the tools re-decided uses DepTime had right. So the check decides
  with DepTime alone, and a model only drafts the fix afterwards, in the user's own agent (ADR 0006: no model inside
  DepTime).
- The traceback work of maintenance mode stands: first runs on six unseen sets stayed between 77% and 92% while each
  set found new rare shapes, so accuracy work on rare shapes still waits for a report.

## Rules

1. **A protocol before every first score.** Each new measurement is fixed and committed before its first scored run,
   as DT-QA-16 to DT-QA-20 were, and reported whichever way it comes out.
2. **New holdouts only for the upgrade check** (DT-QA-22). The six traceback and use sets stay as regression checks;
   DT-QA-13 stays closed.
3. **A report comes first for the long tail.** Held items move up when someone reports the wrong answer they cause,
   or a scheduled check fails; the report becomes a benchmark case before the fix.
4. **Abstain before adding a reader.** `unknown` or `not_covered` with the reason first (Invariant 2); then a
   `[[package.served]]` entry in `coverage.toml`; new extraction code only for a shape several packages share.
5. **Batch extraction changes.** Fixes that need a `SNAPSHOT_FORMAT` bump share one cold build.
6. **Release when a feature lands.** No hosted instance ([docs/05](docs/05-self-hosting.md) stays for self-hosting),
   and no model call inside DepTime (ADR 0006).

## Upkeep

What still needs a person, about once a month:

- **Merge Dependabot's pull requests** when `ci` and `bench` are green. griffe is kept out of the grouped update on
  purpose: its upgrades change what extraction reads, so look at the benchmark first.
- **Keep the schedule alive.** GitHub disables scheduled workflows in a public repository after 60 days without
  repository activity. A merged pull request counts. If the index stops updating, re-enable `build-index` in the
  Actions tab.
- **A red `bench` run after a build means the index is behind,** or a new release dropped a documented name: the
  checks above ran on it. A green build can still carry a release over when its download or snapshot fails
  (Invariant 6); `bench` catches that once the release is a day old.

## To do

In order. The first line of each phase is what it delivers.

**Phase 2, the command (DT-CORE-66, DT-CORE-58).** `deptime check-upgrade` answers "what does this update break in my
code?" from a project directory.
- [ ] **DT-CORE-66**: Read a dependency change from a project · `P1` `M`
  - The packages and versions before and after, from `uv.lock`, `poetry.lock`, `requirements*.txt` or
    `pyproject.toml` pins: either two revisions of the files (a pull request's base and head) or the current file
    and a target version. Never imports or installs anything (Invariant 1).
- [ ] **DT-CORE-58**: `deptime check-upgrade [path] [--base REV] [--package P --to V]` · `P1` `M` · deps: CORE-66
  - Reads every `.py` file under the path with DepTime's own reader (`snippet.py`, not the benchmark's
    independent `bench/holdout/uses.py`), groups the uses by covered package, and runs `check_symbols` at the new
    version for each changed package. Reports, per break, the file and line, what's missing, the release that removed
    it and the replacement candidates with evidence; uses answered `unknown` are listed apart and never fail it.
    Markdown and JSON output; exit code 1 only on a confirmed break. Folds in **DT-CORE-59**: uses deprecated at the
    new version are listed as warnings.
- [ ] **DT-QA-21**: Score the command end to end on the holdout projects · `P1` `M` · deps: CORE-58
  - The six sets' pinned upgrades name each repository and commit: check them out, run `check-upgrade` with the
    set's `from` and `to`, and score its breaks against the probe's labels. Also how many of the set's labelled uses
    DepTime's reader finds. Protocol first, with the bar written in it.

**Phase 3, the GitHub Action (DT-GTM-06).** A check on Dependabot and Renovate pull requests.
- [ ] **DT-GTM-06**: `action.yml` for update pull requests · `P1` `M` · deps: CORE-58, QA-21
  - On a pull request that changes a lockfile or requirements file: pull the index (cached), run `check-upgrade
    --base` against the base branch, write the report to the job summary with an annotation per broken line, and fail
    the check only on confirmed breaks. Dependabot's pull requests get a read-only token and no secrets, so it must
    work without writing a comment; an optional comment goes through a separate `workflow_run` job, never
    `pull_request_target` with the pull request's code checked out.
  - Runs on DepTime's own Dependabot pull requests first (httpx, pydantic, mcp and others are covered packages).
- [ ] **DT-QA-22**: A fresh set of real update pull requests · `P1` `M` · deps: GTM-06
  - Recent Dependabot and Renovate pull requests in public repositories that bump a covered package, collected by a
    rule fixed in advance and labelled by the probe, scored once: the first measure on updates nobody designed a fix
    from.

**Phase 4, the fix (the model's part, outside DepTime).**
- [ ] **DT-CORE-68**: A `check_upgrade` MCP tool · `P2` `S` · deps: CORE-58
  - One call, one answer, as `explain_error` is for a traceback: the package, the two versions and the code (or a
    path), returning each break with its replacement. A new tool name, so the contract only grows (Invariant 3).
- [ ] **DT-GTM-07**: "Fix what DepTime found": the plugin and the report hand an agent the confirmed breaks · `P2` `S`
  · deps: CORE-68
  - The Action's report ends with a block an agent can act on, and the Claude Code plugin gains a command that runs
    `check_upgrade` and asks the agent to fix exactly those lines. The model writes the fix; DepTime decides what is
    broken.
- [ ] **DT-QA-23**: Qwen3.5 9B with the new tools on the upgrade checks · `P2` `S` · deps: CORE-67, CORE-68
  - DT-QA-20's upgrade half again, with `check_upgrade` offered: does one answer per upgrade keep DepTime's
    precision? Protocol first.

**Phase 5, release.**
- [ ] **DT-OSS-16**: Release 0.2.0 with the command, the Action and the tool · `P1` `S` · deps: GTM-06, QA-21
  - README: the check leads "What it does", with DT-QA-21's numbers (and DT-QA-22's once scored).
- [ ] **DT-OSS-17**: The path to 1.0 · `P2` `M` · deps: OSS-16
  - A review of every tool parameter, result field and CLI option (last chance to rename without a major version);
    the GUI clients checked or listed as not covered (DT-SPIKE-05, DT-SPIKE-07); the 1.0 promise in CHANGELOG.md's
    versioning section (what's frozen, how something is retired, supported Pythons, what the index promises).

## Done since 2026-11-13

- [x] **DT-CORE-67** (2026-11-15): `check_symbols` reads `timeout=` as `timeout` and leaves out `_` and empty names,
  saying so in `note`. DT-QA-23 measures what it does for a small model.
- [x] **DT-CORE-63**, **DT-CORE-64** (2026-11-15): backticked keywords, a message continued on the next line, Django's
  `import_string` message, `X.init()` tried as `X.__init__`, and a keyword a removed `**kwargs` took reads
  `param_removed`. Three of 2026-11f's four cases now pass (the 191 holdout tracebacks: 184, in-sample); selenium's
  finds the right release on three same-named `WebDriver` classes, which `note` lists, and stays a known gap: its
  line names no browser.
- [x] **DT-QA-20** (2026-11-15): Qwen3.5 9B with DepTime's five tools, protocol committed first. Tracebacks 86.4%
  (alone 18.8%, DepTime by itself 94.8% now); upgrades 82.2% of breaks found with 4.5% of working uses flagged (alone
  30.9% and 15.4%) (`bench/model-alone/with-tools/results-2026-11-15.md`).
- [x] **DT-QA-19** (2026-11-15): two cheaper models alone, through OpenRouter, protocol committed first. Tracebacks:
  DeepSeek V4.1 Flash 59.2%, Qwen3.5 9B 18.8% (DepTime 86.9%). Upgrades: DeepSeek 80.9% of breaks found with 2.7% of
  working uses flagged, Qwen 30.9% and 15.4% (DepTime 96.7% and 0.1%). The free models were busy and are left for
  another day (`bench/model-alone/cheaper-models.md`).
- [x] **DT-QA-18** (2026-11-15): the same comparison for the upgrade checks. The 2026-11f holdout's 2,265 uses put
  to Claude Sonnet 5.5 with no tools, one run, protocol committed first: 90.8% of breaks found and 0.2% of working uses
  flagged, against 96.7% and 0.1% for DepTime's first run; Claude Haiku 5.5, 73.7% and 0.3%
  (`bench/model-alone/upgrades/results-2026-11-15.md`).
- [x] **DT-QA-16** (2026-11-14): a model-alone baseline beside the traceback score. The six sets' 191 tracebacks,
  put to three Claude models with no tools under a prompt and rule committed first: 66% to 84% against DepTime's
  86.9%, with the models ahead on naming the change and its replacement and DepTime ahead on the release
  (`bench/model-alone/results-2026-11-14.md`). The README has the row.
- [x] **DT-GTM-04** (2026-11-14): the Claude Code plugin runs `uvx deptime==<release>` and names its icon in the
  manifest, as Anthropic's plugin directory requires; a test keeps the pin at the released version.
- [x] **DT-QA-14** (2026-11-14): closed without code. The check it asked for, an alert when the index falls behind,
  already runs: `bench` runs DT-QA-03's tests on the published index after every build (59 of the last 60 such runs
  passed; today's ran 82 tests).
- [x] **DT-OSS-02** (2026-11-13): README proof. An animated demo drawn from the real answer (`tools/demo_svg.py`),
  "How well it works" as four first-run numbers with the full table in `bench/README.md`, a limits section and a
  status line.

## Optional, once

One-off measurements and finishing touches. None is needed for upkeep, and none starts a series.

- [ ] **DT-QA-05** with **DT-SPIKE-06**: does an agent fix more dependency breakages with DepTime, and does it call
  it unprompted? · `P2` `L` (pilot `M`)
  - The one question the benchmarks don't answer, and the one DT-QA-16's result points to: a model alone already
    names most of these changes, so what counts is whether an agent does better with the tool. The pilot is as
    designed in the archive: about 20 covered tasks × 2 arms × 3 runs, success by each task's own tests, the pass
    bar written down before the run. One run, reported in the README whichever way it comes out.
- [ ] **DT-QA-17**: Tracebacks that aren't version breaks · `P2` `M`
  - All 401 traceback cases are real breaks, so nothing measures how often `explain_error` blames a release for an
    error with another cause (a typo, a broken install, the project's own bug). About 30 such errors on covered
    packages, collected by the benchmark's rules and scored once. The upgrade checks already have this measure
    (the working uses).
- [ ] **DT-QA-15**: The same for accuracy: S1's runtime probe on each package's newest release · `P3` `M`
  - Split from DT-QA-14. The probe (`bench/s1/`) runs a fixed plan of releases, up to 150 minutes a package, so
    following new releases means reworking it, and a check that needs upkeep defeats its purpose. DT-QA-03's
    documented names already watch each Tier A package's newest release. Wait for a report that shows decay.
- [ ] **DT-OSS-15**: Dependency updates that merge themselves · `P3` `S`
  - Needs auto-merge and required checks turned on for `main` (neither is set), which changes how every commit
    lands, and lets unattended updates into the environment that builds the signed index. The monthly upkeep merges
    them instead.
- [ ] **DT-GTM-02**: Host the generated rename-map pages (GitHub Pages) · `P2` `S`
- [ ] **DT-GTM-05**: Try the Cursor rule and the AGENTS.md snippet in a fresh project · `P2` `S`
- [ ] **DT-SPIKE-05**, **DT-SPIKE-07**: Cursor, VS Code and Claude Desktop, and a first run on Windows · `P2` `S`
  - Until then the README lists the GUI clients as not checked.
- [ ] **DT-OSS-14**: Publish the holdout sets as a benchmark · `P2` `M`

## Held

Known gaps, most with a case kept as `known_gap` in the benchmark. None is scheduled. A report moves its item to
"To do", and the groups are in the order to take them. Each item's detail is in the archive under its ID.
"Extraction" means the fix needs a `SNAPSHOT_FORMAT` batch (rule 4).

**Wrong answers** (a false alarm, a wrong finding or a wrong replacement)

| ID | Gap | Fix is in |
|---|---|---|
| DT-DATA-75 | Names in compiled extension modules read `missing` (scikit-learn's `tree._tree`) | extraction |
| DT-DATA-51 | Names computed at import time read absent (instructor's provider factories, chromadb's embedding functions) | extraction |
| DT-DATA-77 | A keyword only a decorator takes reads `never_existed` (huggingface_hub's `use_auth_token`) | extraction |
| DT-DATA-78 | openai 1.0's removed resources point to response types of the same name | curated hints, pairing rule |
| DT-DATA-73 | matplotlib 3.10's `cm.ScalarMappable` reads private, so its members read missing | extraction |
| DT-DATA-71 | Names a module only imports read public through a membership-test shim (instructor's `hooks`) | extraction |
| DT-DATA-72 | A name only a stub binds reads present where the runtime raises (numpy 2.0's `cast`) | extraction |

**Missed breaks and deprecations**

| ID | Gap | Fix is in |
|---|---|---|
| DT-CORE-60 | A module that became a function: names under it read `unknown` (fastmcp 3's `prompts.prompt`) | query |
| DT-CORE-34 | Constructor keywords of dataclasses and pydantic models; required arguments | query, extraction |
| DT-DATA-09 | Pydantic model fields as `__init__` keywords | extraction |
| DT-CORE-62 | `diff_versions` on a deprecation in force at both ends, or dropped before `to` | query |
| DT-CORE-61 | `diff_versions` is silent where `check_symbols` answers `unknown` | query |
| DT-DATA-76 | A name a lazy table serves doesn't carry its target's deprecation (langchain-community's `llms.OpenAI`) | extraction |

**Tracebacks with no finding**

| ID | Gap | Fix is in |
|---|---|---|
| DT-CORE-49 | A callable that only raises its own message | query |
| DT-CORE-65 | An attribute missing on an instance of the project's own subclass | query |
| DT-DATA-68 | Private methods' parameters, and the members of classes in internal modules | extraction |
| DT-DATA-02 | numpy names only compiled code registers (`ndarray.tostring`) | extraction |

**Missing replacements**

| ID | Gap | Fix is in |
|---|---|---|
| DT-CORE-40 | Replacements the package's own text states but the holdout tracebacks don't get | hint mining, curated hints |
| DT-DATA-70 | A renaming wrapper bound to the old name; "Deprecated name for the X keyword argument" | extraction |
| DT-DATA-79 | A table of removed keywords and their messages (fastmcp 3's `_REMOVED_KWARGS`) | extraction |
| DT-DATA-80 | A module's warning when imported | extraction |
| DT-CORE-04 | Signature-similarity "moved" heuristic | hint mining |

## Not planned

- **DT-QA-13** (the next holdout set): closed by rule 1.
- **DT-HOST-01 to 04** (a public hosted instance): running one is continuous work. The code for self-hosting stays.
- **DT-DATA-74** (hundreds of packages instead of 53): the build time and the checks grow with it.
- Parked as before: an npm/TypeScript index, a bulk dataset export, MCP resources for rename maps.

## Later

- **DT-CORE-57**: check code as it is written (a Claude Code hook after each edit), once `check-upgrade` and its
  reader are measured.
- **DT-DATA-81** (proposed): a sandboxed runtime floor for dynamic packages, so a name that runs reads `unknown` at
  worst, never `missing`. Needs ADR 0002 and Invariant 1 revisited first.
