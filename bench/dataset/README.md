# DepTime API-change benchmark, v1

Two questions about Python library releases, asked on real code and real error reports, with answers settled by
running the code or reading the library's own source, never by a tool's guess:

1. **Uses.** A public project's code uses a library: a name it imports or reads, or a call with its shape (how many
   arguments by position, which keywords). If the library moves from one release to another, does that use still
   work? **24,873 uses, 1,287 of which break,** from 1,884 version changes in 1,339 public GitHub repositories,
   across 53 packages.
2. **Tracebacks.** A real traceback from a GitHub issue or Stack Overflow post, with the versions the reporter had
   installed. Which change in which library explains it: the package, the name, the kind of change, the last release
   that had it, and what replaces it? **393 real reports,** plus **30 tracebacks with another cause** (a typo, a
   broken install, a file named like the package), where the right answer is not to blame a release.

It is for anything that claims to catch or explain breaking changes in Python libraries: static checkers, upgrade
bots, coding agents, and language models answering from memory. It was collected in November 2026 to measure
[DepTime](https://github.com/cschmertz/deptime), and it is published so other tools can be measured the same way.

**Download:** `deptime-api-change-benchmark-v1.tar.gz` from the
[`benchmark-v1` release](https://github.com/cschmertz/deptime/releases/tag/benchmark-v1), with its sha256 beside it.

## What's in it

| File | What |
|---|---|
| `uses.jsonl` | One labelled use per line |
| `tracebacks.jsonl` | One traceback per line, with the expected answer |
| `score.py` | The scorer. Standard library only, Python 3.9 or newer |
| `predictions/` | Reference answers in the prediction format, and `about.json`, which says what each one is |
| `results.md` | Each file in `predictions/`, scored by `score.py` |
| `LICENSE` | MIT |

## Uses

### A record

```json
{"id": "2026-11f/pin-intelligolabs__coin-openai-up/faff881151fd11d7", "collection": "2026-11f",
 "upgrade": "2026-11f/pin-intelligolabs__coin-openai-up", "package": "openai", "from": "1.65.2", "to": "3.49.0",
 "direction": "up", "python": "3.11", "use": {"kind": "name", "path": "openai.OpenAI"}, "source": "pinned",
 "repo": "https://github.com/intelligolabs/CoIN", "commit": "b750a1a6...", "where": ["vlfm/vlm/openai_llm.py:4"],
 "label": "works", "deprecated": false}
```

| Field | Meaning |
|---|---|
| `id` | Stable: `<collection>/<upgrade>/<use key>` |
| `collection` | The set it was collected in (below) |
| `upgrade` | The version change it belongs to; one project, one package, one `from` and `to` |
| `package` | The distribution, as on PyPI |
| `from`, `to` | The code works with `from`; the question is whether it works with `to` |
| `direction` | `up` when `to` is newer, `down` when it is older (code written for a newer release than the one installed) |
| `python` | The Python the labels were checked on |
| `use.kind` | `name` (an import or an attribute read: `numpy.linalg.norm`) or `call` |
| `use.path` | The dotted path. For a call, the callable; a method reached through an instance is `Class.method` |
| `use.positional`, `use.keywords` | For a call: how many arguments it passes by position, and which keywords |
| `use.via` | `instance` when the code reaches the path through an object it built by calling a class (`client = httpx.Client()`, then `client.get(...)` is `httpx.Client.get`) |
| `source` | How the project was found: `pinned` (it pins the package in a requirements file), `pull-request` (an open Dependabot or Renovate update), `timemachine-bench` |
| `repo`, `commit`, `where` | The project, the commit its code was read at, and the `file:line` positions of the use |
| `pull_request` | For `source: pull-request`, the update's URL |
| `exercise` | `true` for the few upgrades picked because they have a use of a kind an earlier DepTime release got wrong (below) |
| **`label`** | **`works` or `breaks`: the answer** |
| `change` | For a break: `removed`, `param_removed`, `param_now_required`, `positional`, `symbol_not_yet_added` or `param_not_yet_added` |
| `detail` | For a break: the error the check raised |
| `deprecated` | For a use that works: whether the name itself is deprecated at `to`, by the evidence rule linked below |

A tool should read only the fields above `label`. `where`, `repo` and `commit` let it read the project's code.

### How the labels were made

Uses were read from each project's source with Python's `ast`, by a reader that shares no code with DepTime: names
imported or read from the package, and calls with their shape. Calls that unpack (`*args`, `**kwargs`) count as names
only, and at most 40 uses were kept per upgrade, picked by hash.

Then each release was installed from wheels in a throwaway virtual environment on a GitHub runner, with PyPI as it was
soon after the release (30 days later, in most collections), and each use was checked with no network: does the name resolve, and does the call's shape
bind to `inspect.signature`? A use that works at `from` and at `to` is `works`; one that works at `from` and fails at
`to` is `breaks`. Uses the check can't decide were left out: an import failing for another reason, no signature, a
keyword that only `**kwargs` takes, a use that already fails at `from`. 6,846 uses were left out this way, and the
probe's reasons are in each set's `labels.jsonl` in the repository. Every break found by binding a call was checked by
hand against the library's source at `to`, because a generated signature can disagree with what a class accepts; the
ones changed are in each set's `label-overrides.json`, each with the source that shows it.

The full rules, including the deprecation evidence, are in
[bench/holdout/README.md](https://github.com/cschmertz/deptime/blob/main/bench/holdout/README.md).

## Tracebacks

### A record

| Field | Meaning |
|---|---|
| `id` | Stable slug |
| `split` | `holdout`, `dev` or `not-api-change` (below) |
| `collection` | The set it was collected in |
| `source` | The issue or post it was cut from |
| `installed` | `{package: version}` as the reporter stated it (empty for the ten Python standard-library cases in `dev`) |
| `traceback` | The traceback as pasted, trimmed, with usernames and project names in paths replaced |
| **`expected`** | **The answer** (null for `not-api-change`) |
| `expected.package` | The distribution that changed |
| `expected.symbol_suffix` | The end of the name that changed: `Client.__init__(proxies)`, `module.name`, or a dotted module path |
| `expected.issue` | `symbol_removed`, `module_removed`, `param_removed`, `param_now_required`, `symbol_not_yet_added` or `param_not_yet_added` (the last two: code written for a newer release than the one installed) |
| `expected.last_version_with` | Optional: the last release (or release series, as a prefix: `"0.27"`) that still had it |
| `expected.first_version_with` | Optional, for `*_not_yet_added`: the first release or series that has it |
| `expected.replacement_contains` | Optional: text the replacement's name contains, from the library's changelog or migration guide |
| `evidence` | Where the expected answer comes from: changelogs, migration guides, maintainers' replies, and the library's source at the releases, read from the shipped wheels |
| `check` | For some `holdout` cases: a use the probe above confirmed works at the last release with it and fails after |
| `package`, `cause` | For `not-api-change`: the package the error mentions, and what really caused it (`never_existed`, `install`, `shadowing`, `usage`, `environment`) |

### How they were collected

Each report was collected by hand under fixed rules
([bench/README.md](https://github.com/cschmertz/deptime/blob/main/bench/README.md#collection-rules-dt-qa-01)): the
traceback is real, the installed version is stated in the thread and checked against the library's source, the
expected answer comes from the library's own documents or source, at most two reports per break, and no break a later
release reverted.

- **`holdout`** (191): six sets collected blind, before DepTime was run on any of them, each fixed in the repository
  first.
- **`dev`** (202): the reports DepTime was built from, collected from late October to mid-November 2026.
- **`not-api-change`** (30): one per package from closed issues, where the thread settles a cause other than a release
  change ([protocol](https://github.com/cschmertz/deptime/blob/main/bench/false-blame/README.md)).

## Collections

| Collection | Cut off | How the projects were picked | Uses (breaks) | Tracebacks |
|---|---|---|---|---|
| [2026-11](https://github.com/cschmertz/deptime/tree/main/bench/holdout/2026-11) | 2026-11-07 | Repositories pinning a package, moved to its newest release and to one a year older than the pin; and [TimeMachine-bench](https://github.com/tohoku-nlp/timemachine-bench)'s repositories, whose working uses only count | 3,730 (130) | 35 |
| [2026-11b](https://github.com/cschmertz/deptime/tree/main/bench/holdout/2026-11b) | 2026-11-08 | Pinned repositories, up and down, two per package | 2,682 (140) | 37 |
| [2026-11c](https://github.com/cschmertz/deptime/tree/main/bench/holdout/2026-11c) | 2026-11-09 | The same | 1,969 (128) | 35 |
| [2026-11d](https://github.com/cschmertz/deptime/tree/main/bench/holdout/2026-11d) | 2026-11-10 | The same, plus a few `exercise` upgrades | 2,455 (176) | 30 |
| [2026-11e](https://github.com/cschmertz/deptime/tree/main/bench/holdout/2026-11e) | 2026-11-10 | The same | 2,192 (140) | 28 |
| [2026-11f](https://github.com/cschmertz/deptime/tree/main/bench/holdout/2026-11f) | 2026-11-11 | The same | 2,265 (152) | 26 |
| [2026-11g](https://github.com/cschmertz/deptime/tree/main/bench/holdout/2026-11g) | 2026-11-16 | Pinned repositories, up only, up to ten per package | 6,241 (373) | |
| [prs](https://github.com/cschmertz/deptime/tree/main/bench/upgrade-check/prs) | 2026-11-15 | Open Dependabot (240) and Renovate (24) pull requests updating a covered package | 3,339 (48) | |
| [cases](https://github.com/cschmertz/deptime/tree/main/bench/cases) | 2026-11-15 | Reports DepTime was built from | | 202 |
| [false-blame](https://github.com/cschmertz/deptime/tree/main/bench/false-blame) | 2026-11-17 | Closed issues whose cause wasn't a release change | | 30 |

No repository is in two use collections. Each collection's directory has its own README with the counts, the
search (`selection.json`: every candidate and why each skipped one was skipped) and the probe's runs.

The 53 packages are DepTime's covered set: AI SDKs and agent frameworks (openai, anthropic, langchain, langgraph,
crewai, dspy, litellm, transformers, huggingface-hub, mcp, ...), web and data libraries (fastapi, pydantic, httpx,
django, numpy, pandas, polars, scikit-learn, sqlalchemy, ...) and their dependencies.

## Scoring

```bash
python score.py --uses my.uses.jsonl --tracebacks my.tracebacks.jsonl
python score.py --uses my.uses.jsonl --collection 2026-11f     # one collection only
```

**Use predictions:** one line per use, `{"id": "...", "breaks": true}`; `false` says it works and `null` abstains.

- **Breaks found:** breaks flagged, of all breaks.
- **Working uses flagged:** working uses flagged, of all working uses (lower is better).
- Also: how many flags are breaks, abstentions, and the share of upgrades where every use works that get at least one
  false alarm (the number that matters for a check on pull requests).

**Traceback predictions:** one line per traceback, `{"id": "...", "findings": [...]}`, best first, each finding
`{"package", "symbol", "issue", "last_version_with", "first_version_with", "replacements": [...]}` (and optionally
`defined_at`, the path where the object is defined, which counts like `symbol`). An empty list is no finding.

- **Root cause:** the first finding's package (compared as PyPI does), a name ending with `symbol_suffix`, and the
  same `issue`.
- **Root cause and boundary** (the headline): the root cause, and `last_version_with` (or `first_version_with`)
  starting with the expected one, where the case gives one.
- **Replacement:** for the cases that give one, `replacement_contains` is in one of the first three replacements.
- **Blamed** (`not-api-change`, lower is better): any finding whose `issue` is a release change.

Boundary and replacement count only when the root cause is right. A missing prediction counts as an abstention (uses)
or no finding (tracebacks); an id the data doesn't have is an error. Every rate comes with a 95% Wilson interval.

## Reference results

**Uses, 2026-11f** (2,265 uses, 152 breaks; abstentions count as not flagged):

| Who answers | Breaks found | Working uses flagged | Clean upgrades with a false alarm |
|---|---|---|---|
| DepTime `check_symbols`, its first run on the set (index of 2026-11-11) | 96.7% | 0.1% | 0 of 144 |
| Claude Sonnet 5.5 alone, from memory | 90.8% | 0.2% | 0 of 144 |
| DeepSeek V4.1 Flash alone | 80.9% | 2.7% | 18 of 144 |
| Claude Haiku 5.5 alone | 73.7% | 0.3% | 3 of 144 |
| Qwen3.5 9B alone | 30.9% | 15.4% | 74 of 144 |

The models' answers are in `predictions/`
([protocol and prompt](https://github.com/cschmertz/deptime/blob/main/bench/model-alone/upgrades/README.md)).

**Tracebacks, `holdout`** (191): DepTime's first run on each set, pooled, has the right root cause and boundary for
86.9%. Asked with no tools, Claude Opus 5.5 scored 83.2% to 83.8% over three runs, Claude Sonnet 5.5 81.7% to 82.7%,
Claude Haiku 5.5 66.0% to 68.6%, DeepSeek V4.1 Flash 59.2% and Qwen3.5 9B 18.8%
([results](https://github.com/cschmertz/deptime/blob/main/bench/model-alone/results-2026-11-15.md)). That study's
grader gave the models two allowances `score.py` doesn't: a boundary also counted when the answer named the release on
its other side, and a package also counted under its import name.

`predictions/deptime-<version>.*` are DepTime's answers today, on everything. They are **in-sample**: after each set's
first run, DepTime was fixed on its misses, and `dev` is what it was built from. Use them to compare answer by answer,
not as an out-of-sample score; `results.md` has them in full.

## Limits

- **What a label covers.** A use `works` when its name resolves and its call binds at `to`. A change in behaviour
  (another return value, a new exception at run time) is out of scope, and the 6,846 uses the check couldn't decide
  are left out, which tilts the set toward uses a signature can settle.
- **Not independent.** Many uses come from one project, and every `down` upgrade is an `up` upgrade's project moved
  the other way. The intervals are narrower than they should be; the per-upgrade figures are the check on that.
- **Few breaks in some places.** 1,287 breaks over 53 packages: 15 packages have none (numpy, django and fastapi
  among them), and `positional` and `param_now_required` have under ten each.
- **Chosen with DepTime in mind.** The packages are DepTime's covered set, and the `exercise` upgrades (24 of 1,884)
  were picked to test fixes to DepTime.
- **Published.** Everything here has been public since it was collected, and a model trained after November 2026 may
  have seen it. Each collection's cut-off dates its releases: a break released after a model's training cut-off is a
  fairer test of it.

## License and sources

MIT, like DepTime (`LICENSE`). Each traceback is quoted from the public issue or post in its `source` field, trimmed,
with personal paths replaced, and stays its author's. Projects are referred to by URL, commit and line; no project
code is included beyond the dotted names it uses.

v1 is frozen: ids and labels won't change. A corrected label or new collection will be a new version with its own
release.

## Rebuilding it

The data is built from files committed in [the DepTime repository](https://github.com/cschmertz/deptime), so one
commit always builds the same data files. DepTime's predictions also depend on the index they were made with, which
`predictions/about.json` names:

```bash
uv run python bench/dataset/build.py dist/deptime-api-change-benchmark-v1
uv run deptime index pull --verify && uv run python bench/dataset/predict_deptime.py dist/deptime-api-change-benchmark-v1
uv run python bench/dataset/predict_models.py dist/deptime-api-change-benchmark-v1
uv run python bench/dataset/build.py dist/deptime-api-change-benchmark-v1 --pack
```

`score.py` gives the same answer as the repository's own scorers: on DepTime's predictions it matches
`bench/holdout/score.py` use for use and `python -m deptime.bench` case for case, and on the models' it reproduces
the published 2026-11f table.
