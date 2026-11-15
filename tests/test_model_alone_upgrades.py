"""The model-alone upgrade checks' question and scoring rule (DT-QA-18, bench/model-alone/upgrades). Offline: no model
is called. Loaded under their own module names, since ../model-alone has an ask.py and a grade.py too."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).parent.parent / "bench" / "model-alone" / "upgrades"
sys.path.insert(0, str(HERE))


def _load_from(folder: Path, name: str, prefix: str = ""):
    spec = importlib.util.spec_from_file_location(f"{prefix}{name}", folder / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


sys.path.insert(0, str(HERE.parent))
ask_openrouter = _load_from(HERE.parent, "ask_openrouter")


def test_an_openrouter_reply_becomes_what_the_graders_read():
    response = {
        "model": "qwen/qwen3.5-9b-0310",
        "provider": "Example",
        "choices": [{"finish_reason": "stop", "message": {"content": '{"1": "works"}'}}],
        "usage": {
            "prompt_tokens": 900,
            "completion_tokens": 300,
            "completion_tokens_details": {"reasoning_tokens": 250},
            "cost": 0.0001,
        },
    }
    rec = ask_openrouter.record("u1", "qwen/qwen3.5-9b", response, 1.234)
    assert rec["model_id"] == "qwen/qwen3.5-9b" and rec["reply"] == '{"1": "works"}'
    assert rec["served_by"] == {"model": "qwen/qwen3.5-9b-0310", "provider": "Example"}
    assert (rec["input_tokens"], rec["output_tokens"], rec["thinking_tokens"]) == (900, 300, 250)
    # No choices, or no text: an empty reply, which ask_one tries again.
    assert ask_openrouter.record("u1", "m", {"error": {"code": 502}}, 0)["reply"] == ""


def test_both_tests_are_asked_in_the_claude_runs_order():
    _, answers, upgrades = ask_openrouter.questions("upgrades")
    assert answers.name == "answers" and answers.parent.name == "upgrades"
    assert [i for i, _ in upgrades] == [u["id"] for u in cases.load_upgrades()]
    assert upgrades[0][1] == cases.user_message(cases.load_upgrades()[0])
    system, answers, tracebacks = ask_openrouter.questions("tracebacks")
    assert len(tracebacks) == 191 and answers.parent.name == "model-alone"
    assert system.startswith("You diagnose Python errors")


def test_a_rate_limit_pauses_the_run_and_stores_nothing(monkeypatch):
    calls = []

    def limited(*args, **kwargs):
        calls.append(1)
        return {"error": {"code": 503, "message": "overloaded"}}

    monkeypatch.setattr(ask_openrouter.openrouter, "chat", limited)
    monkeypatch.setattr(ask_openrouter.time, "sleep", lambda s: None)
    try:
        ask_openrouter.ask_one("u1", "message", "m:free", "system")
    except ask_openrouter.Paused:
        pass
    else:
        raise AssertionError("a lasting rate limit must pause, not return a reply to store")
    assert len(calls) == len(ask_openrouter.RATE_LIMIT_WAITS) + 1


def test_a_rate_limit_then_an_answer_counts_as_one_attempt(monkeypatch):
    replies = iter(
        [
            {"error": {"code": 429}},
            {"choices": [{"finish_reason": "stop", "message": {"content": "{}"}}], "usage": {}},
        ]
    )
    monkeypatch.setattr(ask_openrouter.openrouter, "chat", lambda *a, **k: next(replies))
    monkeypatch.setattr(ask_openrouter.time, "sleep", lambda s: None)
    assert ask_openrouter.ask_one("u1", "message", "m", "system")["reply"] == "{}"


with_tools = _load_from(HERE.parent / "with-tools", "ask", prefix="with_tools_")


def test_the_with_tools_prompts_change_one_sentence():
    for test in ("tracebacks", "upgrades"):
        alone, _, _ = ask_openrouter.questions(test)
        prompt = with_tools.prompt_path(test).read_text(encoding="utf-8")
        assert with_tools.NO_TOOLS in alone and with_tools.NO_TOOLS not in prompt
        assert prompt.startswith(alone.replace(with_tools.NO_TOOLS, with_tools.WITH_TOOLS))
        assert "DepTime's own instructions:" in prompt


class _FakeClient:
    def __init__(self):
        self.called = []

    async def call_tool(self, name, args):
        self.called.append((name, args))
        from types import SimpleNamespace

        return SimpleNamespace(
            content=[SimpleNamespace(text='{"findings": []}')], structured_content=None, is_error=False
        )


def test_a_conversation_runs_the_tools_and_ends_on_an_answer(monkeypatch):
    import asyncio

    replies = iter(
        [
            {
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "c1",
                                    "function": {"name": "explain_error", "arguments": '{"traceback": "x"}'},
                                }
                            ],
                        },
                    }
                ],
                "usage": {"cost": 0.001, "prompt_tokens": 10, "completion_tokens": 5},
            },
            {
                "choices": [{"finish_reason": "stop", "message": {"content": '{"package": "httpx"}'}}],
                "usage": {"cost": 0.002},
            },
        ]
    )
    seen = []

    def fake_call(model, messages, tools):
        seen.append([m["role"] for m in messages])
        return next(replies)

    monkeypatch.setattr(with_tools, "call_model", fake_call)
    client = _FakeClient()
    rec = asyncio.run(with_tools.converse(client, [], "m", "system", "c", "question"))
    assert client.called == [("explain_error", {"traceback": "x"})]
    assert seen[1] == ["system", "user", "assistant", "tool"]
    assert rec["reply"] == '{"package": "httpx"}' and rec["tool_calls"][0]["ok"]
    assert abs(rec["cost"] - 0.003) < 1e-9 and "failed" not in rec


def test_a_long_tool_result_is_cut_and_says_so():
    from types import SimpleNamespace

    long = SimpleNamespace(content=[SimpleNamespace(text="x" * 40000)], structured_content=None)
    text = with_tools.tool_text(long)
    assert len(text) < 31000 and text.endswith("more characters]")


def test_an_answer_left_in_the_reasoning_is_the_last_json_object():
    assert with_tools.last_json_object('a {"x": 1} b {"1": "works"} end') == '{"1": "works"}'
    assert with_tools.last_json_object("no answer") is None
