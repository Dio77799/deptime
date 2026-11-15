"""Put the 2026-11f upgrade checks to a model with no tools, and keep its replies (DT-QA-18).

  uv run python bench/model-alone/upgrades/ask.py --model sonnet --run 1 --limit 10    the trial: the first ten
  uv run python bench/model-alone/upgrades/ask.py --model sonnet --run 1               the rest of that run

One call per upgrade, made exactly as ../ask.py makes it for a traceback (signed in, no API key, every tool off,
from a new empty folder), with system-prompt.txt as the system prompt. The model gets the package, both releases and
the numbered uses (cases.py), and never a label.

Replies go to answers/<model>-run<N>.jsonl as they arrive, raw; grade.py reads and scores them. An upgrade that
already has a reply there is skipped, so an interrupted run picks up where it stopped. The run also stops itself
when the account's 5-hour usage window passes STOP_AT, and the same command resumes it after the window resets.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from cases import load_upgrades, user_message

HERE = Path(__file__).parent
ANSWERS = HERE / "answers"
SYSTEM_PROMPT = (HERE / "system-prompt.txt").read_text(encoding="utf-8").strip()
STOP_AT = 0.88  # of the 5-hour window


def _traceback_ask():
    """../ask.py, for its call and its clean environment, so both questions are asked the same way."""
    sys.path.append(str(HERE.parent))  # its own `from boundaries import ...`
    spec = importlib.util.spec_from_file_location("traceback_ask", HERE.parent / "ask.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BASE = _traceback_ask()


def command(model: str) -> list[str]:
    cmd = BASE.command(model)
    cmd[cmd.index("--system-prompt") + 1] = SYSTEM_PROMPT
    return cmd


def utilization(windows: dict | None, name: str = "five_hour") -> float | None:
    value = (windows or {}).get(name)
    if value is None:
        return None
    return value / 100 if value > 1 else value


def ask(upgrade: dict, model: str, folder: str) -> dict:
    """One call. Returns the record to store; raises LimitReached when the account's usage limit refuses it."""
    problem = "no attempt"
    for attempt in range(BASE.ATTEMPTS):
        started = time.monotonic()
        try:
            done = subprocess.run(
                command(model),
                input=user_message(upgrade),
                capture_output=True,
                text=True,
                cwd=folder,
                env=BASE.clean_environment(),
                timeout=BASE.TIMEOUT_SECONDS,
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
            raise BASE.LimitReached(json.dumps(limit))
        if result is None or result.get("is_error") or not (result.get("result") or "").strip():
            text = (result or {}).get("result") or done.stderr.strip() or done.stdout.strip()
            problem = f"exit {done.returncode}: {text[-300:]}"
            if "limit" in text.lower() and "reset" in text.lower():
                raise BASE.LimitReached(text[-300:])
            time.sleep(5 * (attempt + 1))
            continue
        models = list(result.get("modelUsage") or {})
        usage = result.get("usage") or {}
        return {
            "id": upgrade["id"],
            "model": model,
            "model_id": models[0] if len(models) == 1 else models,
            "effort": BASE.EFFORT,
            "uses": len(upgrade["items"]),
            "reply": result["result"],
            "input_tokens": sum(
                usage.get(k) or 0
                for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
            ),
            "output_tokens": usage.get("output_tokens"),
            "seconds": round(time.monotonic() - started, 1),
            "usage_windows": limit
            and {k: v.get("utilization") for k, v in (limit.get("unifiedWindows") or {}).items()},
        }
    return {"id": upgrade["id"], "model": model, "failed": problem}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", required=True, help="a model alias the CLI takes: haiku, sonnet or opus")
    parser.add_argument("--run", type=int, required=True, help="the run's number, from 1")
    parser.add_argument(
        "--limit", type=int, help="only the first N upgrades of the fixed order (the trial is 10)"
    )
    parser.add_argument("--jobs", type=int, default=4, help="calls in flight at once")
    args = parser.parse_args()

    ANSWERS.mkdir(exist_ok=True)
    out = ANSWERS / f"{args.model}-run{args.run}.jsonl"
    have = set()
    if out.exists():
        have = {json.loads(x)["id"] for x in out.read_text(encoding="utf-8").splitlines() if x.strip()}
    todo = [u for u in load_upgrades()[: args.limit] if u["id"] not in have]
    print(f"{args.model} run {args.run}: {len(todo)} to ask, {len(have)} already answered", file=sys.stderr)

    folder = tempfile.mkdtemp()
    failed, windows, stopped = [], None, None
    with ThreadPoolExecutor(max_workers=args.jobs) as pool, out.open("a", encoding="utf-8") as sink:
        futures = {pool.submit(ask, u, args.model, folder): u for u in todo}
        for n, future in enumerate(as_completed(futures), 1):
            try:
                record = future.result()
            except BASE.LimitReached as limit:
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
            if n % 10 == 0 or n == len(todo):
                print(f"  {n}/{len(todo)} asked; usage windows {windows}", file=sys.stderr)
            if (used := utilization(windows)) is not None and used >= STOP_AT:
                stopped = f"the 5-hour window is at {used:.0%}"
                pool.shutdown(wait=False, cancel_futures=True)
                break
    leftover = os.listdir(folder)
    os.rmdir(folder) if not leftover else print(f"the empty folder now holds {leftover}", file=sys.stderr)
    print(f"usage windows at the end: {windows}", file=sys.stderr)
    if stopped:
        print(f"STOPPED: {stopped}; run the same command again to resume", file=sys.stderr)
        return 3
    if failed:
        print(f"{len(failed)} calls failed; run the same command again to retry them", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
