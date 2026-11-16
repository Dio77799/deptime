# A small model with the `check_upgrade` tool (DT-QA-23)

**Purpose:** with DepTime's five tools, Qwen3.5 9B found 82.2% of the 2026-11f holdout's breaks and flagged 4.5% of
its working uses, where DepTime by itself finds 96.7% and flags 0.1% (DT-QA-20,
`../with-tools/results-2026-11-15.md`). The model called `check_symbols` per use and then re-decided uses DepTime had
right. 0.2.0 adds `check_upgrade`, one call that answers "what does this update break in this code?" for a whole
upgrade (DT-CORE-68). This asks whether the same model, offered it, keeps more of DepTime's precision.

This page, `grade.py` and `system-prompt-upgrades.txt` were committed before the model was asked. It is run once and
reported whichever way it comes out.

## What is asked

DT-QA-20's upgrade half (`../with-tools/README.md`), with these differences only:

- **Tools:** DepTime's six, exactly as its MCP server lists them at the commit run, `check_upgrade` among them. The
  others are unchanged.
- **System prompt:** made the same way (`../with-tools/ask.py --prompts --dir` here), so DepTime's own instructions
  are the current ones, which name `check_upgrade` for upgrades: two lines differ from DT-QA-20's prompt.
- **Index:** the published index at the run (`SNAPSHOT_FORMAT` 27, after DT-QA-22's fixes); `grade.py` measures
  DepTime by itself on the same index, and states when it was built.

Unchanged: the model (`qwen/qwen3.5-9b` through OpenRouter, the provider's defaults, at most 32,000 tokens out per
call), the 171 upgrades with their questions, order and answer format (the uses are listed, not given as code), the
loop (at most 8 model calls, the last offered no tools; a reply left in the reasoning is taken from there), the retry
and pause rules, and the $3.00 spending cap. The model isn't told which tool to call.

## Scoring

The upgrade grader, unchanged (`../upgrades/grade.py`; abstentions count as not flagged), on these replies, beside:
the same model alone (`../upgrades/answers/`), the same model with the five tools (DT-QA-20), and DepTime's
`check_symbols` by itself, first run and on this index. Also reported, with no bar:

- the share of upgrades where the model called `check_upgrade`, and the calls by tool;
- breaks found and working uses flagged, split by whether the model called `check_upgrade` in that upgrade;
- calls that returned an error, replies with no text, failed conversations and cost.

**What would count as keeping DepTime's precision** (fixed now, read after): working uses flagged at 1% or less
with breaks found at 90% or more, DepTime's own bar for a check on pull requests (DT-QA-21). Either way the result
goes in `../../README.md` and the backlog.

## Order of work

1. This protocol is committed and pushed.
2. A trial of ten upgrades. If it shows the loop or the prompt must change, the change is committed before going on
   and the results say so; otherwise its replies are the first ten of the run.
3. The run, then `grade.py` writes the results file.

```bash
uv run deptime index pull
uv run python bench/model-alone/with-tools/ask.py --test upgrades --model qwen/qwen3.5-9b --run 1 \
    --dir bench/model-alone/check-upgrade --limit 10
uv run python bench/model-alone/with-tools/ask.py --test upgrades --model qwen/qwen3.5-9b --run 1 \
    --dir bench/model-alone/check-upgrade
uv run python bench/model-alone/check-upgrade/grade.py > bench/model-alone/check-upgrade/results-<date>.md
```

## What this doesn't measure

- **Fixing the code.** The model answers which uses break; writing the fix is DT-GTM-07's hand-off, and judging it
  by a project's tests is DT-QA-05.
- **Code as projects write it.** The uses are listed one per line, as in DT-QA-18 to DT-QA-20, so to call
  `check_upgrade` the model writes a snippet from them; on real code the tool reads the files as they are.
- **Other models, and more than one run.**
