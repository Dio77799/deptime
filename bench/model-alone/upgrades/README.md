# A model alone on the upgrade checks (DT-QA-18)

**Purpose:** give the upgrade checks something to compare with, as `../README.md` (DT-QA-16) did for the tracebacks.
On the 2026-11f holdout, DepTime's first run found every break `check_symbols` answered on (147 of 147) and flagged
2 of 2,047 working uses (`../../holdout/2026-11f/results-2026-11-11.md`). This puts the same uses to a language model
that has no tools and answers from memory, and scores its answers the same way.

Everything on this page, `system-prompt.txt`, `cases.py`, `ask.py`, `grade.py`, `released.json` and `shortcuts.md`
was committed before any model was asked. It is run once and reported whichever way it comes out. It is an evaluation
only: DepTime's own answers still involve no model (ADR 0006).

## What is asked

- **Cases:** the 2026-11f holdout's 171 upgrades of real projects that have a scored use: 2,265 uses, 152 that break
  and 2,113 that work, labelled by running them (`../../holdout/README.md`). These are the uses DepTime's first run
  was asked about, and the set the README's upgrade numbers come from. The other five sets aren't asked.
- **One call per upgrade.** The model gets what the two tools get, and nothing else: the package, the `from` and
  `to` releases, and the numbered uses, each a name (`openai.APIConnectionError`) or a call with its shape
  (`call: mistralai.Mistral(api_key=)`, `_` for each argument passed by position), marked "on an instance" where the
  code built the object by calling a class. Not the repository, its file paths or any label (`cases.py`).

  ```
  Package: <package>
  From: <from> (the code works with this release)
  To: <to> (the code will run with this release instead)

  Uses:
  1. <use>
  ...
  ```

- **System prompt:** `system-prompt.txt`, word for word. It asks for one verdict per use, `works`, `breaks` or
  `unknown`, as one JSON object. Its examples are an invented library.
- **Model:** the `sonnet` alias of the `claude` command-line tool, which on 2026-11-15 is Claude Sonnet 5.5, with a
  training data cutoff of June 2026. Each reply records the model ID that answered. One model, because a check on a
  dependency pull request would run a model a team can afford on every update, and on the tracebacks Sonnet scored
  within two points of Opus and far above Haiku.
- **Runs:** one. On the tracebacks, Sonnet's three runs were within one point of each other (156 to 158 of 191).
- **The call:** as `../README.md` describes it, made by the same code (`ask.py` takes `../ask.py`'s command and
  environment and swaps in this system prompt): signed in, no API key, every tool off, effort `high`, from a new empty
  folder.

## Scoring

`grade.py`, beside DepTime's first run as `../../holdout/2026-11f/baseline.json` records it (written once, by the
first scoring in `cb2a82c`):

- A use is **flagged** when the model says `breaks`. `unknown` is an abstention, as DepTime's `unknown` is.
- **A use with no verdict** (a reply that isn't a JSON object, a number left out, or a word other than the three)
  is an abstention too, and the results count these apart from `unknown`. Form isn't marked: a code fence or text
  around the object, case and spaces, a list of verdicts in order, and `work`, `break` or `broken`.
- **Recall** (breaks flagged), **false-positive rate** (working uses flagged) and **precision** (flags that are
  breaks), with 95% Wilson intervals (`../../holdout/score.py`'s), twice: with abstentions counted as not flagged
  (how a check on a pull request behaves, and the table to read first) and with abstentions apart (as the holdout's
  own results count them).
- **Per upgrade:** the share of the 144 upgrades where every use works that get any false alarm, and of the 27 with
  a break where at least one is found.

**Splits, fixed now:**

- **Direction:** `up` (107 upgrades to the newest release at the set's cutoff) against `down` (64 to a release at
  least a year older than the pin: code written for a newer release than the one it gets, where the breaks are names
  or parameters not yet added).
- **The newer of the two releases against the training cutoff:** uploaded to PyPI by 2026-06-30, or from 2026-07-01
  on (`released.json`, from the index). The newer release holds the API the code has to match or keep: `to` going up,
  `from` going down. 1,483 of the 2,265 uses (97 of the 152 breaks) have a newer release from after the cutoff.
- **Whether the release series differs:** the first number, or the first two below 1.0. The question shows it, so it
  is the obvious guess (next section).
- **Change type of each break:** 86 `removed`, 61 `symbol_not_yet_added`, 3 `param_removed`, 2
  `param_not_yet_added`.

## Rules that know nothing, scored first

The traceback question gave its answer away in 132 of 191 cases, and nobody had checked before the run. So four rules
that know nothing about any library were scored on these uses before any model was asked: everything works; a use
breaks when the first number of the release differs; when the series differs; and everything breaks going down.
`shortcuts.md` has their scores, beside DepTime's first run. A model's score means something only above them.

In short: the question gives the answer away only at a cost. Every rule that finds any break flags at least a fifth of
the working uses: the series rule finds 90.1% of the breaks and flags 53.2% of the working uses. Read a model's
recall at its false-positive rate.

## Order of work

1. This protocol is committed and pushed.
2. **A trial of ten upgrades**, the first ten in the order of the sha256 of the upgrade ID
   (`ask.py --limit 10`). It checks the plumbing and the cost. If it shows the prompt or the rule must change, the
   change is committed before going on and the results say so; otherwise its ten replies are the first ten of run 1.
3. The run, then `grade.py` writes the results file.

```bash
uv run python bench/model-alone/upgrades/grade.py --dates                       # released.json, from the index
uv run python bench/model-alone/upgrades/grade.py --shortcuts > bench/model-alone/upgrades/shortcuts.md
uv run python bench/model-alone/upgrades/ask.py --model sonnet --run 1 --limit 10
uv run python bench/model-alone/upgrades/ask.py --model sonnet --run 1
uv run python bench/model-alone/upgrades/grade.py > bench/model-alone/upgrades/results-<date>.md
```

## What this doesn't measure

- **A model with tools.** An agent can read the installed package's source, or install `to` and run the code. Whether
  an agent does better with DepTime than without is DT-QA-05.
- **Other models.** One model, one vendor, one run.
- **Unseen code, for the model.** The projects are public on GitHub, and so are the libraries' changelogs, for releases
  older than the training data.
- **The other five holdout sets.** DepTime's first runs on them are in their own results; asking them would be about
  six times the calls.
