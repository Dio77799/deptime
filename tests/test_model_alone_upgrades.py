"""The model-alone upgrade checks' question and scoring rule (DT-QA-18, bench/model-alone/upgrades). Offline: no model
is called. Loaded under their own module names, since ../model-alone has an ask.py and a grade.py too."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).parent.parent / "bench" / "model-alone" / "upgrades"
sys.path.insert(0, str(HERE))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"upgrades_{name}", HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cases = _load("cases")
grade = _load("grade")
ask = _load("ask")


def test_the_questions_are_the_scored_uses_in_a_fixed_order():
    upgrades = cases.load_upgrades()
    assert len(upgrades) == 171
    assert sum(len(u["items"]) for u in upgrades) == 2265
    assert [u["id"] for u in upgrades] == [u["id"] for u in cases.load_upgrades()]
    assert {i["label"] for u in upgrades for i in u["items"]} == {"works", "breaks"}


def test_a_use_reads_as_the_prompt_describes_it():
    assert cases.render_use({"kind": "name", "path": "openai.OpenAI"}) == "openai.OpenAI"
    assert (
        cases.render_use({"kind": "call", "path": "httpx.Client", "npos": 1, "kwargs": ["timeout"]})
        == "call: httpx.Client(_, timeout=)"
    )
    assert (
        cases.render_use(
            {"kind": "call", "path": "httpx.Client.get", "npos": 0, "kwargs": [], "via": "instance"}
        )
        == "call on an instance: httpx.Client.get()"
    )
    assert (
        cases.render_use({"kind": "name", "path": "httpx.Client.headers", "via": "instance"})
        == "attribute on an instance: httpx.Client.headers"
    )


def test_the_message_never_carries_a_label():
    for upgrade in cases.load_upgrades()[:20]:
        text = cases.user_message(upgrade)
        assert "breaks" not in text and "works with this" in text
        assert text.count("\n") == 5 + len(upgrade["items"])


def test_the_call_is_the_traceback_baseline_with_this_prompt():
    cmd = ask.command("sonnet")
    assert cmd[cmd.index("--system-prompt") + 1] == ask.SYSTEM_PROMPT
    assert cmd[cmd.index("--tools") + 1] == ""
    assert "--effort" in cmd and "--safe-mode" in cmd


def test_usage_windows_read_as_a_share():
    assert ask.utilization({"five_hour": 0.5}) == 0.5
    assert ask.utilization({"five_hour": 91}) == 0.91
    assert ask.utilization(None) is None


def test_replies_are_read_for_meaning_not_form():
    assert grade.parse_reply('{"1": "works", "2": "breaks", "3": "unknown"}', 3) == {
        1: False,
        2: True,
        3: None,
    }
    assert grade.parse_reply('```json\n{"1": " Breaks ", "2": "WORKS"}\n```', 2) == {1: True, 2: False}
    assert grade.parse_reply('["works", "breaks"]', 2) == {1: False, 2: True}
    # Out of range, not a verdict, or not a number: no verdict for that use.
    assert grade.parse_reply('{"1": "maybe", "4": "breaks", "x": "works", "2": "works"}', 3) == {2: False}
    assert grade.parse_reply("I think they all work.", 3) is None


def test_abstentions_count_apart_or_as_not_flagged():
    rows = [
        {"label": "breaks", "answers": {"m": True}},
        {"label": "breaks", "answers": {"m": None}},
        {"label": "works", "answers": {"m": None}},
        {"label": "works", "answers": {"m": True}},
        {"label": "works", "answers": {}},
    ]
    apart = grade.counts(rows, "m")
    assert (apart["tp"], apart["fn"], apart["fp"], apart["tn"]) == (1, 0, 1, 0)
    assert (apart["abstain_breaks"], apart["abstain_works"]) == (1, 2)
    as_no = grade.counts(rows, "m", abstain_as_no=True)
    assert (as_no["tp"], as_no["fn"], as_no["fp"], as_no["tn"]) == (1, 1, 1, 2)


def test_the_release_series():
    assert grade.series("0.27.2") != grade.series("0.28.0")
    assert grade.series("1.2.0") == grade.series("1.9.1")
    assert grade.series("1.65.2") != grade.series("3.49.0")
