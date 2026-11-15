"""Put either model-alone test to a model on OpenRouter that can call DepTime's tools, and keep its replies (DT-QA-20).

  uv run python bench/model-alone/with-tools/ask.py --prompts                write the two system prompts
  uv run python bench/model-alone/with-tools/ask.py --test tracebacks --model qwen/qwen3.5-9b --run 1 --limit 10
  uv run python bench/model-alone/with-tools/ask.py --test upgrades --model qwen/qwen3.5-9b --run 1

The questions, order and answer format are the model-alone runs' (../ask_openrouter.py). The model is offered
DepTime's five tools as its MCP server lists them, names, descriptions and schemas unchanged, and the server's own
instructions; each call it makes runs in this process, through DepTime's MCP server (`build_mcp`, in-process client),
on the local index, offline. Its last message without a tool call is its reply, scored by the unchanged graders.

The system prompt is the model-alone one with one sentence changed (`--prompts` writes both; README.md has the
change). A conversation ends after MAX_ROUNDS model calls; the last text, if any, is the reply. A model call is retried
as ../ask_openrouter.py retries one: busy answers wait and pause the run; other failures are tried three times, after
which the question's reply is what it has (empty if nothing), scored as it stands.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("DEPTIME_OFFLINE", "1")  # the tools read the local index and nothing else

import httpx
from mcp import Client

from deptime.config import Settings, load_coverage
from deptime.index.location import open_index
from deptime.query import DepTime
from deptime.server.mcp_app import INSTRUCTIONS, build_mcp

HERE = Path(__file__).parent
ALONE = HERE.parent
MAX_TOKENS = 32000
MAX_ROUNDS = 8
TOOL_RESULT_CHARS = 30000  # longer tool results are cut, and say so
SPEND_CAP = 3.00
NO_TOOLS = "You have no tools and cannot look anything up. Answer from memory."
WITH_TOOLS = (
    "You can call DepTime's tools, which answer from an index of the libraries' released code; use them as you judge"
    " best, then give your answer."
)


def _module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sys.path.insert(0, str(ALONE))
openrouter = _module(ALONE / "openrouter.py", "openrouter")
base = _module(ALONE / "ask_openrouter.py", "ask_openrouter")


def prompt_path(test: str) -> Path:
    return HERE / f"system-prompt-{test}.txt"


def write_prompts() -> None:
    for test in ("tracebacks", "upgrades"):
        alone, _, _ = base.questions(test)
        assert alone.count(NO_TOOLS) == 1, test
        text = (
            alone.replace(NO_TOOLS, WITH_TOOLS) + "\n\nDepTime's own instructions:\n" + INSTRUCTIONS.strip()
        )
        prompt_path(test).write_text(text + "\n", encoding="utf-8")


def as_function(tool) -> dict:
    return {
        "type": "function",
        "function": {"name": tool.name, "description": tool.description, "parameters": tool.input_schema},
    }


def tool_text(result) -> str:
    texts = [c.text for c in result.content if getattr(c, "text", None)]
    text = "\n".join(texts) if texts else json.dumps(result.structured_content or {})
    if len(text) > TOOL_RESULT_CHARS:
        text = text[:TOOL_RESULT_CHARS] + f"\n[cut: {len(text) - TOOL_RESULT_CHARS} more characters]"
    return text


def call_model(model: str, messages: list[dict], tools: list[dict]) -> dict:
    """One model call with ../ask_openrouter.py's retry rules; raises base.Paused when the service is busy."""
    attempt = waited = 0
    last_error = "no attempt"
    while attempt < base.ATTEMPTS:
        error, response = None, None
        try:
            response = openrouter.complete(model, messages, tools, max_tokens=MAX_TOKENS)
        except (httpx.HTTPError, ValueError) as caught:
            error = caught
        status = base._status(error, response)
        if status in base.BUSY_CODES:
            if waited == len(base.RATE_LIMIT_WAITS):
                raise base.Paused(f"busy (HTTP {status}) after {sum(base.RATE_LIMIT_WAITS)} s of waiting")
            time.sleep(base.RATE_LIMIT_WAITS[waited])
            waited += 1
            continue
        if status in base.PAUSE_CODES:
            raise base.Paused(f"HTTP {status}: {str(error or response.get('error'))[:200]}")
        attempt += 1
        if error is None and (response.get("choices") or []):
            return response
        last_error = f"{type(error).__name__}: {str(error)[:200]}" if error else "no choices"
        time.sleep(5 * attempt)
    return {"failed": last_error}


async def converse(
    client: Client, tools: list[dict], model: str, system: str, case_id: str, message: str
) -> dict:
    messages: list[dict] = [{"role": "system", "content": system}, {"role": "user", "content": message}]
    calls, reply, cost, tokens_in, tokens_out, served, finish = [], "", 0.0, 0, 0, set(), None
    started = time.monotonic()
    failed = None
    for _ in range(MAX_ROUNDS):
        response = await asyncio.to_thread(call_model, model, messages, tools)
        if "failed" in response:
            failed = response["failed"]
            break
        usage = response.get("usage") or {}
        cost += usage.get("cost") or 0
        tokens_in += usage.get("prompt_tokens") or 0
        tokens_out += usage.get("completion_tokens") or 0
        served.add(str(response.get("provider")))
        choice = response["choices"][0]
        finish = choice.get("finish_reason")
        msg = choice.get("message") or {}
        reply = msg.get("content") or reply
        wanted = msg.get("tool_calls") or []
        if not wanted:
            break
        messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": wanted})
        for call in wanted:
            name = (call.get("function") or {}).get("name", "")
            try:
                args = json.loads((call.get("function") or {}).get("arguments") or "{}")
                result = await client.call_tool(name, args)
                text = tool_text(result)
                ok = not result.is_error
            except (
                Exception
            ) as error:  # a malformed call is the model's doing: tell it, as an MCP client would
                args, text, ok = (
                    {"raw": (call.get("function") or {}).get("arguments")},
                    f"error: {error}",
                    False,
                )
            calls.append({"tool": name, "ok": ok, "args": args})
            messages.append({"role": "tool", "tool_call_id": call.get("id"), "content": text})
    record = {
        "id": case_id,
        "model": model,
        "model_id": model,
        "reply": reply,
        "tool_calls": calls,
        "rounds": sum(1 for m in messages if m["role"] == "assistant") + 1,
        "finish_reason": finish,
        "served_by": sorted(served),
        "input_tokens": tokens_in,
        "output_tokens": tokens_out,
        "cost": cost,
        "seconds": round(time.monotonic() - started, 1),
    }
    if failed:
        record["failed"] = failed
    return record


async def run(args) -> int:
    settings = Settings.from_env()
    store = open_index(settings.index_path)
    if store is None:
        print("no index; run `deptime index pull` first", file=sys.stderr)
        return 2
    dt = DepTime(store, load_coverage(settings.coverage_file), settings.index_path)
    system = prompt_path(args.test).read_text(encoding="utf-8").strip()
    _, _, todo = base.questions(args.test)
    out_dir = HERE / args.test
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"{args.model.split('/')[-1].replace(':', '-')}-run{args.run}.jsonl"
    have, spent = set(), 0.0
    if out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            if line.strip():
                old = json.loads(line)
                have.add(old["id"])
                spent += old.get("cost") or 0
    todo = [(i, m) for i, m in todo[: args.limit] if i not in have]
    print(
        f"{args.model} {args.test} with tools, run {args.run}: {len(todo)} to ask (index built {store.built_at()})"
    )
    gate = asyncio.Semaphore(args.jobs)
    stopped = None
    async with Client(build_mcp(dt)) as client:
        tools = [as_function(t) for t in (await client.list_tools()).tools]

        async def one(case_id: str, message: str) -> dict:
            async with gate:
                return await converse(client, tools, args.model, system, case_id, message)

        tasks = [asyncio.create_task(one(i, m)) for i, m in todo]
        with out.open("a", encoding="utf-8") as sink:
            for n, finished in enumerate(asyncio.as_completed(tasks), 1):
                try:
                    rec = await finished
                except base.Paused as pause:
                    stopped = f"paused: {pause}; run the same command again later"
                    break
                spent += rec["cost"]
                sink.write(json.dumps(rec, ensure_ascii=False) + "\n")
                sink.flush()
                if n % 20 == 0 or n == len(todo):
                    print(f"  {n}/{len(todo)} asked; ${spent:.4f} spent on this run", file=sys.stderr)
                if spent > SPEND_CAP:
                    stopped = f"spend passed ${SPEND_CAP:.2f}"
                    break
        for task in tasks:
            task.cancel()
    print(f"spent on this run: ${spent:.4f}", file=sys.stderr)
    if stopped:
        print(f"STOPPED: {stopped}", file=sys.stderr)
        return 3
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--prompts", action="store_true", help="write the two system prompts and stop")
    parser.add_argument("--test", choices=("tracebacks", "upgrades"))
    parser.add_argument("--model", help="an OpenRouter model id, such as qwen/qwen3.5-9b")
    parser.add_argument("--run", type=int, default=1)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args()
    if args.prompts:
        write_prompts()
        return 0
    if not (args.test and args.model):
        parser.error("--test and --model are needed")
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
