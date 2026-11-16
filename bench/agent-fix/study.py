"""Which agent-fix study `run.py` and `score.py` work on: DT-QA-05 (the default) or DT-QA-26.

    AGENT_FIX_STUDY=qa26 uv run python bench/agent-fix/run.py tasks

Each study keeps its own protocol, tasks, sessions, diffs, probe environments and hand checks: DT-QA-05's in this
directory (frozen with its results), DT-QA-26's in `qa26/`. Only what differs between them is here.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Study:
    name: str  # the backlog ID
    out: Path  # tasks.json, sessions/, diffs/, envs.json, hand-*.json
    work: Path  # task repositories, session copies and transcripts
    holdout_sets: tuple[str, ...]  # sets whose upward upgrades with a labelled break are tasks
    # those sets' task ids, when the protocol names them (None: every one)
    holdout_only: tuple[str, ...] | None
    prs: bool  # DT-QA-22's pull requests with a labelled break are tasks too
    trial_set: str
    trial_tasks: tuple[str, ...]
    deptime_pin: str
    bash_rules: tuple[str, ...]  # the Bash commands arms B and C may run
    arms_by_run: dict[int, list[str]]
    seed: int
    scored: tuple[str, ...]


_TRIAL = ("pin-wayveai__driving-with-llms-openai-up", "pin-vivekkeshore__flask-dantic-pydantic-up")

STUDIES = {
    "qa05": Study(
        name="DT-QA-05",
        out=HERE,
        work=Path(os.environ.get("QA05_WORK", "~/.cache/deptime-work/qa05")).expanduser(),
        holdout_sets=("2026-11f",),
        holdout_only=(  # README.md: every 2026-11f upgrade to a newer version with a labelled break
            "pin-tonypeng1__personal-chatgpt-mistralai-up",
            "pin-ai-learning-gems__ai-learning-gems.github.io-mistralai-up",
            "pin-aianytime__medical-rag-using-bio-mistral-7b-langchain-community-up",
            "pin-mindsdb__minds-mcp-mcp-up",
            "pin-gaa-uam__c-gb-scikit-learn-up",
            "pin-oaklight__mango-anthropic-up",
            "pin-surajrimal07__nepseapi-unofficial-fastmcp-up",
            "pin-dtunai__synthtot-langchain-up",
            "pin-jerome3o__schemallm-langchain-up",
            "pin-mbzuai-oryx__xraygpt-gradio-up",
            "pin-wpydcr__llm-kit-gradio-up",
            "ex-2023csb1141__iitd-summer-intern-huggingface-hub-up",
        ),
        prs=True,
        trial_set="2026-11e",
        trial_tasks=_TRIAL,
        deptime_pin="deptime==0.2.1",
        bash_rules=("Bash(uvx deptime==0.2.1 check-upgrade:*)",),
        arms_by_run={1: ["A", "B", "C"], 2: ["A", "B"]},
        seed=5,
        scored=("A1", "A2", "B1", "B2", "C1"),
    ),
    "qa26": Study(
        name="DT-QA-26",
        out=HERE / "qa26",
        work=Path(os.environ.get("QA26_WORK", "~/.cache/deptime-work/qa26")).expanduser(),
        holdout_sets=("2026-11", "2026-11b", "2026-11c", "2026-11d", "2026-11e"),
        holdout_only=None,  # qa26/README.md: every one, but the trial tasks
        prs=False,
        trial_set="2026-11e",
        trial_tasks=_TRIAL,
        deptime_pin="deptime==0.2.2",
        bash_rules=("Bash(uvx deptime==0.2.2 check-upgrade:*)", "Bash(rm .deptime-report.md)"),
        arms_by_run={1: ["A", "B"]},
        seed=26,
        scored=("A1", "B1"),
    ),
}

STUDY = STUDIES[os.environ.get("AGENT_FIX_STUDY", "qa05")]
