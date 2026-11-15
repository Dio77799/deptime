"""Put either model-alone test to a model on OpenRouter, and keep its replies (DT-QA-19).

  uv run python bench/model-alone/ask_openrouter.py --test tracebacks --model qwen/qwen3.5-9b --run 1 --limit 10
  uv run python bench/model-alone/ask_openrouter.py --test upgrades --model qwen/qwen3.5-9b --run 1

The same questions, system prompts and order as the Claude runs (ask.py for the tracebacks, upgrades/ask.py for the
upgrade checks), sent as one chat completion each through OpenRouter (openrouter.py, which holds the key): no tools,
the provider's default reasoning and temperature, at most MAX_TOKENS tokens out. Replies go to the test's answers/
folder as <model>-run<N>.jsonl, in the fields grade.py and upgrades/grade.py read, so both score them unchanged.

A call that fails or returns no text is tried up to ATTEMPTS times; after that its last reply, empty or not, is stored
and scored as it stands (a wrong answer, or no verdicts). A rate limit (HTTP 429) isn't a failure: the call waits and tries
again, and if the limit outlasts the waits, or OpenRouter refuses the key, the credit or the account's data policy, the
run pauses without storing anything for that question. An interrupted or paused run picks up where it stopped. The run
also stops itself when its spend passes SPEND_CAP dollars, by OpenRouter's own count.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx
import openrouter

HERE = Path(__file__).parent
MAX_TOKENS = 32000  # 8,000 in the protocol; raised after the trial (cheaper-models.md)
ATTEMPTS = 3
SPEND_CAP = 3.00  # dollars, per run of one test


def _module(path: Path, name: str):
    """A test's own module, loaded by its path: both folders have an ask.py, so `import ask` could find either."""
    sys.path.insert(0, str(path.parent))  # for that module's own imports (boundaries, cases)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def questions(test: str) -> tuple[str, Path, list[tuple[str, str]]]:
    """The system prompt, the answers folder, and (id, message) in the fixed order of the Claude runs."""
    if test == "tracebacks":
        ask = _module(HERE / "ask.py", "traceback_ask")
        return ask.SYSTEM_PROMPT, ask.ANSWERS, [(c["id"], ask.user_message(c)) for c in ask.ordered_cases()]
    cases = _module(HERE / "upgrades" / "cases.py", "upgrade_cases")
    prompt = (HERE / "upgrades" / "system-prompt.txt").read_text(encoding="utf-8").strip()
    return (
        prompt,
        HERE / "upgrades" / "answers",
        [(u["id"], cases.user_message(u)) for u in cases.load_upgrades()],
    )


def record(case_id: str, model: str, response: dict, seconds: float) -> dict:
    """What the graders read, from OpenRouter's reply; `model_id` is the model asked for, `served_by` what answered."""
    choice = (response.get("choices") or [{}])[0]
    usage = response.get("usage") or {}
    return {
        "id": case_id,
        "model": model,
        "model_id": model,
        "served_by": {"model": response.get("model"), "provider": response.get("provider")},
        "finish_reason": choice.get("finish_reason"),
        "reply": (choice.get("message") or {}).get("content") or "",
        "input_tokens": usage.get("prompt_tokens"),
        "output_tokens": usage.get("completion_tokens"),
        "thinking_tokens": (usage.get("completion_tokens_details") or {}).get("reasoning_tokens"),
        "cost": usage.get("cost"),
        "seconds": round(seconds, 1),
    }


class Paused(Exception):
    """OpenRouter refused for a reason that isn't the question's: a rate limit that outlasts the waits, no credit, or
    an account setting. Nothing is stored for the question, and the same command resumes the run later."""


RATE_LIMIT_WAITS = (15, 30, 60, 120)  # seconds between tries while OpenRouter answers one of BUSY_CODES
# A rate limit, or a provider overloaded or unreachable: about the service, not the question (502, 503 added after
# the free trials met "Service temporarily overloaded", before any model that answered them was asked).
BUSY_CODES = {429, 502, 503}
PAUSE_CODES = {401, 402, 403, 404}  # the key, credit, or a data policy that rules out every provider


def _status(error: Exception | None, response: dict | None) -> int | None:
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code
    code = ((response or {}).get("error") or {}).get("code")  # an error inside a 200 reply
    return code if isinstance(code, int) else None


def ask_one(case_id: str, message: str, model: str, system: str) -> dict:
    last: dict = {"id": case_id, "model": model, "model_id": model, "reply": "", "failed": "no attempt"}
    attempt = waited = 0
    while attempt < ATTEMPTS:
        started = time.monotonic()
        error, response = None, None
        try:
            response = openrouter.chat(model, system, message, max_tokens=MAX_TOKENS)
        except (httpx.HTTPError, ValueError) as caught:
            error = caught
        status = _status(error, response)
        if status in BUSY_CODES:
            if waited == len(RATE_LIMIT_WAITS):
                raise Paused(f"busy (HTTP {status}) after {sum(RATE_LIMIT_WAITS)} s of waiting")
            time.sleep(RATE_LIMIT_WAITS[waited])
            waited += 1
            continue  # a rate limit isn't one of the question's attempts
        if status in PAUSE_CODES:
            raise Paused(f"HTTP {status}: {str(error or response.get('error'))[:200]}")
        attempt += 1
        if error is not None:
            last = {**last, "failed": f"{type(error).__name__}: {str(error)[:200]}"}
            time.sleep(5 * attempt)
            continue
        last = record(case_id, model, response, time.monotonic() - started)
        if last["reply"].strip():
            return last
        time.sleep(2 * attempt)
    return last


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--test", required=True, choices=("tracebacks", "upgrades"))
    parser.add_argument("--model", required=True, help="an OpenRouter model id, such as qwen/qwen3.5-9b")
    parser.add_argument("--run", type=int, required=True, help="the run's number, from 1")
    parser.add_argument(
        "--limit", type=int, help="only the first N questions of the fixed order (the trial is 10)"
    )
    parser.add_argument("--jobs", type=int, default=4, help="calls in flight at once")
    args = parser.parse_args()

    system, answers, todo = questions(args.test)
    answers.mkdir(exist_ok=True)
    out = answers / f"{args.model.split('/')[-1].replace(':', '-')}-run{args.run}.jsonl"
    have, spent = set(), 0.0
    if out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            if line.strip():
                old = json.loads(line)
                have.add(old["id"])
                spent += old.get("cost") or 0
    todo = [(i, m) for i, m in todo[: args.limit] if i not in have]
    print(
        f"{args.model} {args.test} run {args.run}: {len(todo)} to ask, {len(have)} already answered",
        file=sys.stderr,
    )

    stopped = None
    with ThreadPoolExecutor(max_workers=args.jobs) as pool, out.open("a", encoding="utf-8") as sink:
        futures = [pool.submit(ask_one, i, m, args.model, system) for i, m in todo]
        for n, future in enumerate(as_completed(futures), 1):
            try:
                rec = future.result()
            except Paused as pause:
                stopped = (
                    f"paused, nothing stored for the question: {pause}; run the same command again later"
                )
                pool.shutdown(wait=False, cancel_futures=True)
                break
            if rec.get("failed"):
                print(
                    f"  stored after {ATTEMPTS} failed attempts: {rec['id']}: {rec['failed']}",
                    file=sys.stderr,
                )
            spent += rec.get("cost") or 0
            sink.write(json.dumps(rec, ensure_ascii=False) + "\n")
            sink.flush()
            if n % 20 == 0 or n == len(todo):
                print(f"  {n}/{len(todo)} asked; ${spent:.4f} spent on this run", file=sys.stderr)
            if spent > SPEND_CAP:
                stopped = f"spend passed ${SPEND_CAP:.2f}"
                pool.shutdown(wait=False, cancel_futures=True)
                break
    print(f"spent on this run: ${spent:.4f}", file=sys.stderr)
    if stopped:
        print(f"STOPPED: {stopped}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
