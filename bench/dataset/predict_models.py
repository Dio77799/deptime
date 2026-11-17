"""The DT-QA-18/19 model answers on 2026-11f's upgrades, in the benchmark's prediction format (DT-OSS-14).

  uv run python bench/dataset/predict_models.py <out>

Each bench/model-alone/upgrades/answers/<model>-run<N>.jsonl becomes <out>/predictions/<model>-run<N>.uses.jsonl, read
with that study's own parser (`grade.parse_reply`): "breaks" flags a use, "works" doesn't, and "unknown" or a missing
verdict is null. The models answered from memory, with no tools; the protocol and prompt are in
bench/model-alone/upgrades/README.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

UPGRADES = Path(__file__).resolve().parents[1] / "model-alone" / "upgrades"
sys.path.insert(0, str(UPGRADES))
from cases import SET, load_upgrades  # noqa: E402
from grade import parse_reply  # noqa: E402

MODELS = {
    "sonnet": "Claude Sonnet 5.5 (`claude-sonnet-5-5`, effort high)",
    "haiku": "Claude Haiku 5.5 (`claude-haiku-5-5`, effort high)",
    "deepseek-v4.1-flash": "DeepSeek V4.1 Flash (`deepseek/deepseek-v4.1-flash`, through OpenRouter)",
    "qwen3.5-9b": "Qwen3.5 9B (`qwen/qwen3.5-9b`, through OpenRouter)",
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path, help="the bundle's directory (build.py)")
    a = ap.parse_args(argv)
    preds = a.out / "predictions"
    preds.mkdir(exist_ok=True)
    collection = SET.name
    upgrades = load_upgrades()
    about_path = preds / "about.json"
    about = json.loads(about_path.read_text(encoding="utf-8")) if about_path.exists() else {}
    for path in sorted((UPGRADES / "answers").glob("*.jsonl")):
        model, run = path.stem.rsplit("-run", 1)
        replies = {
            r["id"]: r["reply"]
            for r in (json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x)
        }
        rows = []
        for up in upgrades:
            verdicts = parse_reply(replies[up["id"]], len(up["items"])) if up["id"] in replies else None
            for n, item in enumerate(up["items"], 1):
                said = (verdicts or {}).get(n)
                rows.append({"id": f"{collection}/{up['id']}/{item['key']}", "breaks": said})
        name = f"{model}-run{run}.uses.jsonl"
        (preds / name).write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        about[name] = {
            "collection": collection,
            "what": f"{MODELS[model]} alone, no tools, answering from memory, run {run}, on 2026-11-15 (DT-QA-18/19)."
            " One question per upgrade with its uses listed; out of sample for the model.",
        }
    about_path.write_text(json.dumps(about, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(preds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
