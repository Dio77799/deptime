# A small model with DepTime's tools (DT-QA-20)

**Purpose:** the model-alone runs show room for DepTime to help a small model: Qwen3.5 9B alone names the right
package, name and release for 18.8% of the holdout tracebacks, against DepTime's 86.9% (`../results-2026-11-15.md`),
and on the upgrade checks finds 30.9% of the breaks while flagging 15.4% of working code
(`../upgrades/results-2026-11-15.md`). Room to help isn't help: a small model may not call the tool, may misread its
answer, or may overrule it. This asks the same model the same questions with DepTime's tools available, to see
whether it gets DepTime's answers through.

This page, `ask.py`, `grade.py` and the two system prompts were committed before the model was asked. It is run once
and reported whichever way it comes out.

## What is asked

- **Model:** Qwen3.5 9B (`qwen/qwen3.5-9b`) through OpenRouter, as in `../cheaper-models.md`; at most 32,000 tokens
  out per call, the provider's default reasoning and temperature, the same retry and pause rules.
- **Questions:** the 191 tracebacks and 171 upgrades, with the same messages, order and answer format as the
  model-alone runs (`../ask_openrouter.py`).
- **System prompt:** the model-alone one with one sentence changed, "You have no tools and cannot look anything up.
  Answer from memory." becoming "You can call DepTime's tools, which answer from an index of the libraries' released
  code; use them as you judge best, then give your answer.", followed by DepTime's own MCP server instructions, as an
  MCP client shows them (`system-prompt-tracebacks.txt`, `system-prompt-upgrades.txt`). The model isn't told which
  tool to call or that it must call one.
- **Tools:** DepTime's five, exactly as its MCP server lists them (names, descriptions, input schemas), offered as
  functions. Each call runs in `ask.py` through DepTime's MCP server in-process (`build_mcp` and the SDK's client),
  on the local index (built 2026-11-13), offline. A malformed call gets the error back, as an MCP client would pass it
  on. A tool result over 30,000 characters is cut, and says so.
- **The conversation** ends when the model answers without a tool call, or after 8 model calls; its last text is the
  reply. Every tool call and its arguments are kept with the reply.

  **The trial's change (committed before the runs):** in each test, one of the ten trial conversations spent all 8
  calls on tools and gave no answer. The 8th call is now offered no tools, so the model answers with what it has
  gathered, as agent loops usually end. The trial is asked again under it.

  **The second trial's change (committed before the runs):** in that trial, 3 of 20 replies were empty although the
  call finished normally. All came from one provider (Darkbloom), which turns on Qwen's reasoning once tools are in
  play; Qwen then ended its answer inside the reasoning (`... {"1": "works", "2": "works", ...}`) and left the reply
  empty. When the final message has no text and no tool call, the last JSON object in its reasoning is taken as the
  reply, and the record says so (`reply_from_reasoning`). The trial is asked again under it.

## Scoring

The model-alone graders, unchanged (`../grade.py`, `../upgrades/grade.py`), on these replies. `grade.py` adds:

- **The comparison:** the model with tools, the same model alone (its model-alone replies) and DepTime by itself,
  both on its first run and now. DepTime now is the yardstick for "does the model get DepTime's answers through":
  fixes since the first runs were designed from these tracebacks, so it answers more of them than it did then.
  Measured before the run, on the index above: **94.8%** of the tracebacks (181 of 191; first run 86.9%), and on the
  upgrade checks **96.7%** of breaks found and **0.1%** of working uses flagged, as on its first run.
- **Kept and added:** of the cases DepTime by itself answers right now, how many the model with tools answers right;
  of those it misses, how many the model gets.
- **Tool use:** the share of questions where the model called a tool, the calls by tool, and calls that failed.

## Order of work

1. This protocol is committed and pushed.
2. **A trial of ten questions** per test. If it shows the loop or the prompt must change, the change is committed
   before going on and the results say so; otherwise its replies are the first ten of the run.
3. The runs, then `grade.py` writes the results file.

```bash
uv run python bench/model-alone/with-tools/ask.py --prompts
uv run python bench/model-alone/with-tools/ask.py --test tracebacks --model qwen/qwen3.5-9b --run 1 --limit 10
uv run python bench/model-alone/with-tools/ask.py --test tracebacks --model qwen/qwen3.5-9b --run 1
uv run python bench/model-alone/with-tools/ask.py --test upgrades --model qwen/qwen3.5-9b --run 1
uv run python bench/model-alone/with-tools/grade.py > bench/model-alone/with-tools/results-<date>.md
```

## What this doesn't measure

- **Fixing code.** The model answers questions about a break; whether it then fixes the code, judged by the
  project's tests, is DT-QA-05.
- **Other tools.** It has DepTime's tools and nothing else: no web search and no reading the installed source.
- **Other models, and more than one run.**

## Result

Added after the runs; everything above is as it was committed before them. The run of 2026-11-15 is in
[results-2026-11-15.md](results-2026-11-15.md), with the conversations' replies and tool calls in `tracebacks/` and
`upgrades/`.
