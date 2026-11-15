# A model alone on the holdout tracebacks (DT-QA-16)

**Purpose:** give the traceback score something to compare with. DepTime's first runs name the right package, name
and breaking release for 86.9% of the six holdout sets' tracebacks (166 of 191). This puts the same tracebacks to a
language model that has no tools and answers from memory, and scores its answers the same way.

Everything on this page, `system-prompt.txt`, `ask.py`, `grade.py` and `boundaries.json` was committed before any
model was asked. It is run once and reported whichever way it comes out. It is an evaluation only: DepTime's own
answers still involve no model (ADR 0006).

## What is asked

- **Cases:** the 191 tracebacks in `bench/holdout/*/tracebacks.jsonl`, the ones the README's first-run row counts.
- **Input:** what `explain_error` gets, and nothing else: the installed versions the case records, and the traceback.

  ```
  Installed versions:
  <package>==<version>
  ...

  Traceback:
  <the traceback>
  ```

- **System prompt:** `system-prompt.txt`, word for word. It asks for one JSON object in the scorer's fields: the
  package, the name (in the form `explain_error` writes it), the kind of change (the benchmark's six issues), both
  sides of the boundary, and up to three replacements. Its examples are an invented library, so no case is in it.
- **Models:** the `haiku`, `sonnet` and `opus` aliases of the `claude` command-line tool, which on 2026-11-14 are
  Claude Haiku 5.5, Claude Sonnet 5.5 and Claude Opus 5.5. Each reply records the model ID that answered. Anthropic's
  [models page](https://platform.claude.com/docs/en/about-claude/models/overview) gives all three a training data
  cutoff of June 2026.
- **Runs:** three per model, since a model can answer the same question differently each time. Reported as a range.

## How the model is called

One call per case (`ask.py`), from a new empty folder outside this repository:

```bash
claude --print --model <alias> --effort high --tools "" --system-prompt "$(cat system-prompt.txt)" \
  --safe-mode --strict-mcp-config --disable-slash-commands --no-session-persistence \
  --output-format stream-json --verbose < message.txt
```

- `--tools ""` leaves the model no tool: it can't search, read a file or run code. `--safe-mode`,
  `--strict-mcp-config` and `--disable-slash-commands` keep out instruction files, plugins, skills and MCP servers.
  `ask.py` stops if a call reports any tool, or an API key in use.
- The command-line tool adds a little around the prompt: one line naming its agent SDK, and a block with the working
  directory (the empty folder), the platform, the model's name and knowledge cutoff, today's date and the signed-in
  account. Nothing from this repository reaches the model.
- The effort level is `high` for all three models, set in the call so that it doesn't depend on a default.
- `ask.py` runs without the caller's `ANTHROPIC_*` and `CLAUDE*` environment variables, so a call made from inside
  another Claude Code session behaves like one made from a terminal.

## Scoring

`grade.py` turns each reply into the finding `explain_error` would have returned and gives it to the benchmark's
own scorer, `deptime.bench.score_case` (`bench/README.md`):

- **Root cause:** the package, the end of the name (the reply's `symbol` or `defined_at`) and the issue all match.
- **Boundary:** `last_version_with` (or `first_version_with`, for a name not yet added) starts with the case's
  prefix.
- **Headline:** root cause and boundary, the measure behind DepTime's 86.9%.
- **Replacement:** the case's replacement is in one of the reply's first three, on the 85 cases that have one.

Three allowances, each of which can only raise a model's score:

1. **Either side of the boundary counts.** A case records the last release with a name; a model may as correctly
   say when it went. So a right root cause also gets the boundary when the reply's `first_version_without` is the
   first release without the name (for a name not yet added: when its `last_version_without` is the last release
   before the one that added it). `boundaries.json` holds those releases, read from PyPI's release lists by
   `boundaries.py`. The match is as loose as the case's own prefix: where the case says `0.27`, `0.28.0` and `0.28.1`
   both name the release after the 0.27 series; where it gives three numbers, all three must match.
2. **An import name counts as the package:** `sklearn` for scikit-learn.
3. **Form isn't marked:** a code fence or a sentence around the JSON, backticks, `f()` for `f`, `f(strict=)` for
   `f(strict)`, and `v2.31.0` or `2.31.x` for a version are read as meant.

A reply that isn't a JSON object, or has no package or name or an issue outside the six, is a wrong answer.

## Before and after the training cutoff

A model can only know a break from memory if the release that made it came out before its training data ends.
`boundaries.json` records the day each case's breaking release was uploaded to PyPI (the first release without the
name, or the first with a name not yet added). The results give the cases apart: 169 whose breaking release came
out by 2026-06-30, and 22 from 2026-07-01 on, which none of the three models can have seen.

## Order of work

1. This protocol is committed.
2. **A trial of ten cases** per model, the first ten in the order of the sha256 of the case ID (`ask.py --limit 10`).
   It checks the plumbing: the call works, replies parse, how long a case takes. If it shows the prompt or the rule
   must change, the change is committed before going on and the results say so; otherwise the ten replies are the
   first ten of run 1.
3. The three runs, then `grade.py` writes the results file.

```bash
uv run python bench/model-alone/boundaries.py            # rebuild boundaries.json from PyPI
uv run python bench/model-alone/boundaries.py --check    # the probe's checks agree with it
uv run python bench/model-alone/ask.py --model haiku --run 1 --limit 10
uv run python bench/model-alone/ask.py --model haiku --run 1
uv run python bench/model-alone/grade.py > bench/model-alone/results-<date>.md
```

## What this doesn't measure

- **A model with tools.** A coding agent can read the installed package's source or search the web, which this
  leaves out on purpose. Whether an agent fixes more breakages with DepTime than without is DT-QA-05.
- **Other models.** Three models from one vendor, all with the same training cutoff.
- **Unseen cases, for the model.** The tracebacks come from public GitHub issues, so a model may have read the
  issue itself, answer included, where the break is older than its training data.

## Result

Added after the run; everything above is as it was committed before it. The run of 2026-11-14 is in
[results-2026-11-14.md](results-2026-11-14.md), with the replies it scores in `answers/`. `grade.py` gained one
table afterwards, "Where the installed release is the boundary", to explain the result; it changes no mark.
