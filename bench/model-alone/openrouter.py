"""OpenRouter access for the model-alone benchmarks: the API key, a key check, and one chat call.

  uv run python bench/model-alone/openrouter.py --check     is the key there, and does OpenRouter accept it?

The key comes from the OPENROUTER_API_KEY environment variable or, failing that, the repository's `.env` file
(`OPENROUTER_API_KEY=...`), which git ignores. Nothing here prints, logs or stores the key. Only the benchmarks'
own prompts are sent: public tracebacks and library uses already in this repository.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import httpx

API = "https://openrouter.ai/api/v1"
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
VARIABLE = "OPENROUTER_API_KEY"
TIMEOUT_SECONDS = 300


class NoKey(Exception):
    pass


def api_key() -> str:
    key = os.environ.get(VARIABLE, "").strip()
    if not key and ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            name, sep, value = line.partition("=")
            if sep and name.strip() == VARIABLE:
                key = value.strip().strip("'\"")
    if not key:
        raise NoKey(f"no {VARIABLE}: set it in the environment or after the = in {ENV_FILE}")
    return key


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key()}"}


def check() -> dict:
    """OpenRouter's description of the key (its label, limit and usage), which needs no model call."""
    response = httpx.get(f"{API}/key", headers=_headers(), timeout=30)
    response.raise_for_status()
    return response.json().get("data") or {}


def complete(
    model: str, messages: list[dict], tools: list[dict] | None = None, max_tokens: int = 4000
) -> dict:
    """One completion over a whole conversation, with the tools offered if any. Returns OpenRouter's JSON reply."""
    body: dict = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "usage": {"include": True},  # OpenRouter's own count of the call's cost
    }
    if tools:
        body["tools"] = tools
    response = httpx.post(f"{API}/chat/completions", headers=_headers(), json=body, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()


def chat(model: str, system: str, user: str, max_tokens: int = 4000) -> dict:
    """One completion, no tools. Returns OpenRouter's JSON reply (choices, usage, model)."""
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    return complete(model, messages, max_tokens=max_tokens)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="check the key with OpenRouter (no model call)")
    args = parser.parse_args()
    if not args.check:
        parser.print_help()
        return 0
    try:
        info = check()
    except NoKey as missing:
        print(missing, file=sys.stderr)
        return 2
    except httpx.HTTPStatusError as error:
        print(f"OpenRouter refused the key: HTTP {error.response.status_code}", file=sys.stderr)
        return 1
    shown = {
        # Not `label`: OpenRouter sets it to a masked form of the key itself.
        k: info.get(k)
        for k in ("limit", "limit_remaining", "usage", "is_free_tier")
        if k in info
    }
    print(f"key accepted: {shown}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
