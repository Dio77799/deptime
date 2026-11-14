"""Put the holdout tracebacks to a model with no tools, and keep its replies (DT-QA-16).

  uv run python bench/model-alone/ask.py --model haiku --run 1 --limit 10    the trial: the first ten cases
  uv run python bench/model-alone/ask.py --model haiku --run 1               the rest of that run

Each case is one call of the `claude` command-line tool in print mode, signed in to a Claude account (no API key),
from a new empty folder, with every tool off and system-prompt.txt as the system prompt. The model is given what
`explain_error` is given: the installed versions and the traceback. README.md has the exact call.

Replies go to answers/<model>-run<N>.jsonl as they arrive, raw; grade.py reads and scores them. A case that already
has a reply there is skipped, so an interrupted run picks up where it stopped. Nothing here reads a case's expected
answer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from boundaries import load_cases

HERE = Path(__file__).parent
ANSWERS = HERE / "answers"
SYSTEM_PROMPT = (HERE / "system-prompt.txt").read_text(encoding="utf-8").strip()
EFFORT = "high"
TIMEOUT_SECONDS = 900
ATTEMPTS = 3


def ordered_cases() -> list[dict]:
    """Every case, in the order of the sha256 of its id: fixed, and no set or package comes first."""
    return sorted(load_cases(), key=lambda c: hashlib.sha256(c["id"].encode()).hexdigest())


def user_message(case: dict) -> str:
    installed = "\n".join(f"{name}=={version}" for name, version in case["installed"].items())
    return f"Installed versions:\n{installed}\n\nTraceback:\n{case['traceback'].strip()}\n"


def command(model: str) -> list[str]:
    return [
        "claude",
        "--print",
        "--model",
        model,
        "--effort",
        EFFORT,
        "--tools",
        "",
        "--system-prompt",
        SYSTEM_PROMPT,
        "--safe-mode",
        "--strict-mcp-config",
        "--disable-slash-commands",
        "--no-session-persistence",
        "--output-format",
        "stream-json",
        "--verbose",
    ]


def clean_environment() -> dict[str, str]:
    """The caller's environment without an API key and without a parent Claude Code session's settings, so the call
    is a signed-in one that behaves the same from any terminal."""
    return {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("ANTHROPIC_")
        and (not name.startswith("CLAUDE") or name == "CLAUDE_CONFIG_DIR")
    }


class LimitReached(Exception):
    pass


def ask(case: dict, model: str, folder: str) -> dict:
    """One call. Returns the record to store; raises LimitReached when the account's usage limit refuses it."""
    problem = "no attempt"
    for attempt in range(ATTEMPTS):
        started = time.monotonic()
        try:
            done = subprocess.run(
                command(model),
                input=user_message(case),
                capture_output=True,
                text=True,
                cwd=folder,
                env=clean_environment(),
                timeout=TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            problem = "timed out"
            continue
        init = result = limit = None
        for line in done.stdout.splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("type") == "system" and event.get("subtype") == "init":
                init = event
            elif event.get("type") == "rate_limit_event":
                limit = event.get("rate_limit_info") or {}
            elif event.get("type") == "result":
                result = event
        if init is not None and (init.get("apiKeySource") != "none" or init.get("tools")):
            raise RuntimeError(f"the call isn't a signed-in one with no tools: {init.get('apiKeySource')!r}")
        if limit and limit.get("status") == "rejected":
            raise LimitReached(json.dumps(limit))
        if result is None or result.get("is_error") or not (result.get("result") or "").strip():
            text = (result or {}).get("result") or done.stderr.strip() or done.stdout.strip()
            problem = f"exit {done.returncode}: {text[-300:]}"
            if "limit" in text.lower() and "reset" in text.lower():
                raise LimitReached(text[-300:])
            time.sleep(5 * (attempt + 1))
            continue
        models = list(result.get("modelUsage") or {})
        usage = result.get("usage") or {}
        return {
            "id": case["id"],
            "model": model,
            "model_id": models[0] if len(models) == 1 else models,
            "effort": EFFORT,
            "reply": result["result"],
            "input_tokens": sum(
                usage.get(k) or 0
                for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
            ),
            "output_tokens": usage.get("output_tokens"),
            "thinking_tokens": (usage.get("output_tokens_details") or {}).get("thinking_tokens"),
            "seconds": round(time.monotonic() - started, 1),
            "usage_windows": limit
            and {k: v.get("utilization") for k, v in (limit.get("unifiedWindows") or {}).items()},
        }
    return {"id": case["id"], "model": model, "failed": problem}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", required=True, help="a model alias the CLI takes: haiku, sonnet or opus")
    parser.add_argument("--run", type=int, required=True, help="the run's number, from 1")
    parser.add_argument(
        "--limit", type=int, help="only the first N cases of the fixed order (the trial is 10)"
    )
    parser.add_argument("--jobs", type=int, default=4, help="calls in flight at once")
    args = parser.parse_args()

    ANSWERS.mkdir(exist_ok=True)
    out = ANSWERS / f"{args.model}-run{args.run}.jsonl"
    have = set()
    if out.exists():
        have = {
            json.loads(line)["id"] for line in out.read_text(encoding="utf-8").splitlines() if line.strip()
        }
    cases = [c for c in ordered_cases()[: args.limit] if c["id"] not in have]
    print(f"{args.model} run {args.run}: {len(cases)} to ask, {len(have)} already answered", file=sys.stderr)

    folder = tempfile.mkdtemp()
    failed, windows, stopped = [], None, None
    with ThreadPoolExecutor(max_workers=args.jobs) as pool, out.open("a", encoding="utf-8") as sink:
        futures = {pool.submit(ask, case, args.model, folder): case for case in cases}
        for n, future in enumerate(as_completed(futures), 1):
            try:
                record = future.result()
            except LimitReached as limit:
                stopped = str(limit)
                pool.shutdown(wait=False, cancel_futures=True)
                break
            if "failed" in record:
                failed.append(record)
                print(f"  FAILED {record['id']}: {record['failed']}", file=sys.stderr)
                continue
            # The account's usage is the caller's business, not part of the result: report it, don't store it.
            windows = record.pop("usage_windows") or windows
            sink.write(json.dumps(record, ensure_ascii=False) + "\n")
            sink.flush()
            if n % 20 == 0 or n == len(cases):
                print(f"  {n}/{len(cases)} asked; usage windows {windows}", file=sys.stderr)
    leftover = os.listdir(folder)
    os.rmdir(folder) if not leftover else print(f"the empty folder now holds {leftover}", file=sys.stderr)
    if stopped:
        print(f"STOPPED at the account's usage limit: {stopped}", file=sys.stderr)
        return 3
    if failed:
        print(f"{len(failed)} calls failed; run the same command again to retry them", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
