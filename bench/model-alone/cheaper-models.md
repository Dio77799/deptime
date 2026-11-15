# Cheaper and smaller models alone, through OpenRouter (DT-QA-19)

**Purpose:** the Claude runs (DT-QA-16, DT-QA-18) found DepTime's lead grows as the model gets smaller: on the upgrade
checks it is 6 points over Claude Sonnet 5.5 and 23 over Claude Haiku 5.5; on the tracebacks, 4 over Sonnet and about
20 over Haiku. This asks five models from other vendors the same questions, to see whether that holds beyond Claude:
two paid ones (a model priced for running on every pull request, and a small one of the size people run on their own
machine) and three of OpenRouter's free ones (a small and a tiny open-weight model, and a very large one).

This page, `ask_openrouter.py` and `openrouter.py` were committed before any of these models was asked. It is run once and
reported whichever way it comes out. It is an evaluation only: DepTime's own answers still involve no model (ADR 0006).

## The models

Chosen from OpenRouter's model list on 2026-11-15, by what each tests; prices are OpenRouter's that day, per million
tokens in and out.

| OpenRouter id | Released on OpenRouter | Price | Why |
|---|---|---|---|
| `deepseek/deepseek-v4.1-flash` | 2026-09-10 | $0.05 / $0.20 | The cheapest tier a team would run on every update: a sparse mixture of experts, 8B to 16B parameters active |
| `qwen/qwen3.5-9b` | 2026-03-10 | $0.09 / $0.14 | A small open-weight model, 9B parameters, of the size people run locally |
| `google/gemma-4-26b-a4b-it:free` | 2026-04-03 | free | A small open-weight model from another vendor: a mixture of experts with 3.8B parameters active |
| `liquid/lfm-3-1.7b:free` | 2026-11-06 | free | A tiny one, 1.7B parameters, the far end of "small" |
| `nvidia/nemotron-3-ultra-550b-a55b:free` | 2026-06-04 | free | A very large open-weight model (550B, 55B active): does size alone close the gap? |

The free variants are OpenRouter's `:free` endpoints of those models. Their providers may log prompts, which is
acceptable here: everything sent is already public in this repository.

None states a training cutoff; each is described by its release date, which bounds it. Not asked: larger or
frontier models (Sonnet already shows what a strong model does), and OpenRouter's `~...-latest` aliases, which can
point at a different model later.

## What is asked

- **Both tests, unchanged:** the 191 tracebacks with `system-prompt.txt` and the message `ask.py` builds (`README.md`),
  and the 171 upgrades of 2026-11f with `upgrades/system-prompt.txt` and the message `upgrades/cases.py` builds
  (`upgrades/README.md`), in the same order.
- **The call:** one chat completion per question through OpenRouter's API (`openrouter.py`), a system and a user
  message, no tools, at most 8,000 tokens out, the provider's default reasoning and temperature. OpenRouter picks the
  provider; each reply records the model and provider that served it, its tokens and OpenRouter's count of its cost.
- **Retries:** a call that fails or returns no text is tried up to three times; after that its last reply, empty or
  not, is stored and scored as it stands: a wrong answer on the tracebacks, no verdicts (abstentions) on the upgrades.
- **Rate limits** (HTTP 429, which the free endpoints answer often) aren't failures: the call waits and tries again,
  and if the limit outlasts the waits, or OpenRouter refuses the key, the credit or the account's data policy, the run
  pauses with nothing stored for that question and resumes later from where it stopped. A model that can't be finished
  (withdrawn, or limited for days) is reported with the questions it answered and marked incomplete, not scored as if
  it had answered the rest.
- **Runs:** one per model per test. A spend cap of $3 per run stops a runaway. Order: the paid models, then Gemma,
  Liquid and Nemotron, each model's trial and then its runs.

## Scoring

Unchanged: `grade.py` for the tracebacks and `upgrades/grade.py` for the upgrade checks, which score every file in
their `answers/` folders, so each results file is regenerated with these two models beside the Claude ones and
DepTime's first run.

## Order of work

1. This protocol is committed and pushed.
2. **A trial of ten questions** per model per test (`--limit 10`). If it shows the call or the parsing must change, the
   change is committed before going on and the results say so; otherwise its replies are the first ten of the run.

   **The trial's change (committed before the runs):** DeepSeek V4.1 Flash reasons at length (a median of about 5,300
   thinking tokens on the tracebacks), and in each test one of its ten trial replies reached the 8,000-token cap
   before any answer, which would score a lack of room as a wrong answer. The cap is raised to 32,000 for every model,
   and DeepSeek's trial is asked again under it. Qwen3.5 9B's trial replies stand: it answered without reasoning, in
   under 100 tokens, far below either cap.

   **The free models' trial (committed before any of their runs):** OpenRouter's free endpoints answered 429, "rate
   limited upstream" (a pool every user shares, not this account's limit), and Nemotron 503, "Service temporarily
   overloaded". A provider that is overloaded or unreachable (502, 503) is now treated like a rate limit: wait, try
   again, and pause with nothing stored if it lasts. No reply was stored by either: the trials paused before any
   answer. The free models are asked whenever their pools allow, in any order.
3. The runs, then both graders write their results files.

```bash
uv run python bench/model-alone/openrouter.py --check
uv run python bench/model-alone/ask_openrouter.py --test tracebacks --model qwen/qwen3.5-9b --run 1 --limit 10
uv run python bench/model-alone/ask_openrouter.py --test tracebacks --model qwen/qwen3.5-9b --run 1
uv run python bench/model-alone/ask_openrouter.py --test upgrades --model qwen/qwen3.5-9b --run 1
uv run python bench/model-alone/grade.py > bench/model-alone/results-<date>.md
uv run python bench/model-alone/upgrades/grade.py > bench/model-alone/upgrades/results-<date>.md
```

## What this doesn't measure

- **A small model with DepTime.** A low score alone shows room to help, not that the model would call the tool and
  use its answer; smaller models are less reliable at both. That is DT-QA-05.
- **The same model run locally.** OpenRouter's providers may serve a model differently from a local quantized copy.
- **More than one run.** Runs of the same model vary; the Claude runs varied by one to three points.

## Result

Added after the runs; everything above is as it was committed before them. DeepSeek V4.1 Flash and Qwen3.5 9B were
run on 2026-11-15, $1.76 in all; the results are in [results-2026-11-15.md](results-2026-11-15.md) (tracebacks) and
[upgrades/results-2026-11-15.md](upgrades/results-2026-11-15.md) (upgrade checks), with the replies in each test's
`answers/` folder.

**The free models were not run.** Every free endpoint was busy during the trial (rate limited upstream, or
overloaded), and no reply was stored; asking them was left for another day. The protocol, runner and order above
still apply to them.
